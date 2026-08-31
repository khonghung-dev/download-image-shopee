"""Chrome Native Messaging Host for Shopee Image Downloader.

Relays messages bidirectionally between the Chrome Extension (via stdin/stdout)
and the PySide6 desktop application (via localhost WebSocket on 127.0.0.1:8765).
"""

from __future__ import annotations

import json
import logging
import os
import struct
import sys
import threading
from typing import Any

from ws_client import SimpleWebSocketClient

# Constants
PROTOCOL_VERSION = 1
MAX_MESSAGE_SIZE = 5 * 1024 * 1024  # 5 MB
DESKTOP_HOST = "127.0.0.1"
DESKTOP_PORT = 8765


# Configure Logging (File only, never stdout)
def setup_logging() -> None:
    """Configure non-sensitive file logging in LocalAppData."""
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(local_app_data, "ShopeeImageDownloader", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "native_host.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
        encoding="utf-8",
    )


logger = logging.getLogger("native_host")


class NativeMessagingHost:
    """Manages Chrome Native Messaging stdio framing and WebSocket relay."""

    def __init__(
        self,
        host: str = DESKTOP_HOST,
        port: int = DESKTOP_PORT,
        stdin_stream: Any | None = None,
        stdout_stream: Any | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._stdin = stdin_stream
        self._stdout = stdout_stream
        self.ws_client = SimpleWebSocketClient(host=self.host, port=self.port)
        self._stdout_lock = threading.Lock()
        self._running = True

    @property
    def stdout_stream(self) -> Any:
        if self._stdout is not None:
            return self._stdout
        return sys.stdout.buffer

    @property
    def stdin_stream(self) -> Any:
        if self._stdin is not None:
            return self._stdin
        return sys.stdin.buffer

    def send_native_message(self, message_dict: dict[str, Any]) -> bool:
        """Encode and write a 4-byte length-prefixed JSON message to stdout."""
        try:
            payload_bytes = json.dumps(message_dict, ensure_ascii=False).encode("utf-8")
            if len(payload_bytes) > MAX_MESSAGE_SIZE:
                logger.error("Message exceeds maximum size: %d bytes", len(payload_bytes))
                return False

            length_prefix = struct.pack("<I", len(payload_bytes))

            with self._stdout_lock:
                stream = self.stdout_stream
                stream.write(length_prefix)
                stream.write(payload_bytes)
                stream.flush()
            return True
        except Exception as exc:
            logger.error("Failed to send native message: %s", exc)
            return False

    def read_exact_stdin(self, num_bytes: int) -> bytes | None:
        """Read exact number of bytes from stdin stream."""
        buf = bytearray()
        stream = self.stdin_stream
        while len(buf) < num_bytes:
            chunk = stream.read(num_bytes - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def read_native_message(self) -> dict[str, Any] | None:
        """Read one 4-byte length-prefixed JSON message from stdin."""
        raw_length = self.read_exact_stdin(4)
        if not raw_length:
            return None  # Clean EOF when Chrome closes port

        message_length = struct.unpack("<I", raw_length)[0]
        if message_length == 0:
            return {}

        if message_length > MAX_MESSAGE_SIZE:
            logger.error("Incoming native message too large: %d bytes", message_length)
            # Skip invalid large message to avoid memory exhaustion
            self.read_exact_stdin(min(message_length, 1024 * 1024))
            return {"type": "error", "error": "Message size exceeds limit"}

        raw_payload = self.read_exact_stdin(message_length)
        if not raw_payload:
            return None

        try:
            payload_str = raw_payload.decode("utf-8")
            return json.loads(payload_str)
        except Exception as err:
            logger.error("Failed to decode JSON from stdin: %s", err)
            return {"type": "error", "error": f"Invalid JSON payload: {err}"}

    def _on_ws_message_received(self, text: str) -> None:
        """Callback when desktop app sends a message over WebSocket."""
        logger.info("Received WebSocket frame from Desktop: %s", text[:120])
        try:
            parsed = json.loads(text)
            if parsed.get("type") == "hello_ack":
                return
            self.send_native_message(parsed)
        except Exception as err:
            logger.error("Failed to parse Desktop WebSocket payload: %s", err)

    def _on_ws_closed(self) -> None:
        """Callback when desktop app WebSocket closes or disconnects."""
        logger.info("Desktop WebSocket disconnected")
        self.send_native_message({
            "protocol_version": PROTOCOL_VERSION,
            "type": "bridge_status",
            "desktop_connected": False,
            "message": "Mất kết nối với Desktop. Hãy mở ứng dụng rồi nhấn \"Kết nối lại\".",
        })

    def ensure_desktop_connection(self) -> bool:
        """Ensure WebSocket connection to desktop is open; attempt connect if offline."""
        if self.ws_client.is_connected:
            return True

        connected = self.ws_client.connect(timeout=1.5)
        if connected:
            self.ws_client.start_listener(
                on_message=self._on_ws_message_received,
                on_close=self._on_ws_closed,
            )
            # Send initial handshake to Desktop
            self.ws_client.send_text(json.dumps({
                "type": "hello",
                "protocol_version": PROTOCOL_VERSION,
                "client": "shopee_chrome_extension",
            }))
            return True
        return False

    def handle_incoming_message(self, message: dict[str, Any]) -> None:
        """Process an incoming message from the Chrome Extension."""
        msg_type = message.get("type", "")
        logger.info("Processing message from Chrome Extension: %s", msg_type)

        if msg_type == "connect_desktop":
            connected = self.ensure_desktop_connection()
            if connected:
                self.send_native_message({
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "bridge_status",
                    "desktop_connected": True,
                    "message": "Đã kết nối với Desktop.",
                })
            else:
                self.send_native_message({
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "bridge_status",
                    "desktop_connected": False,
                    "message": "Shopee Image Downloader chưa được mở.",
                })
            return

        # The host is a transport relay. Message validation and business state
        # remain with the extension and desktop application.
        if self.ensure_desktop_connection():
            sent = self.ws_client.send_text(json.dumps(message, ensure_ascii=False))
            if not sent and msg_type == "product_result":
                self.send_native_message({
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "product_result_ack",
                    "success": False,
                    "error": "Không thể gửi dữ liệu tới Desktop.",
                })
        else:
            if msg_type == "product_result":
                self.send_native_message({
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "product_result_ack",
                    "success": False,
                    "error": "Shopee Image Downloader chưa được mở (127.0.0.1:8765).",
                })
            else:
                self.send_native_message({
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "error",
                    "error": f"Desktop chưa kết nối để nhận lệnh '{msg_type}'.",
                })

    def run(self) -> None:
        """Main execution loop reading native frames until stdin EOF."""
        logger.info("Native Host started. Entering message loop.")
        try:
            # Announce initial status to extension
            connected = self.ensure_desktop_connection()
            self.send_native_message({
                "protocol_version": PROTOCOL_VERSION,
                "type": "bridge_status",
                "desktop_connected": connected,
                "message": "Đã kết nối với Desktop." if connected else "Shopee Image Downloader chưa được mở.",
            })

            while self._running:
                message = self.read_native_message()
                if message is None:
                    # Clean termination on EOF
                    logger.info("Stdin EOF reached. Shutting down native host.")
                    break
                self.handle_incoming_message(message)

        except Exception as exc:
            logger.exception("Unexpected exception in Native Host loop: %s", exc)
        finally:
            self.ws_client.close()
            logger.info("Native Host terminated cleanly.")


def main() -> None:
    """Entry point configuring binary stdio mode and running host."""
    setup_logging()

    # Ensure binary mode on Windows for stdin and stdout
    if sys.platform == "win32":
        try:
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        except Exception as e:
            logger.warning("Could not set binary mode via msvcrt: %s", e)

    host = NativeMessagingHost()
    host.run()


if __name__ == "__main__":
    main()
