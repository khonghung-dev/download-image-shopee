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
    window = MainWindow(settings_manager=settings, session_manager=session_manager)

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


def test_main_window_auth_guard_when_unauthenticated(tmp_path: Path) -> None:
    """Verify start button halts and shows warning if Shopee session is not logged in."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_session = _create_mock_session_manager(status=STATUS_NOT_LOGGED_IN)
    window = MainWindow(settings_manager=settings, session_manager=mock_session)

    window.url_input.setPlainText("https://shopee.vn/product-1")
    window.start_button.click()

    assert window.status_label.text() == "Vui lòng đăng nhập Shopee trước."
    assert window.results_table.rowCount() == 0
    assert window._worker is None

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


def test_main_window_metadata_extraction_ui_flow(tmp_path: Path) -> None:
    """Verify clicking start button with valid folder & auth triggers worker and replaces raw URL with product name."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_session = _create_mock_session_manager(status=STATUS_LOGGED_IN)

    mock_extractor = MagicMock(spec=ShopeeMetadataExtractor)
    mock_extractor.extract.side_effect = [
        ProductMetadata(
            product_name="Áo Thun Nam Cotton 100%",
            shop_id="111",
            item_id="222",
            final_url="https://shopee.vn/Ao-Thun-Nam-i.111.222",
        ),
        ProductMetadata(
            product_name="Củ Sạc Anker GaN 30W",
            shop_id="333",
            item_id="444",
            final_url="https://shopee.vn/Cu-Sac-Anker-i.333.444",
        ),
    ]

    window = MainWindow(
        settings_manager=settings,
        session_manager=mock_session,
        extractor=mock_extractor,
    )

    sample_input = """
    https://shopee.vn/product-1
    https://s.shopee.vn/short-2
    https://shopee.vn/product-1
    https://lazada.vn/other-3
    """

    window.url_input.setPlainText(sample_input)
    window.start_button.click()

    # Wait for worker thread to finish
    if window._worker:
        window._worker.wait(3000)
    app.processEvents()

    # Should have 3 rows after deduplication (2 valid, 1 invalid)
    assert window.results_table.rowCount() == 3

    # Row 1: Valid Shopee URL -> Replaced with actual product name, status "Đã lấy thông tin"
    assert window.results_table.item(0, 0).text() == "1"
    assert window.results_table.item(0, 1).text() == "Áo Thun Nam Cotton 100%"
    assert window.results_table.item(0, 2).text() == STATUS_COMPLETED
    assert window.results_table.item(0, 3).text() == "-"

    # Row 2: Valid Shortened Shopee URL -> Replaced with actual product name, status "Đã lấy thông tin"
    assert window.results_table.item(1, 0).text() == "2"
    assert window.results_table.item(1, 1).text() == "Củ Sạc Anker GaN 30W"
    assert window.results_table.item(1, 2).text() == STATUS_COMPLETED
    assert window.results_table.item(1, 3).text() == "-"

    # Row 3: Invalid Non-Shopee URL -> Kept invalid
    assert window.results_table.item(2, 0).text() == "3"
    assert window.results_table.item(2, 1).text() == "https://lazada.vn/other-3"
    assert window.results_table.item(2, 2).text() == "Link không hợp lệ"
    assert window.results_table.item(2, 3).text() == "-"

    # Status label should show extraction summary
    assert window.status_label.text() == "Đã lấy thông tin 2/2 sản phẩm"
    assert window.progress_bar.value() == 100
    assert window.start_button.isEnabled() is True

    window.close()


def test_main_window_metadata_extraction_failure_and_verification_flow(tmp_path: Path) -> None:
    """Verify table displays failed status when product is not found or verification is required."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_session = _create_mock_session_manager(status=STATUS_LOGGED_IN)

    mock_extractor = MagicMock(spec=ShopeeMetadataExtractor)
    mock_extractor.extract.side_effect = [
        ProductMetadata(
            final_url="https://shopee.vn/fake-product",
            error=ERROR_PRODUCT_NOT_FOUND,
        ),
        ProductMetadata(
            final_url="https://shopee.vn/verify-product",
            error=ERROR_VERIFICATION_REQUIRED,
        ),
    ]

    window = MainWindow(
        settings_manager=settings,
        session_manager=mock_session,
        extractor=mock_extractor,
    )
    window.url_input.setPlainText("https://shopee.vn/fake-product\nhttps://shopee.vn/verify-product")
    window.start_button.click()

    if window._worker:
        window._worker.wait(3000)
    app.processEvents()

    assert window.results_table.rowCount() == 2
    # Row 1: Product not found
    assert window.results_table.item(0, 2).text() == ERROR_PRODUCT_NOT_FOUND
    assert window.results_table.item(0, 2).toolTip() == ERROR_PRODUCT_NOT_FOUND

    # Row 2: Verification required
    assert window.results_table.item(1, 2).text() == ERROR_VERIFICATION_REQUIRED
    assert window.results_table.item(1, 2).toolTip() == ERROR_VERIFICATION_REQUIRED

    assert window.status_label.text() == "Đã lấy thông tin 0/2 sản phẩm"

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


def test_main_window_manual_login_status_transition(tmp_path: Path) -> None:
    """Verify table row transitions through 'Cần đăng nhập Shopee' and completes with product name."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    assert app is not None

    valid_dir = tmp_path / "output_dir"
    valid_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings = SettingsManager(config_path=settings_file)
    settings.set_output_folder(valid_dir)

    mock_session = _create_mock_session_manager(status=STATUS_LOGGED_IN)

    def mock_extract(url: str, page=None, on_status_change=None) -> ProductMetadata:
        if on_status_change:
            on_status_change("Cần đăng nhập Shopee")
            on_status_change("Đang lấy thông tin")
        return ProductMetadata(
            product_name="Tai Nghe Bluetooth Pro",
            shop_id="111",
            item_id="222",
            final_url=url,
        )

    mock_extractor = MagicMock(spec=ShopeeMetadataExtractor)
    mock_extractor.extract.side_effect = mock_extract

    window = MainWindow(
        settings_manager=settings,
        session_manager=mock_session,
        extractor=mock_extractor,
    )
    window.url_input.setPlainText("https://shopee.vn/product-1")
    window.start_button.click()

    if window._worker:
        window._worker.wait(3000)
    app.processEvents()

    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == "Tai Nghe Bluetooth Pro"
    assert window.results_table.item(0, 2).text() == STATUS_COMPLETED
    assert window.status_label.text() == "Đã lấy thông tin 1/1 sản phẩm"

    window.close()
