"""UI regression tests for the active extension-backed desktop workflow."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
)

from shopee_image_downloader.app import create_application
from shopee_image_downloader.core.batch_queue import (
    QueueState,
    STATUS_DISPLAY_CANCELLED,
    STATUS_DISPLAY_SCANNING,
    STATUS_DISPLAY_SUCCESS,
    STATUS_DISPLAY_VERIFICATION,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.ui.main_window import MainWindow
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _create_window(
    tmp_path: Path,
    *,
    connected: bool = False,
    with_output_folder: bool = False,
) -> tuple[MainWindow, MagicMock, SettingsManager]:
    create_application([])
    settings = SettingsManager(config_path=tmp_path / "settings.json")
    if with_output_folder:
        output_dir = tmp_path / "output"
        output_dir.mkdir(exist_ok=True)
        settings.set_output_folder(output_dir)

    bridge = MagicMock(spec=ExtensionBridgeServer)
    bridge.has_connected_clients = connected
    window = MainWindow(
        settings_manager=settings,
        bridge_server=bridge,
        start_bridge=False,
    )
    return window, bridge, settings


def _product(
    *,
    request_id: str | None = None,
    shop_id: str = "1001",
    item_id: str = "2001",
    name: str = "Bàn phím cơ không dây",
    image_count: int = 2,
) -> BridgeProductData:
    return BridgeProductData(
        url=f"https://shopee.vn/product-i.{shop_id}.{item_id}",
        product_name=name,
        shop_id=shop_id,
        item_id=item_id,
        images=[f"https://example.com/{item_id}-{index}.jpg" for index in range(image_count)],
        image_count=image_count,
        request_id=request_id,
    )


def test_main_window_ui_components(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path)

    assert window.windowTitle() == "Shopee Image Downloader"
    assert isinstance(window.bridge_title_label, QLabel)
    assert window.bridge_title_label.text() == "Chrome Extension:"
    assert window.bridge_status_label.text() == "🔴 Chưa kết nối"
    assert isinstance(window.url_input, QPlainTextEdit)
    assert window.url_input.placeholderText() == "Dán mỗi link Shopee trên một dòng..."
    assert isinstance(window.output_folder_input, QLineEdit)
    assert window.output_folder_input.isReadOnly()
    assert isinstance(window.select_folder_button, QPushButton)
    assert window.select_folder_button.text() == "Chọn thư mục"
    assert window.start_button.text() == "Bắt đầu tải ảnh"
    assert isinstance(window.progress_bar, QProgressBar)
    assert window.progress_bar.value() == 0
    assert isinstance(window.results_table, QTableWidget)
    assert [
        window.results_table.horizontalHeaderItem(index).text()
        for index in range(window.results_table.columnCount())
    ] == ["STT", "Sản phẩm / Link", "Trạng thái", "Số ảnh"]

    window.close()


def test_main_window_bridge_guard_when_disconnected(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path, with_output_folder=True)
    window.url_input.setPlainText("https://shopee.vn/product-1")

    window.start_button.click()

    assert window.status_label.text() == "Chrome Extension chưa kết nối."
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 2).text() == "Đang chờ"
    window.close()


def test_main_window_folder_selection_and_cancel(tmp_path: Path) -> None:
    window, _, settings = _create_window(tmp_path)
    chosen_dir = tmp_path / "downloads"
    chosen_dir.mkdir()

    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(chosen_dir)):
        window.select_folder_button.click()

    assert window.output_folder_input.text() == str(chosen_dir)
    assert settings.get_output_folder() == str(chosen_dir)

    with patch.object(QFileDialog, "getExistingDirectory", return_value=""):
        window.select_folder_button.click()

    assert window.output_folder_input.text() == str(chosen_dir)
    window.close()


def test_main_window_folder_restoration_existing_vs_missing(tmp_path: Path) -> None:
    create_application([])
    existing = tmp_path / "existing"
    existing.mkdir()
    existing_settings = SettingsManager(config_path=tmp_path / "existing.json")
    existing_settings.set_output_folder(existing)
    existing_window = MainWindow(settings_manager=existing_settings, start_bridge=False)
    assert existing_window.output_folder_input.text() == str(existing)
    existing_window.close()

    missing_settings = SettingsManager(config_path=tmp_path / "missing.json")
    missing_settings.set_output_folder(tmp_path / "missing")
    missing_window = MainWindow(settings_manager=missing_settings, start_bridge=False)
    assert missing_window.output_folder_input.text() == ""
    missing_window.close()


def test_main_window_requires_existing_output_folder(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path)
    window.url_input.setPlainText("https://shopee.vn/product-1")

    window.start_button.click()
    assert window.status_label.text() == "Vui lòng chọn thư mục lưu ảnh."
    assert window.results_table.rowCount() == 0

    window.output_folder_input.setText(str(tmp_path / "does-not-exist"))
    window.start_button.click()
    assert window.status_label.text() == "Vui lòng chọn thư mục lưu ảnh."
    assert window.results_table.rowCount() == 0
    window.close()


def test_main_window_empty_and_invalid_input(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path, connected=True, with_output_folder=True)

    window.url_input.setPlainText("   \n\n")
    window.start_button.click()
    assert window.status_label.text() == "Chưa nhập link"

    window.url_input.setPlainText("https://google.com\nhttps://lazada.vn")
    window.start_button.click()
    assert window.results_table.rowCount() == 2
    assert window.results_table.item(0, 2).text() == "Link không hợp lệ"
    assert window.results_table.item(1, 2).text() == "Link không hợp lệ"
    assert window.status_label.text() == "Đã nhận 0 link hợp lệ"
    window.close()


def test_main_window_batch_queue_ui_flow(tmp_path: Path, qtbot) -> None:
    window, bridge, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    qtbot.addWidget(window)
    sent_messages: list[str] = []
    bridge.send_message.side_effect = lambda message: sent_messages.append(message)
    window.url_input.setPlainText(
        "https://shopee.vn/product-1\n"
        "https://s.shopee.vn/short-2\n"
        "https://shopee.vn/product-1\n"
        "https://lazada.vn/invalid"
    )

    window.start_button.click()

    assert window.results_table.rowCount() == 3
    assert window.start_button.text() == "Hủy"
    assert len(sent_messages) == 1
    first_open = json.loads(sent_messages[0])
    assert first_open["type"] == "open_product"
    assert "process_url" not in sent_messages[0]

    first_request = window.queue_manager.current_item.request_id
    window._on_bridge_process_progress_received(first_request, "scanning_gallery")
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_SCANNING

    update_calls: list[tuple[int, BridgeProductData]] = []
    original_update = window._update_table_row

    def record_update(row: int, data: BridgeProductData, status_text: str = STATUS_DISPLAY_SUCCESS) -> None:
        update_calls.append((row, data))
        original_update(row, data, status_text)

    window._update_table_row = record_update
    window._on_bridge_product_received(
        _product(request_id=first_request, item_id="222", name="Sản phẩm 1")
    )
    assert len(update_calls) == 1
    assert len(sent_messages) == 2

    second_request = window.queue_manager.current_item.request_id
    window._on_bridge_product_received(
        _product(
            request_id=second_request,
            item_id="444",
            name="Sản phẩm 2",
            image_count=1,
        )
    )

    assert window.results_table.item(0, 1).text() == "Sản phẩm 1"
    assert window.results_table.item(1, 1).text() == "Sản phẩm 2"
    assert window.status_label.text() == "Hoàn tất: 2 thành công, 0 lỗi"
    assert window.progress_bar.value() == 100
    assert window.start_button.text() == "Bắt đầu tải ảnh"
    window.close()


def test_main_window_batch_verification_resume_and_cancel(tmp_path: Path, qtbot) -> None:
    window, bridge, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    qtbot.addWidget(window)
    sent_messages: list[str] = []
    bridge.send_message.side_effect = lambda message: sent_messages.append(message)
    window.url_input.setPlainText("https://shopee.vn/product-verify")
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id

    window._on_bridge_process_error_received(
        request_id,
        "https://shopee.vn/product-verify",
        "VERIFICATION_REQUIRED",
        "Shopee yêu cầu xác minh",
    )

    assert window.queue_manager.state == QueueState.PAUSED_VERIFICATION
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_VERIFICATION
    assert window.start_button.text() == "Tiếp tục"

    window.start_button.click()
    assert window.queue_manager.state == QueueState.RUNNING
    assert len(sent_messages) == 2

    window.start_button.click()
    assert window.queue_manager.state == QueueState.IDLE
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_CANCELLED
    assert json.loads(sent_messages[-1])["type"] == "batch_finished"
    window.close()


def test_main_window_bridge_ui_status_transitions(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path)
    window._on_bridge_status_changed(True)
    assert window.bridge_status_label.text() == "🟢 Đã kết nối"
    window._on_bridge_status_changed(False)
    assert window.bridge_status_label.text() == "🔴 Mất kết nối"
    window.close()


def test_manual_product_reception_deduplicates_by_product_key(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path, with_output_folder=True)
    window._on_bridge_product_received(_product(name="Product v1", image_count=1))
    window._on_bridge_product_received(_product(name="Product v2", image_count=3))
    window._on_bridge_product_received(
        _product(item_id="2002", name="Different product", image_count=1)
    )

    assert window.results_table.rowCount() == 2
    assert window.results_table.item(0, 1).text() == "Product v2"
    assert window.results_table.item(0, 3).text() == "3"
    assert window.results_table.item(1, 1).text() == "Different product"
    window.close()


def test_batch_preserves_authoritative_nine_image_result(tmp_path: Path) -> None:
    """Folder creation must preserve the known authoritative nine-image result."""
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    window.url_input.setPlainText("https://shopee.vn/product-i.78513158.28469164720")
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id

    window._on_bridge_product_received(
        _product(
            request_id=request_id,
            shop_id="78513158",
            item_id="28469164720",
            name="Known regression product",
            image_count=9,
        )
    )

    stored = window._products_by_product_key["78513158:28469164720"]
    assert window.results_table.item(0, 3).text() == "9"
    assert len(stored.images) == 9
    assert window.status_label.text() == "Hoàn tất: 1 thành công, 0 lỗi"
    window.close()


def test_batch_row_and_subsequent_manual_send_share_one_row(tmp_path: Path) -> None:
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    window.url_input.setPlainText("https://shopee.vn/product-i.1001.2001")
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id
    window._on_bridge_product_received(
        _product(request_id=request_id, name="Batch result", image_count=4)
    )
    window._on_bridge_product_received(
        _product(request_id=None, name="Manual result", image_count=9)
    )

    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == "Manual result"
    assert window.results_table.item(0, 3).text() == "9"
    window.close()


def test_product_success_creates_empty_folder_and_stores_path(tmp_path: Path) -> None:
    """007A integrates after authoritative data without downloading images."""
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    window.url_input.setPlainText(
        "https://shopee.vn/product-i.78513158.28469164720"
    )
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id
    product = _product(
        request_id=request_id,
        shop_id="78513158",
        item_id="28469164720",
        name="Túi đựng đồ du lịch CSHome",
        image_count=9,
    )

    window._on_bridge_product_received(product)

    stored = window._products_by_product_key[product.product_key]
    assert stored.product_folder == tmp_path / "output" / product.product_name
    assert stored.product_folder.is_dir()
    assert list(stored.product_folder.iterdir()) == []
    assert len(stored.images) == 9
    assert stored.images == product.images
    window.close()


def test_folder_failure_marks_batch_item_failed(tmp_path: Path) -> None:
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    window.url_input.setPlainText("https://shopee.vn/product-i.1001.2001")
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id
    window.output_folder_input.setText(str(tmp_path / "missing"))

    window._on_bridge_product_received(_product(request_id=request_id))

    assert window.results_table.item(0, 2).text() == "Không thể tạo thư mục sản phẩm."
    assert window.status_label.text() == "Hoàn tất: 0 thành công, 1 lỗi"
    window.close()


def test_folder_failure_does_not_corrupt_next_queue_item(tmp_path: Path) -> None:
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    window.url_input.setPlainText(
        "https://shopee.vn/product-i.1001.2001\n"
        "https://shopee.vn/product-i.1002.2002"
    )
    window.start_button.click()
    first_request_id = window.queue_manager.current_item.request_id
    valid_output = window.output_folder_input.text()
    window.output_folder_input.setText(str(tmp_path / "missing"))

    window._on_bridge_product_received(
        _product(request_id=first_request_id, shop_id="1001", item_id="2001")
    )

    second_request_id = window.queue_manager.current_item.request_id
    window.output_folder_input.setText(valid_output)
    window._on_bridge_product_received(
        _product(request_id=second_request_id, shop_id="1002", item_id="2002")
    )

    stored = window._products_by_product_key["1002:2002"]
    assert stored.product_folder is not None
    assert stored.product_folder.is_dir()
    assert window.status_label.text() == "Hoàn tất: 1 thành công, 1 lỗi"
    window.close()
