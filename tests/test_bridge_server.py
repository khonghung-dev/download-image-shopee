"""Unit and integration tests for ExtensionBridgeServer WebSocket server."""

import json
from PySide6.QtCore import QUrl
from PySide6.QtWebSockets import QWebSocket
import pytest

from shopee_image_downloader.core.bridge_protocol import (
    MSG_TYPE_HELLO,
    MSG_TYPE_PRODUCT_RESULT,
    PROTOCOL_VERSION,
    BridgeProductData,
)
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer

NATIVE_HOST_CLIENT = "shopee_chrome_extension"


@pytest.fixture
def bridge_server(qtbot):
    """Fixture providing a started ExtensionBridgeServer on an ephemeral loopback port."""
    server = ExtensionBridgeServer(host="127.0.0.1", port=0)
    started = server.start_server()
    assert started is True
    assert server.is_running is True

    yield server

    server.stop_server()


def test_server_rejects_non_loopback(qtbot):
    """Verify that server strictly rejects non-loopback interfaces (e.g. 0.0.0.0 or LAN)."""
    server = ExtensionBridgeServer(host="0.0.0.0", port=0)
    with qtbot.waitSignal(server.error_occurred, timeout=1000):
        started = server.start_server()
    assert started is False
    assert server.is_running is False


def test_server_handshake_hello_ack(qtbot, bridge_server):
    """Verify hello handshake exchange and connection_status_changed signal."""
    client_socket = QWebSocket()
    received_messages = []

    client_socket.textMessageReceived.connect(lambda msg: received_messages.append(json.loads(msg)))

    port = bridge_server._server.serverPort()
    client_url = QUrl(f"ws://127.0.0.1:{port}")

    with qtbot.waitSignal(client_socket.connected, timeout=2000):
        client_socket.open(client_url)

    assert client_socket.isValid() is True

    # Send hello handshake
    hello_msg = json.dumps({
        "type": MSG_TYPE_HELLO,
        "protocol_version": PROTOCOL_VERSION,
        "client": NATIVE_HOST_CLIENT,
    })

    with qtbot.waitSignal(bridge_server.connection_status_changed, timeout=2000) as blocker:
        client_socket.sendTextMessage(hello_msg)
        qtbot.waitUntil(lambda: len(received_messages) > 0, timeout=2000)

    assert blocker.args == [True]
    assert len(received_messages) == 1
    assert received_messages[0]["type"] == "hello_ack"
    assert received_messages[0]["protocol_version"] == PROTOCOL_VERSION

    # Disconnect client
    with qtbot.waitSignal(bridge_server.connection_status_changed, timeout=2000) as blocker_disc:
        client_socket.close()

    assert blocker_disc.args == [False]


def test_server_receives_valid_product_result(qtbot, bridge_server):
    """Verify valid product_result processing, signal emission, and product_result_ack response."""
    client_socket = QWebSocket()
    received_messages = []

    client_socket.textMessageReceived.connect(lambda msg: received_messages.append(json.loads(msg)))

    port = bridge_server._server.serverPort()
    client_url = QUrl(f"ws://127.0.0.1:{port}")

    with qtbot.waitSignal(client_socket.connected, timeout=2000):
        client_socket.open(client_url)

    payload = {
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "data": {
            "url": "https://shopee.vn/product-test",
            "product_name": "Giày thể thao nam siêu êm",
            "shop_id": "88888",
            "item_id": "99999",
            "images": [
                "https://down-vn.img.susercontent.com/file/shoe1.jpg",
                "https://down-vn.img.susercontent.com/file/shoe2.jpg",
                "https://down-vn.img.susercontent.com/file/shoe3.jpg",
            ],
        },
    }

    with qtbot.waitSignal(bridge_server.product_received, timeout=2000) as blocker:
        client_socket.sendTextMessage(json.dumps(payload))
        qtbot.waitUntil(lambda: len(received_messages) > 0, timeout=2000)

    received_data: BridgeProductData = blocker.args[0]
    assert isinstance(received_data, BridgeProductData)
    assert received_data.product_name == "Giày thể thao nam siêu êm"
    assert received_data.shop_id == "88888"
    assert received_data.item_id == "99999"
    assert len(received_data.images) == 3
    assert received_data.product_key == "88888:99999"

    assert len(received_messages) == 1
    assert received_messages[0]["type"] == "product_result_ack"
    assert received_messages[0]["success"] is True

    client_socket.close()


def test_server_handles_malformed_message_gracefully(qtbot, bridge_server):
    """Verify server rejects malformed messages safely without crashing."""
    client_socket = QWebSocket()
    received_messages = []

    client_socket.textMessageReceived.connect(lambda msg: received_messages.append(json.loads(msg)))

    port = bridge_server._server.serverPort()
    client_url = QUrl(f"ws://127.0.0.1:{port}")

    with qtbot.waitSignal(client_socket.connected, timeout=2000):
        client_socket.open(client_url)

    with qtbot.waitSignal(bridge_server.error_occurred, timeout=2000):
        client_socket.sendTextMessage("INVALID_NON_JSON")
        qtbot.waitUntil(lambda: len(received_messages) > 0, timeout=2000)

    assert len(received_messages) == 1
    assert received_messages[0]["type"] == "error"

    client_socket.close()


def test_server_disconnect_and_reconnect(qtbot, bridge_server):
    """Verify that multiple consecutive connection and disconnection cycles work seamlessly."""
    port = bridge_server._server.serverPort()
    client_url = QUrl(f"ws://127.0.0.1:{port}")

    hello_msg = json.dumps({
        "type": MSG_TYPE_HELLO,
        "protocol_version": PROTOCOL_VERSION,
        "client": NATIVE_HOST_CLIENT,
    })

    for cycle in range(2):
        client_socket = QWebSocket()
        received = []
        client_socket.textMessageReceived.connect(lambda m: received.append(json.loads(m)))

        with qtbot.waitSignal(client_socket.connected, timeout=2000):
            client_socket.open(client_url)

        with qtbot.waitSignal(bridge_server.connection_status_changed, timeout=2000) as blocker_conn:
            client_socket.sendTextMessage(hello_msg)
            qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)

        assert blocker_conn.args == [True]
        assert received[0]["type"] == "hello_ack"

        with qtbot.waitSignal(bridge_server.connection_status_changed, timeout=2000) as blocker_disc:
            client_socket.close()

        assert blocker_disc.args == [False]
