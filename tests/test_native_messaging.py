"""Tests for the active Chrome Native Messaging bridge."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

# Add native_host and src to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
NATIVE_HOST_DIR = REPO_ROOT / "native_host"
SRC_DIR = REPO_ROOT / "src"

if str(NATIVE_HOST_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_HOST_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from host import NativeMessagingHost, MAX_MESSAGE_SIZE
from shopee_image_downloader.core.bridge_protocol import (
    BridgeProductData,
)
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer
from shopee_image_downloader.ui.main_window import MainWindow
from shopee_image_downloader.storage.settings import SettingsManager
from build_support.extension_identity import (
    extension_id_from_manifest,
    validate_native_manifest,
)


class SilentDownloadController(QObject):
    """No-network test double for a UI-only duplicate-row regression."""

    folder_ready = Signal(object)
    progress = Signal(object, int, int)
    finished = Signal(object, object)
    failed = Signal(object, str, str)
    cancelled = Signal(object)
    idle = Signal()

    @property
    def is_busy(self) -> bool:
        return False

    def start(self, product_data: BridgeProductData, output_root: str) -> bool:
        return True

    def cancel(self, request_id: str | None = None) -> bool:
        return False


class ChunkedBytesIO(io.BytesIO):
    """Custom stream that yields bytes in small chunks to simulate partial reads."""

    def __init__(self, initial_bytes: bytes = b"", chunk_size: int = 2) -> None:
        super().__init__(initial_bytes)
        self.chunk_size = chunk_size

    def read(self, size: int = -1) -> bytes:
        if size == -1 or size > self.chunk_size:
            return super().read(self.chunk_size)
        return super().read(size)


def test_native_framing_encode_and_decode() -> None:
    """Verify encoding and decoding 4-byte length prefixed native messaging JSON."""
    mock_stdout = io.BytesIO()
    host = NativeMessagingHost(stdout_stream=mock_stdout)
    test_data = {
        "protocol_version": 1,
        "type": "test_message",
        "nested": {"key": "value", "list": [1, 2, 3]},
    }

    success = host.send_native_message(test_data)
    assert success is True

    raw_bytes = mock_stdout.getvalue()
    assert len(raw_bytes) > 4

    # Verify length prefix (little endian uint32)
    length = struct.unpack("<I", raw_bytes[:4])[0]
    payload_bytes = raw_bytes[4:]
    assert len(payload_bytes) == length

    decoded = json.loads(payload_bytes.decode("utf-8"))
    assert decoded == test_data

    # Now verify read_native_message reads it back
    mock_stdin = io.BytesIO(raw_bytes)
    host_reader = NativeMessagingHost(stdin_stream=mock_stdin)

    read_back = host_reader.read_native_message()
    assert read_back == test_data


def test_partial_stdin_reads() -> None:
    """Verify host handles partial reads when stdin chunks arrive in fragments."""
    sample_payload = {
        "type": "product_result",
        "data": {
            "product_name": "Sản phẩm thử nghiệm",
            "shop_id": "123456",
            "item_id": "987654",
        },
    }
    payload_bytes = json.dumps(sample_payload, ensure_ascii=False).encode("utf-8")
    raw_message = struct.pack("<I", len(payload_bytes)) + payload_bytes

    # Deliver 1 byte at a time
    chunked_stdin = ChunkedBytesIO(raw_message, chunk_size=1)
    host = NativeMessagingHost(stdin_stream=chunked_stdin)

    result = host.read_native_message()
    assert result == sample_payload


def test_malformed_json_handling() -> None:
    """Verify malformed JSON payload from stdin is handled gracefully without crashing."""
    invalid_json_bytes = b"{invalid_json_without_quotes: 123"
    raw_message = struct.pack("<I", len(invalid_json_bytes)) + invalid_json_bytes

    mock_stdin = io.BytesIO(raw_message)
    host = NativeMessagingHost(stdin_stream=mock_stdin)

    result = host.read_native_message()
    assert result is not None
    assert result.get("type") == "error"
    assert "Invalid JSON payload" in result.get("error", "")


def test_oversize_message_rejection() -> None:
    """Verify messages exceeding MAX_MESSAGE_SIZE are safely rejected."""
    mock_stdout = io.BytesIO()
    host = NativeMessagingHost(stdout_stream=mock_stdout)

    # Outgoing rejection
    huge_data = {"huge": "a" * (MAX_MESSAGE_SIZE + 100)}
    assert host.send_native_message(huge_data) is False

    # Incoming rejection
    oversize_len = struct.pack("<I", MAX_MESSAGE_SIZE + 500)
    mock_stdin = io.BytesIO(oversize_len + b"x" * 100)
    host_reader = NativeMessagingHost(stdin_stream=mock_stdin)

    incoming = host_reader.read_native_message()
    assert incoming is not None
    assert incoming.get("type") == "error"
    assert "Message size exceeds limit" in incoming.get("error", "")


def test_allowed_extension_id_in_manifest(tmp_path: Path) -> None:
    """Derive the keyed ID and require the exact same Native Messaging origin."""
    extension_manifest_path = REPO_ROOT / "chrome_extension" / "manifest.json"
    extension_manifest = json.loads(extension_manifest_path.read_text(encoding="utf-8"))
    public_key = extension_manifest.get("key")
    assert isinstance(public_key, str) and public_key

    public_key_der = base64.b64decode(public_key, validate=True)
    first_128_bits_hex = hashlib.sha256(public_key_der).hexdigest()[:32]
    independently_derived_id = "".join(
        chr(ord("a") + int(nibble, 16)) for nibble in first_128_bits_hex
    )
    assert independently_derived_id == extension_id_from_manifest(extension_manifest_path)
    assert re.fullmatch(r"[a-p]{32}", independently_derived_id)

    copied_manifest = tmp_path / "unrelated-location" / "manifest.json"
    copied_manifest.parent.mkdir()
    copied_manifest.write_text(
        json.dumps(extension_manifest),
        encoding="utf-8",
    )
    assert extension_id_from_manifest(copied_manifest) == independently_derived_id

    template_path = NATIVE_HOST_DIR / "com.shopee_image_downloader.bridge.json.template"
    assert template_path.exists(), "Manifest template must exist"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    assert template.get("name") == "com.shopee_image_downloader.bridge"
    assert template.get("type") == "stdio"
    assert template.get("allowed_origins") == ["EXTENSION_ORIGIN_PLACEHOLDER"]

    generated_manifest_path = (
        NATIVE_HOST_DIR / "com.shopee_image_downloader.bridge.json"
    )
    assert validate_native_manifest(
        extension_manifest_path,
        generated_manifest_path,
    ) == independently_derived_id
    expected_origin = f"chrome-extension://{independently_derived_id}/"
    generated_manifest = json.loads(
        generated_manifest_path.read_text(encoding="utf-8-sig")
    )
    assert generated_manifest.get("allowed_origins") == [expected_origin]
    assert "*" not in expected_origin


def test_desktop_unavailable_handling() -> None:
    """Verify host returns clean bridge_status when PySide6 desktop is closed."""
    mock_stdout = io.BytesIO()
    # Use an unused port where no server is listening
    host = NativeMessagingHost(port=59999, stdout_stream=mock_stdout)

    host.handle_incoming_message({"type": "connect_desktop"})

    raw_output = mock_stdout.getvalue()
    assert len(raw_output) > 4
    length = struct.unpack("<I", raw_output[:4])[0]
    response = json.loads(raw_output[4 : 4 + length].decode("utf-8"))

    assert response["type"] == "bridge_status"
    assert response["desktop_connected"] is False
    assert "Shopee Image Downloader chưa được mở" in response["message"]


def test_desktop_available_handshake_and_product_relay(qtbot) -> None:
    """Verify native host connects to running ExtensionBridgeServer, performs handshake, and relays products."""
    server = ExtensionBridgeServer(port=8769)
    assert server.start_server() is True

    mock_stdout = io.BytesIO()
    host = NativeMessagingHost(port=8769, stdout_stream=mock_stdout)

    try:
        received_products: list[BridgeProductData] = []
        server.product_received.connect(received_products.append)

        # 1. Test connect_desktop handshake in thread to keep Qt event loop active
        t_connect = threading.Thread(target=lambda: host.handle_incoming_message({"type": "connect_desktop"}))
        t_connect.start()

        qtbot.waitUntil(lambda: len(mock_stdout.getvalue()) > 4, timeout=3000)
        t_connect.join(timeout=2.0)

        raw_output = mock_stdout.getvalue()
        assert len(raw_output) > 4
        length = struct.unpack("<I", raw_output[:4])[0]
        response = json.loads(raw_output[4 : 4 + length].decode("utf-8"))

        assert response["type"] == "bridge_status"
        assert response["desktop_connected"] is True

        # 2. Test product_result relay
        product_payload = {
            "type": "product_result",
            "protocol_version": 1,
            "data": {
                "url": "https://shopee.vn/product-test",
                "product_name": "Sản phẩm test Native Bridge",
                "shop_id": "112233",
                "item_id": "445566",
                "images": ["https://cf.shopee.vn/file/img1.jpg", "https://cf.shopee.vn/file/img2.jpg"],
            },
        }

        t_send = threading.Thread(target=lambda: host.handle_incoming_message(product_payload))
        t_send.start()

        qtbot.waitUntil(lambda: len(received_products) == 1, timeout=3000)
        t_send.join(timeout=2.0)

        assert len(received_products) == 1
        p = received_products[0]
        assert p.product_name == "Sản phẩm test Native Bridge"
        assert p.shop_id == "112233"
        assert p.item_id == "445566"
        assert len(p.images) == 2

    finally:
        server.stop_server()
        host.ws_client.close()


def test_duplicate_product_behavior_preserved(qtbot, tmp_path: Path) -> None:
    """Verify MainWindow updates row for matching shop_id:item_id and appends for new item_id."""
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    settings = SettingsManager(config_path=tmp_path / "settings.json")
    settings.set_output_folder(output_folder)
    window = MainWindow(
        settings_manager=settings,
        image_download_controller=SilentDownloadController(),
        start_bridge=False,
    )
    qtbot.addWidget(window)

    p1 = BridgeProductData(
        url="https://shopee.vn/p1",
        product_name="Product Alpha v1",
        shop_id="100",
        item_id="200",
        images=["https://img/1.jpg"],
    )
    p1_update = BridgeProductData(
        url="https://shopee.vn/p1",
        product_name="Product Alpha v2 (Updated)",
        shop_id="100",
        item_id="200",
        images=["https://img/1.jpg", "https://img/2.jpg"],
    )
    p2 = BridgeProductData(
        url="https://shopee.vn/p2",
        product_name="Product Beta",
        shop_id="100",
        item_id="300",
        images=["https://img/3.jpg"],
    )

    # Initial product
    window._on_bridge_product_received(p1)
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == "Product Alpha v1"
    assert window.results_table.item(0, 2).text() == "1"

    # Send updated version of same shop_id:item_id
    window._on_bridge_product_received(p1_update)
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == "Product Alpha v2 (Updated)"
    assert window.results_table.item(0, 2).text() == "2"

    # Send distinct product
    window._on_bridge_product_received(p2)
    assert window.results_table.rowCount() == 2
    assert window.results_table.item(1, 1).text() == "Product Beta"


def test_native_host_disconnect_and_eof() -> None:
    """Verify host terminates cleanly when stdin delivers EOF."""
    mock_stdin = io.BytesIO(b"")
    mock_stdout = io.BytesIO()
    host = NativeMessagingHost(port=59999, stdin_stream=mock_stdin, stdout_stream=mock_stdout)

    # run() must terminate without infinite loop
    host.run()
    assert host._running is True


def test_no_direct_websocket_in_active_extension_source() -> None:
    """Verify no active extension JavaScript file creates a direct WebSocket connection."""
    ext_dir = REPO_ROOT / "chrome_extension"
    js_files = list(ext_dir.glob("*.js"))
    assert len(js_files) > 0, "Extension JS files must exist"

    for js_file in js_files:
        content = js_file.read_text(encoding="utf-8")

        # Strip multi-line comments and single-line comments
        stripped = re.sub(r"/\*[\s\S]*?\*/", "", content)
        stripped = re.sub(r"//.*", "", stripped)

        # Check for active `new WebSocket(`
        match = re.search(r"new\s+WebSocket\s*\(", stripped)
        assert match is None, (
            f"Found direct WebSocket creation in active code of {js_file.name}: {match}"
        )


def test_registry_scripts_target_only_exact_hkcu_key() -> None:
    """Verify install_host.ps1 and uninstall_host.ps1 target ONLY the exact HKCU key and require no admin."""
    install_script = NATIVE_HOST_DIR / "install_host.ps1"
    uninstall_script = NATIVE_HOST_DIR / "uninstall_host.ps1"

    assert install_script.exists()
    assert uninstall_script.exists()

    install_content = install_script.read_text(encoding="utf-8")
    uninstall_content = uninstall_script.read_text(encoding="utf-8")

    expected_host_name = "com.shopee_image_downloader.bridge"
    expected_reg_path = f"HKCU:\\Software\\Google\\Chrome\\NativeMessagingHosts\\{expected_host_name}"

    for script_name, content in [
        ("install_host.ps1", install_content),
        ("uninstall_host.ps1", uninstall_content),
    ]:
        # Must target HKCU only
        assert "HKCU" in content, f"{script_name} must target HKCU"
        assert "HKLM" not in content, f"{script_name} must NOT target HKLM"
        assert "HKEY_LOCAL_MACHINE" not in content, f"{script_name} must NOT target HKEY_LOCAL_MACHINE"
        assert "HKCR" not in content, f"{script_name} must NOT target HKCR"
        assert "HKU" not in content, f"{script_name} must NOT target HKU"
        assert expected_host_name in content, f"{script_name} must target {expected_host_name}"


def test_extension_manifest_permissions() -> None:
    """Verify manifest.json includes nativeMessaging and avoids forbidden permissions."""
    manifest_path = REPO_ROOT / "chrome_extension" / "manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    permissions = manifest.get("permissions", [])

    assert "nativeMessaging" in permissions, "Manifest must include 'nativeMessaging' permission"

    forbidden = ["debugger", "cookies", "history", "<all_urls>"]
    for perm in forbidden:
        assert perm not in permissions, f"Permission '{perm}' is forbidden"

    host_perms = manifest.get("host_permissions", [])
    for perm in forbidden:
        assert perm not in host_perms, f"Host permission '{perm}' is forbidden"


def test_native_host_lossless_relay_9_and_30_images() -> None:
    """Verify NativeHost losslessly relays product_result with exact 9 images and 30 image large galleries."""
    from unittest.mock import MagicMock

    host = NativeMessagingHost()
    host.ws_client = MagicMock()
    host.ws_client.is_connected = True

    sent_ws_frames = []
    host.ws_client.send_text.side_effect = lambda txt: sent_ws_frames.append(txt)

    # 1. Test 9 images payload
    payload_9 = {
        "protocol_version": 1,
        "type": "product_result",
        "request_id": "req-009",
        "data": {
            "input_url": "https://shopee.vn/product-i.78513158.28469164720",
            "final_url": "https://shopee.vn/product-i.78513158.28469164720",
            "product_name": "Áo Thun Cotton",
            "shop_id": "78513158",
            "item_id": "28469164720",
            "images": [f"https://cf.shopee.vn/file/img_{i}.jpg" for i in range(1, 10)],
            "image_count": 9,
        }
    }
    host.handle_incoming_message(payload_9)
    assert len(sent_ws_frames) == 1
    relayed_9 = json.loads(sent_ws_frames[0])
    assert len(relayed_9["data"]["images"]) == 9
    assert relayed_9["data"]["image_count"] == 9
    assert relayed_9["data"]["shop_id"] == "78513158"
    assert relayed_9["data"]["item_id"] == "28469164720"

    # 2. Test 30 images large gallery payload (verifies no truncation on large payloads)
    payload_30 = {
        "protocol_version": 1,
        "type": "product_result",
        "request_id": "req-030",
        "data": {
            "input_url": "https://shopee.vn/product-i.78513158.99999999999",
            "final_url": "https://shopee.vn/product-i.78513158.99999999999",
            "product_name": "Bộ Sưu Tập Lớn 30 Ảnh",
            "shop_id": "78513158",
            "item_id": "99999999999",
            "images": [f"https://cf.shopee.vn/file/huge_gallery_img_{i:02d}.jpg" for i in range(1, 31)],
            "image_count": 30,
        }
    }
    host.handle_incoming_message(payload_30)
    assert len(sent_ws_frames) == 2
    relayed_30 = json.loads(sent_ws_frames[1])
    assert len(relayed_30["data"]["images"]) == 30
    assert relayed_30["data"]["image_count"] == 30
    assert relayed_30["data"]["images"][29] == "https://cf.shopee.vn/file/huge_gallery_img_30.jpg"
