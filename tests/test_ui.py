"""UI tests for MainWindow components, layouts, folder selection, auth section, and metadata extraction."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
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
    BatchQueueManager,
    ItemState,
    QueueState,
    STATUS_DISPLAY_CANCELLED,
    STATUS_DISPLAY_FAILED,
    STATUS_DISPLAY_NAVIGATING,
    STATUS_DISPLAY_NOT_FOUND,
    STATUS_DISPLAY_SCANNING,
    STATUS_DISPLAY_SUCCESS,
    STATUS_DISPLAY_TIMEOUT,
    STATUS_DISPLAY_VERIFICATION,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.browser_session import (
    STATUS_CHECKING_SESSION,
    STATUS_LOGGED_IN,
    STATUS_LOGIN_REQUIRED,
    STATUS_LOGIN_VERIFY,
    STATUS_NOT_LOGGED_IN,
    STATUS_OPENING_CHROME,
    STATUS_SESSION_EXPIRED,
    STATUS_VERIFICATION_REQUIRED,
    STATUS_WAITING_FOR_LOGIN,
    ShopeeSessionManager,
)
from shopee_image_downloader.core.metadata_extractor import (
    ERROR_PRODUCT_NOT_FOUND,
    ERROR_VERIFICATION_REQUIRED,
    ProductMetadata,
    ShopeeMetadataExtractor,
)
from shopee_image_downloader.core.url_resolver import ResolvedUrl, ShopeeUrlResolver
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.ui.main_window import (
    STATUS_COMPLETED,
    STATUS_EXTRACTING,
    STATUS_FAILED,
    STATUS_RESOLVING,
    MainWindow,
)
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer



def _create_mock_session_manager(status: str = STATUS_LOGGED_IN, username: str | None = None) -> ShopeeSessionManager:
    """Helper to construct a mock ShopeeSessionManager returning a fixed status."""
    manager = MagicMock(spec=ShopeeSessionManager)
    manager.get_session_status.return_value = status
    manager.is_logged_in.return_value = (status == STATUS_LOGGED_IN)
    manager.get_authenticated_username.return_value = username
    manager.start_context.return_value = MagicMock()
    return manager


def test_main_window_ui_components(tmp_path: Path) -> None:
    """Verify that all required UI elements including Shopee Account section exist."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    session_manager = ShopeeSessionManager(profile_dir=tmp_path / "empty_profile")
    window = MainWindow(settings_manager=settings, session_manager=session_manager, start_bridge=False)

    # 1. Window Title
    assert window.windowTitle() == "Shopee Image Downloader"

    # 2. Shopee Account Section
    assert isinstance(window.auth_title_label, QLabel)
    assert window.auth_title_label.text() == "Tài khoản Shopee:"
    assert isinstance(window.auth_status_label, QLabel)
    assert window.auth_status_label.text() == STATUS_NOT_LOGGED_IN
    assert isinstance(window.login_button, QPushButton)
    assert window.login_button.text() == "Đăng nhập Shopee"
    assert isinstance(window.complete_login_button, QPushButton)
    assert window.complete_login_button.text() == "Hoàn tất đăng nhập"
    assert window.complete_login_button.isEnabled() is False
    assert isinstance(window.logout_button, QPushButton)
    assert window.logout_button.text() == "Đăng xuất"
    assert window.logout_button.isEnabled() is False

    # 3. URL Input Section
    assert isinstance(window.url_label, QLabel)
    assert window.url_label.text() == "Link sản phẩm Shopee"
    assert isinstance(window.url_input, QPlainTextEdit)
    assert window.url_input.placeholderText() == "Dán mỗi link Shopee trên một dòng..."

    # 4. Output Folder Field & Button
    assert isinstance(window.output_folder_input, QLineEdit)
    assert window.output_folder_input.isReadOnly() is True
    assert window.output_folder_input.text() == ""
    assert isinstance(window.select_folder_button, QPushButton)
    assert window.select_folder_button.text() == "Chọn thư mục"

    # 5. Action Button
    assert isinstance(window.start_button, QPushButton)
    assert window.start_button.text() == "Bắt đầu tải ảnh"

    # 6. Progress Bar & Status Label
    assert isinstance(window.progress_bar, QProgressBar)
    assert window.progress_bar.value() == 0
    assert isinstance(window.status_label, QLabel)
    assert window.status_label.text() == "Sẵn sàng"

    # 7. Results Table
    assert isinstance(window.results_table, QTableWidget)
    assert window.results_table.columnCount() == 4
    expected_headers = ["STT", "Sản phẩm / Link", "Trạng thái", "Số ảnh"]
    actual_headers = [
        window.results_table.horizontalHeaderItem(i).text()
        for i in range(window.results_table.columnCount())
    ]
    assert actual_headers == expected_headers

    # 8. Resize behavior
    window.resize(1024, 768)
    assert window.width() == 1024
    assert window.height() == 768

    window.close()


def test_main_window_bridge_guard_when_disconnected(tmp_path: Path) -> None:
    """Verify start button halts and shows warning if Chrome Extension bridge is not connected."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    mock_server.has_connected_clients = False

    window = MainWindow(settings_manager=settings, bridge_server=mock_server, start_bridge=False)

    window.url_input.setPlainText("https://shopee.vn/product-1")
    window.start_button.click()

    assert window.status_label.text() == "Chrome Extension chưa kết nối."
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 2).text() == "Đang chờ"

    window.close()


def test_main_window_login_button_opens_browser_and_enables_complete(tmp_path: Path) -> None:
    """Verify clicking login button triggers auth worker and enables complete_login_button."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_session = MagicMock(spec=ShopeeSessionManager)
    mock_session.get_session_status.return_value = STATUS_NOT_LOGGED_IN
    mock_session.open_auth_browser.return_value = True

    window = MainWindow(session_manager=mock_session)
    assert window.auth_status_label.text() == STATUS_NOT_LOGGED_IN

    # Click login button
    window.login_button.click()
    app.processEvents()

    assert window.complete_login_button.isEnabled() is True
    assert window.login_button.isEnabled() is False
    assert window.auth_status_label.text() == STATUS_WAITING_FOR_LOGIN

    if window._auth_worker:
        window._auth_worker.cancel()
        window._auth_worker.wait(1000)

    window.close()


def test_main_window_complete_login_success(tmp_path: Path) -> None:
    """Verify clicking 'Hoàn tất đăng nhập' validates session and updates status to username."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_session = MagicMock(spec=ShopeeSessionManager)
    mock_session.get_session_status.return_value = STATUS_NOT_LOGGED_IN
    mock_session.validate_and_finalize_session.return_value = (True, "chuasudung4526", "Đã đăng nhập Shopee thành công")

    window = MainWindow(session_manager=mock_session)
    window.complete_login_button.setEnabled(True)

    # Click complete login button
    window.complete_login_button.click()
    app.processEvents()

    mock_session.validate_and_finalize_session.assert_called_once()
    assert window.auth_status_label.text() == "chuasudung4526"
    assert window.logout_button.isEnabled() is True
    assert window.complete_login_button.isEnabled() is False
    assert window.status_label.text() == "Đã đăng nhập Shopee thành công"

    window.close()


def test_main_window_complete_login_failure(tmp_path: Path) -> None:
    """Verify clicking 'Hoàn tất đăng nhập' with invalid session displays notice and retains complete button."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_session = MagicMock(spec=ShopeeSessionManager)
    mock_session.get_session_status.return_value = STATUS_NOT_LOGGED_IN
    mock_session.validate_and_finalize_session.return_value = (
        False,
        "",
        "Chưa hoàn tất đăng nhập Shopee (thiếu cookie xác thực). Vui lòng hoàn tất trên trình duyệt rồi nhấn 'Hoàn tất đăng nhập'.",
    )

    window = MainWindow(session_manager=mock_session)
    window.complete_login_button.setEnabled(True)

    window.complete_login_button.click()
    app.processEvents()

    assert window.auth_status_label.text() == STATUS_SESSION_EXPIRED
    assert window.complete_login_button.isEnabled() is True
    assert "Chưa hoàn tất đăng nhập" in window.status_label.text()

    window.close()


def test_main_window_verification_state_display(tmp_path: Path) -> None:
    """Verify verification status update displays Shopee đang yêu cầu xác minh."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_session = MagicMock(spec=ShopeeSessionManager)
    mock_session.get_session_status.return_value = STATUS_NOT_LOGGED_IN

    window = MainWindow(session_manager=mock_session)
    window._on_auth_status_updated(STATUS_LOGIN_VERIFY)
    app.processEvents()

    assert window.auth_status_label.text() == STATUS_VERIFICATION_REQUIRED
    assert window.status_label.text() == STATUS_LOGIN_VERIFY

    window.close()


def test_main_window_logout_flow(tmp_path: Path) -> None:
    """Verify clicking logout button clears session and resets status to Chưa đăng nhập."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_session = MagicMock(spec=ShopeeSessionManager)
    mock_session.get_session_status.side_effect = [STATUS_LOGGED_IN, STATUS_NOT_LOGGED_IN]
    mock_session.get_authenticated_username.return_value = "chuasudung4526"

    window = MainWindow(session_manager=mock_session)
    assert window.auth_status_label.text() == "chuasudung4526"
    assert window.logout_button.isEnabled() is True

    # Click logout
    window.logout_button.click()

    mock_session.logout.assert_called_once()
    assert window.auth_status_label.text() == STATUS_NOT_LOGGED_IN
    assert window.logout_button.isEnabled() is False
    assert window.complete_login_button.isEnabled() is False
    assert window.status_label.text() == "Đã đăng xuất Shopee"

    window.close()


def test_main_window_startup_session_restoration(tmp_path: Path) -> None:
    """Verify startup restores authenticated state with username if session is valid."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_session = _create_mock_session_manager(status=STATUS_LOGGED_IN)
    mock_session.get_authenticated_username.return_value = "chuasudung4526"
    window = MainWindow(session_manager=mock_session)

    assert window.auth_status_label.text() == "chuasudung4526"
    assert window.logout_button.isEnabled() is True

    window.close()


def test_main_window_folder_selection(tmp_path: Path) -> None:
    """Verify selecting a folder updates the line edit and persists to settings."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    window = MainWindow(settings_manager=settings)

    chosen_dir = tmp_path / "my_downloads"
    chosen_dir.mkdir()

    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(chosen_dir)):
        window.select_folder_button.click()

    assert window.output_folder_input.text() == str(chosen_dir)
    assert settings.get_output_folder() == str(chosen_dir)

    window.close()


def test_main_window_folder_selection_cancel(tmp_path: Path) -> None:
    """Verify cancelling the folder dialog does not overwrite existing path."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    existing_dir = tmp_path / "first_folder"
    existing_dir.mkdir()
    settings.set_output_folder(existing_dir)

    window = MainWindow(settings_manager=settings)
    assert window.output_folder_input.text() == str(existing_dir)

    with patch.object(QFileDialog, "getExistingDirectory", return_value=""):
        window.select_folder_button.click()

    assert window.output_folder_input.text() == str(existing_dir)
    assert settings.get_output_folder() == str(existing_dir)

    window.close()


def test_main_window_folder_restoration_existing_vs_missing(tmp_path: Path) -> None:
    """Verify saved folder is restored if it exists, and ignored if it does not."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    # Case 1: Folder exists -> restored
    existing_dir = tmp_path / "persisted_dir"
    existing_dir.mkdir()
    settings_file = tmp_path / "settings_1.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(existing_dir)

    window1 = MainWindow(settings_manager=settings)
    assert window1.output_folder_input.text() == str(existing_dir)
    window1.close()

    # Case 2: Folder was deleted/missing -> not restored
    missing_dir = tmp_path / "deleted_dir"
    settings_file_2 = tmp_path / "settings_2.json"
    settings_2 = SettingsManager(config_path=settings_file_2)
    settings_2.set_output_folder(missing_dir)

    window2 = MainWindow(settings_manager=settings_2)
    assert window2.output_folder_input.text() == ""
    window2.close()


def test_main_window_start_without_folder(tmp_path: Path) -> None:
    """Verify start button halts and shows warning if no output folder is selected."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    window = MainWindow(settings_manager=settings)

    window.url_input.setPlainText("https://shopee.vn/product-1")
    window.start_button.click()

    assert window.status_label.text() == "Vui lòng chọn thư mục lưu ảnh."
    assert window.results_table.rowCount() == 0

    window.close()


def test_main_window_start_with_invalid_folder_path(tmp_path: Path) -> None:
    """Verify start button halts if output folder path in input does not exist on disk."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    window = MainWindow(settings_manager=settings)

    non_existent = tmp_path / "does_not_exist"
    window.output_folder_input.setText(str(non_existent))
    window.url_input.setPlainText("https://shopee.vn/product-1")
    window.start_button.click()

    assert window.status_label.text() == "Vui lòng chọn thư mục lưu ảnh."
    assert window.results_table.rowCount() == 0

    window.close()


def test_main_window_batch_queue_ui_flow(tmp_path: Path, qtbot) -> None:
    """Verify clicking start button with connected bridge starts queue and updates table on progress and completion."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    mock_server.has_connected_clients = True

    sent_messages = []
    mock_server.send_message.side_effect = lambda msg: sent_messages.append(msg)

    window = MainWindow(
        settings_manager=settings,
        bridge_server=mock_server,
        start_bridge=False,
    )
    qtbot.addWidget(window)

    sample_input = """
    https://shopee.vn/product-1
    https://s.shopee.vn/short-2
    https://shopee.vn/product-1
    https://lazada.vn/other-3
    """

    window.url_input.setPlainText(sample_input)
    window.start_button.click()

    # Table initialized with 3 rows (2 valid, 1 invalid)
    assert window.results_table.rowCount() == 3
    assert window.start_button.text() == "Hủy"
    assert window.queue_manager.is_running is True

    # First item dispatched to bridge
    assert len(sent_messages) == 1
    req1 = window.queue_manager.current_item.request_id

    # Item 1 progress update
    window._on_bridge_process_progress_received(req1, "scanning_gallery")
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_SCANNING

    # Item 1 completed
    prod1 = BridgeProductData(
        url="https://shopee.vn/product-1",
        product_name="Áo Thun Nam Cotton 100%",
        shop_id="111",
        item_id="222",
        images=["https://img.com/1.jpg", "https://img.com/2.jpg"],
        request_id=req1,
    )
    window._on_bridge_product_received(prod1)

    assert window.results_table.item(0, 1).text() == "Áo Thun Nam Cotton 100%"
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_SUCCESS
    assert window.results_table.item(0, 3).text() == "2"

    # Item 2 dispatched
    assert len(sent_messages) == 2
    req2 = window.queue_manager.current_item.request_id

    # Item 2 completed
    prod2 = BridgeProductData(
        url="https://s.shopee.vn/short-2",
        product_name="Củ Sạc Anker GaN 30W",
        shop_id="333",
        item_id="444",
        images=["https://img.com/3.jpg"],
        request_id=req2,
    )
    window._on_bridge_product_received(prod2)

    assert window.results_table.item(1, 1).text() == "Củ Sạc Anker GaN 30W"
    assert window.results_table.item(1, 2).text() == STATUS_DISPLAY_SUCCESS
    assert window.results_table.item(1, 3).text() == "1"

    # Completed batch summary
    assert window.status_label.text() == "Hoàn tất: 2 thành công, 0 lỗi"
    assert window.progress_bar.value() == 100
    assert window.start_button.text() == "Bắt đầu tải ảnh"

    window.close()


def test_main_window_batch_verification_and_resume_ui_flow(tmp_path: Path, qtbot) -> None:
    """Verify verification challenge pauses queue and resume re-processes the item."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    mock_server.has_connected_clients = True

    sent_messages = []
    mock_server.send_message.side_effect = lambda msg: sent_messages.append(msg)

    window = MainWindow(
        settings_manager=settings,
        bridge_server=mock_server,
        start_bridge=False,
    )
    qtbot.addWidget(window)

    window.url_input.setPlainText("https://shopee.vn/product-verify")
    window.start_button.click()

    req1 = window.queue_manager.current_item.request_id

    # Emit verification error
    window._on_bridge_process_error_received(req1, "https://shopee.vn/product-verify", "VERIFICATION_REQUIRED", "Shopee yêu cầu xác minh")

    assert window.queue_manager.is_paused_for_verification is True
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_VERIFICATION
    assert window.start_button.text() == "Tiếp tục"
    assert "Shopee yêu cầu xác minh trên Chrome" in window.status_label.text()

    # User solves verification and clicks "Tiếp tục"
    window.start_button.click()

    assert window.queue_manager.is_running is True
    assert window.start_button.text() == "Hủy"
    assert len(sent_messages) == 2  # Re-dispatched

    # Complete after verification
    prod = BridgeProductData(
        url="https://shopee.vn/product-verify",
        product_name="Sản Phẩm Đã Xác Minh",
        shop_id="777",
        item_id="888",
        images=["https://img.com/v.jpg"],
        request_id=window.queue_manager.current_item.request_id,
    )
    window._on_bridge_product_received(prod)

    assert window.results_table.item(0, 1).text() == "Sản Phẩm Đã Xác Minh"
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_SUCCESS
    assert window.status_label.text() == "Hoàn tất: 1 thành công, 0 lỗi"

    window.close()


def test_main_window_batch_cancel_ui_flow(tmp_path: Path, qtbot) -> None:
    """Verify clicking cancel stops the queue and marks in-flight item as cancelled."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    mock_server.has_connected_clients = True

    window = MainWindow(
        settings_manager=settings,
        bridge_server=mock_server,
        start_bridge=False,
    )
    qtbot.addWidget(window)

    window.url_input.setPlainText("https://shopee.vn/item-1\nhttps://shopee.vn/item-2")
    window.start_button.click()

    assert window.start_button.text() == "Hủy"

    # Click cancel button
    window.start_button.click()

    assert window.queue_manager.state == QueueState.IDLE
    assert window.start_button.text() == "Bắt đầu tải ảnh"
    assert window.results_table.item(0, 2).text() == STATUS_DISPLAY_CANCELLED

    window.close()


def test_main_window_empty_input_flow(tmp_path: Path) -> None:
    """Verify handling when start button is clicked with valid folder and auth but empty input."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_session = _create_mock_session_manager(status=STATUS_LOGGED_IN)

    window = MainWindow(settings_manager=settings, session_manager=mock_session)
    window.url_input.setPlainText("   \n\n   ")
    window.start_button.click()

    assert window.results_table.rowCount() == 0
    assert window.status_label.text() == "Chưa nhập link"

    window.close()


def test_main_window_only_invalid_urls_flow(tmp_path: Path) -> None:
    """Verify handling when all input URLs are non-Shopee URLs."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_session = _create_mock_session_manager(status=STATUS_LOGGED_IN)

    window = MainWindow(settings_manager=settings, session_manager=mock_session)
    window.url_input.setPlainText("https://google.com\nhttps://lazada.vn")
    window.start_button.click()

    assert window.results_table.rowCount() == 2
    assert window.results_table.item(0, 2).text() == "Link không hợp lệ"
    assert window.results_table.item(1, 2).text() == "Link không hợp lệ"
    assert window.status_label.text() == "Đã nhận 0 link hợp lệ"

    window.close()


def test_main_window_bridge_ui_status_transitions(tmp_path: Path, qtbot) -> None:
    """Verify bridge status label transitions: Chưa kết nối -> Đã kết nối -> Mất kết nối."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    window = MainWindow(bridge_server=mock_server)
    qtbot.addWidget(window)

    assert hasattr(window, "bridge_title_label")
    assert hasattr(window, "bridge_status_label")
    assert window.bridge_title_label.text() == "Chrome Extension:"
    assert window.bridge_status_label.text() == "🔴 Chưa kết nối"

    # Simulate connection established
    window._on_bridge_status_changed(True)
    assert window.bridge_status_label.text() == "🟢 Đã kết nối"

    # Simulate disconnection after being connected
    window._on_bridge_status_changed(False)
    assert window.bridge_status_label.text() == "🔴 Mất kết nối"

    window.close()


def test_main_window_bridge_product_reception_and_deduplication(tmp_path: Path, qtbot) -> None:
    """Verify table row insertion and deduplication when receiving products from bridge."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    from shopee_image_downloader.core.bridge_protocol import BridgeProductData

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    window = MainWindow(bridge_server=mock_server)
    qtbot.addWidget(window)

    assert window.results_table.rowCount() == 0

    # 1. Receive product 1
    prod1 = BridgeProductData(
        url="https://shopee.vn/product-1",
        product_name="Bàn phím cơ không dây",
        shop_id="1001",
        item_id="2001",
        images=["https://example.com/img1.jpg", "https://example.com/img2.jpg"],
    )
    window._on_bridge_product_received(prod1)

    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 0).text() == "1"
    assert window.results_table.item(0, 1).text() == "Bàn phím cơ không dây"
    assert window.results_table.item(0, 2).text() == "Đã nhận từ Chrome"
    assert window.results_table.item(0, 3).text() == "2"
    assert "Đã nhận từ Chrome: Bàn phím cơ không dây" in window.status_label.text()

    # 2. Receive duplicate product 1 (updated name or count)
    prod1_updated = BridgeProductData(
        url="https://shopee.vn/product-1",
        product_name="Bàn phím cơ không dây RGB",
        shop_id="1001",
        item_id="2001",
        images=["https://example.com/img1.jpg", "https://example.com/img2.jpg", "https://example.com/img3.jpg"],
    )
    window._on_bridge_product_received(prod1_updated)

    # Should update existing row without adding new row
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == "Bàn phím cơ không dây RGB"
    assert window.results_table.item(0, 2).text() == "Đã nhận từ Chrome"
    assert window.results_table.item(0, 3).text() == "3"

    # 3. Receive product 2 with different item_id
    prod2 = BridgeProductData(
        url="https://shopee.vn/product-2",
        product_name="Chuột công thái học",
        shop_id="1001",
        item_id="2002",
        images=["https://example.com/mouse.jpg"],
    )
    window._on_bridge_product_received(prod2)

    assert window.results_table.rowCount() == 2
    assert window.results_table.item(1, 0).text() == "2"
    assert window.results_table.item(1, 1).text() == "Chuột công thái học"
    assert window.results_table.item(1, 2).text() == "Đã nhận từ Chrome"
    assert window.results_table.item(1, 3).text() == "1"

    window.close()


def test_main_window_table_updates_existing_row_from_4_to_9_images(tmp_path: Path, qtbot) -> None:
    """Regression test: Existing row has 4 images -> new COMPLETE result has 9 images -> table displays 9."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    window = MainWindow(bridge_server=mock_server)
    qtbot.addWidget(window)

    # 1. First reception (preliminary snapshot with 4 images)
    prod_4 = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Áo Thun Nam Cao Cấp",
        shop_id="78513158",
        item_id="28469164720",
        images=[f"https://img.com/{i}.jpg" for i in range(1, 5)],
        image_count=4,
    )
    window._on_bridge_product_received(prod_4)

    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == "Áo Thun Nam Cao Cấp"
    assert window.results_table.item(0, 3).text() == "4"

    # 2. Later reception (authoritative COMPLETE result with 9 images)
    prod_9 = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Áo Thun Nam Cao Cấp",
        shop_id="78513158",
        item_id="28469164720",
        images=[f"https://img.com/{i}.jpg" for i in range(1, 10)],
        image_count=9,
    )
    window._on_bridge_product_received(prod_9)

    # Row must update count to 9 without duplicating rows
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == "Áo Thun Nam Cao Cấp"
    assert window.results_table.item(0, 3).text() == "9"

    window.close()


def test_main_window_batch_queue_displays_9_authoritative_images(tmp_path: Path, qtbot) -> None:
    """Verify batch queue completion displays exact 9 images in results table."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "out"
    valid_dir.mkdir()
    settings = SettingsManager(config_path=tmp_path / "settings.json")
    settings.set_output_folder(valid_dir)

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    mock_server.has_connected_clients = True
    window = MainWindow(settings_manager=settings, bridge_server=mock_server, start_bridge=False)
    qtbot.addWidget(window)

    window.url_input.setPlainText("https://shopee.vn/product-i.78513158.28469164720")
    window.start_button.click()

    assert window.results_table.rowCount() == 1
    req_id = window.queue_manager.current_item.request_id

    prod_9 = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Áo Thun Nam Cao Cấp 100% Cotton",
        shop_id="78513158",
        item_id="28469164720",
        images=[f"https://img.com/{i}.jpg" for i in range(1, 10)],
        image_count=9,
        request_id=req_id,
    )
    window._on_bridge_product_received(prod_9)

    assert window.results_table.item(0, 1).text() == "Áo Thun Nam Cao Cấp 100% Cotton"
    assert window.results_table.item(0, 2).text() == "Đã lấy dữ liệu"
    assert window.results_table.item(0, 3).text() == "9"

    window.close()


def test_case_d_deduplication_batch_row_and_subsequent_manual_send(tmp_path: Path, qtbot) -> None:
    """Case D: Existing batch row (req=R1, product_key=P1) followed by manual send (req=None, product_key=P1) must result in EXACTLY ONE row."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "out"
    valid_dir.mkdir()
    settings = SettingsManager(config_path=tmp_path / "settings.json")
    settings.set_output_folder(valid_dir)

    mock_server = MagicMock(spec=ExtensionBridgeServer)
    mock_server.has_connected_clients = True
    window = MainWindow(settings_manager=settings, bridge_server=mock_server, start_bridge=False)
    qtbot.addWidget(window)

    window.url_input.setPlainText("https://shopee.vn/product-i.78513158.28469164720")
    window.start_button.click()

    assert window.results_table.rowCount() == 1
    req_id = window.queue_manager.current_item.request_id

    # 1. Complete batch item with 9 images
    prod_batch = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Áo Thun Nam Cao Cấp 100% Cotton",
        shop_id="78513158",
        item_id="28469164720",
        images=[f"https://img.com/{i}.jpg" for i in range(1, 10)],
        image_count=9,
        request_id=req_id,
    )
    window._on_bridge_product_received(prod_batch)

    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 3).text() == "9"

    # 2. Batch finishes
    assert not window.queue_manager.is_running

    # 3. Subsequent manual send for the EXACT same product listing with request_id = None
    prod_manual = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Áo Thun Nam Cao Cấp 100% Cotton (Updated)",
        shop_id="78513158",
        item_id="28469164720",
        images=[f"https://img.com/{i}.jpg" for i in range(1, 10)],
        image_count=9,
        request_id=None,
    )
    window._on_bridge_product_received(prod_manual)

    # Invariant: Must still be EXACTLY ONE row in the table, updated in place!
    assert window.results_table.rowCount() == 1, (
        f"Expected exactly 1 row, but found {window.results_table.rowCount()} (duplicate row defect)"
    )
    assert window.results_table.item(0, 1).text() == "Áo Thun Nam Cao Cấp 100% Cotton (Updated)"
    assert window.results_table.item(0, 3).text() == "9"

    window.close()



