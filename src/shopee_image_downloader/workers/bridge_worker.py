"""WebSocket bridge server worker for Chrome Extension communication."""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocket, QWebSocketServer

from shopee_image_downloader.core.bridge_protocol import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    MSG_TYPE_HELLO,
    MSG_TYPE_PROCESS_ERROR,
    MSG_TYPE_PROCESS_PROGRESS,
    MSG_TYPE_PRODUCT_RESULT,
    create_error_message,
    create_hello_ack_message,
    create_product_result_ack_message,
    parse_bridge_product_data,
    validate_incoming_message,
)

logger = logging.getLogger(__name__)


class ExtensionBridgeServer(QObject):
    """Event-driven WebSocket server for communication with the Shopee Chrome Extension.

    Binds strictly to loopback address (127.0.0.1) and handles versioned JSON protocol.
    """

    connection_status_changed = Signal(bool)  # True = connected, False = disconnected
    product_received = Signal(object)  # Emits BridgeProductData
    process_progress_received = Signal(str, str)  # Emits (request_id, stage)
    process_error_received = Signal(str, str, str, str)  # Emits (request_id, url, error_code, message)
    error_occurred = Signal(str)

    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.host = host
        self.port = port
        self._server: QWebSocketServer | None = None
        self._clients: set[QWebSocket] = set()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Return whether server is actively listening."""
        return self._is_running

    @property
    def has_connected_clients(self) -> bool:
        """Return whether at least one client is connected."""
        return len(self._clients) > 0

    def start_server(self) -> bool:
        """Initialize and start the WebSocket server on loopback interface."""
        if self._server is not None:
            self.stop_server()

        self._server = QWebSocketServer(
            "ShopeeExtensionBridge",
            QWebSocketServer.SslMode.NonSecureMode,
            self,
        )

        # Enforce loopback address strictly (127.0.0.1)
        bind_address = QHostAddress(self.host)
        if not bind_address.isLoopback():
            err = f"Từ chối khởi chạy máy chủ: Địa chỉ '{self.host}' không phải loopback (127.0.0.1)"
            logger.error(err)
            self.error_occurred.emit(err)
            return False

        listen_success = self._server.listen(bind_address, self.port)
        if not listen_success:
            err = f"Không thể lắng nghe trên {self.host}:{self.port} - {self._server.errorString()}"
            logger.error(err)
            self.error_occurred.emit(err)
            self._is_running = False
            return False

        self._server.newConnection.connect(self._on_new_connection)
        self._server.acceptError.connect(self._on_accept_error)
        self._is_running = True
        logger.info(f"WebSocket bridge server đang lắng nghe tại {self.host}:{self._server.serverPort()}")
        return True

    def stop_server(self) -> None:
        """Stop server and disconnect all active clients."""
        for client in list(self._clients):
            try:
                client.close()
            except Exception:
                pass
        self._clients.clear()

        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None

        self._is_running = False
        self.connection_status_changed.emit(False)
        logger.info("WebSocket bridge server đã dừng")

    def _on_accept_error(self, socket_error: object) -> None:
        """Handle socket accept errors."""
        err_msg = f"Lỗi chấp nhận kết nối: {socket_error}"
        logger.warning(err_msg)
        self.error_occurred.emit(err_msg)

    def _on_new_connection(self) -> None:
        """Handle incoming WebSocket client connection."""
        if not self._server:
            return

        client_socket = self._server.nextPendingConnection()
        if not client_socket:
            return

        peer_address = client_socket.peerAddress().toString()
        logger.info(f"Client kết nối mới từ {peer_address}")

        self._clients.add(client_socket)
        client_socket.textMessageReceived.connect(
            lambda msg, s=client_socket: self._on_text_message(msg, s)
        )
        client_socket.disconnected.connect(
            lambda s=client_socket: self._on_client_disconnected(s)
        )

    def _on_client_disconnected(self, socket: QWebSocket) -> None:
        """Handle client disconnection."""
        if socket in self._clients:
            self._clients.remove(socket)
            peer_address = socket.peerAddress().toString()
            logger.info(f"Client ngắt kết nối: {peer_address}")

        if not self._clients:
            self.connection_status_changed.emit(False)

        socket.deleteLater()

    def send_message(self, data: dict[str, Any] | str) -> bool:
        """Send a JSON message to all currently connected clients (Native Host)."""
        if not self._clients:
            logger.warning("Không thể gửi tin nhắn: Không có client nào kết nối")
            return False

        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        success = True
        for client in list(self._clients):
            try:
                client.sendTextMessage(text)
            except Exception as ex:
                logger.error(f"Lỗi gửi tin nhắn tới client: {ex}")
                success = False
        return success

    def _on_text_message(self, message: str, socket: QWebSocket) -> None:
        """Process incoming text message from client socket."""
        is_valid, parsed_data, error_msg = validate_incoming_message(message)

        if not is_valid or parsed_data is None:
            logger.warning(f"Từ chối tin nhắn không hợp lệ: {error_msg}")
            request_id = ""
            source_url = ""
            try:
                raw_data = json.loads(message)
                if isinstance(raw_data, dict):
                    request_id = str(raw_data.get("request_id", "")).strip()
                    inner = raw_data.get("data")
                    if isinstance(inner, dict):
                        source_url = str(
                            inner.get("input_url") or inner.get("url") or ""
                        ).strip()
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            if request_id:
                self.process_error_received.emit(
                    request_id,
                    source_url,
                    "PROTOCOL_INTEGRITY_ERROR",
                    error_msg or "Invalid bridge message",
                )
            try:
                socket.sendTextMessage(create_error_message(error_msg or "Tin nhắn không hợp lệ"))
            except Exception:
                pass
            if not request_id:
                self.error_occurred.emit(error_msg or "Tin nhắn không hợp lệ")
            return

        msg_type = parsed_data.get("type")

        if msg_type == MSG_TYPE_HELLO:
            logger.info("Nhận handshake 'hello' từ Extension")
            try:
                socket.sendTextMessage(create_hello_ack_message())
            except Exception as ex:
                logger.error(f"Lỗi khi gửi hello_ack: {ex}")
            self.connection_status_changed.emit(True)
            return

        if msg_type == MSG_TYPE_PROCESS_PROGRESS:
            req_id = str(parsed_data.get("request_id", "")).strip()
            stage = str(parsed_data.get("stage", "")).strip()
            logger.info(f"Nhận process_progress: req={req_id}, stage={stage}")
            self.process_progress_received.emit(req_id, stage)
            return

        if msg_type == MSG_TYPE_PROCESS_ERROR:
            req_id = str(parsed_data.get("request_id", "")).strip()
            url = str(parsed_data.get("url", "")).strip()
            error_code = str(parsed_data.get("error_code", "ERROR")).strip()
            msg = str(parsed_data.get("message", "")).strip()
            logger.info(f"Nhận process_error: req={req_id}, code={error_code}, msg={msg}")
            self.process_error_received.emit(req_id, url, error_code, msg)
            return

        if msg_type == MSG_TYPE_PRODUCT_RESULT:
            try:
                product_data = parse_bridge_product_data(parsed_data)
                logger.info(
                    "[DESKTOP IN]\nrequest_id=%s\nproduct_key=%s\nimages=%d",
                    product_data.request_id or "N/A",
                    product_data.product_key,
                    len(product_data.images),
                )
                socket.sendTextMessage(create_product_result_ack_message(True, "Đã nhận thành công"))
                self.product_received.emit(product_data)
            except Exception as ex:
                err = f"Lỗi xử lý product_result: {ex}"
                logger.exception(err)
                req_id = str(parsed_data.get("request_id", "")).strip()
                if req_id:
                    self.process_error_received.emit(
                        req_id,
                        "",
                        "PROTOCOL_INTEGRITY_ERROR",
                        err,
                    )
                socket.sendTextMessage(create_error_message(err))
                if not req_id:
                    self.error_occurred.emit(err)
            return
