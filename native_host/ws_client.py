"""Lightweight standard-library RFC 6455 WebSocket client for Native Host ↔ Desktop communication."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import socket
import struct
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# Frame Opcodes
OPCODE_CONTINUATION = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA


class SimpleWebSocketClient:
    """Self-contained WebSocket client connecting strictly to loopback interface."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._is_connected = False
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._on_message_callback: Callable[[str], None] | None = None
        self._on_close_callback: Callable[[], None] | None = None
        self._stop_requested = False

    @property
    def is_connected(self) -> bool:
        """Return whether client is actively connected."""
        return self._is_connected

    def connect(self, timeout: float = 2.0) -> bool:
        """Attempt to connect and perform WebSocket handshake with loopback server.

        Returns True on successful handshake, False if server is offline or rejected.
        """
        self.close()
        self._stop_requested = False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))

            # Perform HTTP Upgrade Handshake
            key_raw = os.urandom(16)
            key_b64 = base64.b64encode(key_raw).decode("ascii")

            handshake_req = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key_b64}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n"
            )

            sock.sendall(handshake_req.encode("utf-8"))

            # Read Handshake Response Header
            response_bytes = bytearray()
            while b"\r\n\r\n" not in response_bytes:
                chunk = sock.recv(1024)
                if not chunk:
                    sock.close()
                    return False
                response_bytes.extend(chunk)

            header_text = response_bytes.decode("utf-8", errors="replace")
            status_line = header_text.split("\r\n", 1)[0]
            if "101" not in status_line:
                logger.warning("WebSocket handshake rejected: %s", status_line)
                sock.close()
                return False

            sock.settimeout(None)  # Set to blocking for receiver thread
            self._sock = sock
            self._is_connected = True
            logger.info("WebSocket connected successfully to %s:%d", self.host, self.port)
            return True

        except (ConnectionRefusedError, OSError, socket.timeout) as exc:
            logger.debug("Failed to connect to %s:%d: %s", self.host, self.port, exc)
            self._cleanup_socket()
            return False

    def start_listener(
        self,
        on_message: Callable[[str], None],
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """Start background receiver thread to process incoming frames."""
        self._on_message_callback = on_message
        self._on_close_callback = on_close

        if self._reader_thread and self._reader_thread.is_alive():
            return

        self._reader_thread = threading.Thread(
            target=self._recv_loop,
            daemon=True,
            name="WSClient-Reader",
        )
        self._reader_thread.start()

    def send_text(self, text: str) -> bool:
        """Send a masked UTF-8 text frame over the WebSocket."""
        with self._lock:
            if not self._is_connected or not self._sock:
                return False

            payload = text.encode("utf-8")
            payload_len = len(payload)
            frame = bytearray()

            # Byte 0: FIN (0x80) | OPCODE_TEXT (0x01)
            frame.append(0x80 | OPCODE_TEXT)

            # Byte 1: Mask bit (0x80) | length
            if payload_len < 126:
                frame.append(0x80 | payload_len)
            elif payload_len <= 0xFFFF:
                frame.append(0x80 | 126)
                frame.extend(struct.pack(">H", payload_len))
            else:
                frame.append(0x80 | 127)
                frame.extend(struct.pack(">Q", payload_len))

            # 4-byte masking key
            mask = os.urandom(4)
            frame.extend(mask)

            # Masked payload
            masked_payload = bytearray(payload_len)
            for i in range(payload_len):
                masked_payload[i] = payload[i] ^ mask[i % 4]
            frame.extend(masked_payload)

            try:
                self._sock.sendall(frame)
                return True
            except OSError as err:
                logger.error("Error sending frame: %s", err)
                self._is_connected = False
                return False

    def _recv_exact(self, count: int) -> bytes | None:
        """Receive exact number of bytes or return None on EOF/error."""
        sock = self._sock
        if not sock:
            return None
        buf = bytearray()
        while len(buf) < count:
            try:
                chunk = sock.recv(count - len(buf))
                if not chunk:
                    return None
                buf.extend(chunk)
            except OSError:
                return None
        return bytes(buf)

    def _recv_loop(self) -> None:
        """Continuously read and dispatch incoming WebSocket frames."""
        try:
            while self._is_connected and not self._stop_requested:
                header = self._recv_exact(2)
                if not header:
                    break

                byte0, byte1 = header[0], header[1]
                fin = bool(byte0 & 0x80)
                opcode = byte0 & 0x0F
                is_masked = bool(byte1 & 0x80)
                payload_len = byte1 & 0x7F

                if payload_len == 126:
                    len_bytes = self._recv_exact(2)
                    if not len_bytes:
                        break
                    payload_len = struct.unpack(">H", len_bytes)[0]
                elif payload_len == 127:
                    len_bytes = self._recv_exact(8)
                    if not len_bytes:
                        break
                    payload_len = struct.unpack(">Q", len_bytes)[0]

                mask_key = None
                if is_masked:
                    mask_key = self._recv_exact(4)
                    if not mask_key:
                        break

                payload_data = bytearray()
                if payload_len > 0:
                    raw_data = self._recv_exact(payload_len)
                    if not raw_data:
                        break
                    if is_masked and mask_key:
                        payload_data = bytearray(
                            raw_data[i] ^ mask_key[i % 4] for i in range(payload_len)
                        )
                    else:
                        payload_data = bytearray(raw_data)

                if opcode == OPCODE_CLOSE:
                    logger.info("Received WebSocket close frame from server")
                    break

                if opcode == OPCODE_PING:
                    # Respond with Pong
                    self._send_pong(payload_data)
                    continue

                if opcode == OPCODE_TEXT:
                    text_str = payload_data.decode("utf-8", errors="replace")
                    if self._on_message_callback:
                        try:
                            self._on_message_callback(text_str)
                        except Exception as cb_err:
                            logger.error("Error in message callback: %s", cb_err)

        except Exception as exc:
            logger.debug("Exception in ws receive loop: %s", exc)
        finally:
            self._cleanup_socket()
            if self._on_close_callback and not self._stop_requested:
                try:
                    self._on_close_callback()
                except Exception:
                    pass

    def _send_pong(self, data: bytes) -> None:
        """Send masked Pong frame in response to Ping."""
        with self._lock:
            if not self._is_connected or not self._sock:
                return
            frame = bytearray()
            frame.append(0x80 | OPCODE_PONG)
            frame.append(0x80 | (len(data) & 0x7F))
            mask = os.urandom(4)
            frame.extend(mask)
            frame.extend(bytes(data[i] ^ mask[i % 4] for i in range(len(data))))
            try:
                self._sock.sendall(frame)
            except OSError:
                pass

    def _cleanup_socket(self) -> None:
        """Close socket and mark state as disconnected."""
        self._is_connected = False
        sock = self._sock
        self._sock = None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass

    def close(self) -> None:
        """Cleanly close the WebSocket client."""
        self._stop_requested = True
        self._cleanup_socket()
        if self._reader_thread and threading.current_thread() != self._reader_thread:
            self._reader_thread.join(timeout=1.0)
            self._reader_thread = None
