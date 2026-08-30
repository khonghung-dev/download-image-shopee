"""Main window implementation for Shopee Image Downloader."""

from pathlib import Path
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from shopee_image_downloader.core.browser_session import (
    STATUS_CHECKING_SESSION,
    STATUS_LOGGED_IN,
    STATUS_LOGIN_GRACE,
    STATUS_LOGIN_REQUIRED,
    STATUS_LOGIN_TIMEOUT,
    STATUS_LOGIN_VERIFY,
    STATUS_LOGIN_VERIFY_TEMP_FAIL,
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
from shopee_image_downloader.core.url_validator import (
    STATUS_INVALID,
    STATUS_PENDING,
    parse_url_lines,
)
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.workers.auth_worker import AuthLoginWorker
from shopee_image_downloader.workers.metadata_worker import MetadataExtractorWorker

STATUS_RESOLVING: str = "Đang xử lý link"
STATUS_EXTRACTING: str = "Đang lấy thông tin"
STATUS_COMPLETED: str = "Đã lấy thông tin"
STATUS_FAILED: str = "Không thể xử lý link"


class MainWindow(QMainWindow):
    """The main application window for Shopee Image Downloader."""

    TABLE_HEADERS: list[str] = ["STT", "Sản phẩm / Link", "Trạng thái", "Số ảnh"]

    def __init__(
        self,
        parent: QWidget | None = None,
        settings_manager: SettingsManager | None = None,
        session_manager: ShopeeSessionManager | None = None,
        resolver: ShopeeUrlResolver | None = None,
        extractor: ShopeeMetadataExtractor | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Shopee Image Downloader")
        self.resize(850, 650)
        self.setMinimumSize(650, 500)
        self.settings_manager = settings_manager or SettingsManager()
        self.session_manager = session_manager or ShopeeSessionManager()
        self.resolver = resolver or ShopeeUrlResolver()
        self.extractor = extractor or ShopeeMetadataExtractor(
            resolver=self.resolver,
            session_manager=self.session_manager,
        )
        self._worker: MetadataExtractorWorker | None = None
        self._auth_worker: AuthLoginWorker | None = None

        self._init_ui()
        self._restore_settings()

    def _init_ui(self) -> None:
        """Initialize all UI widgets, layouts, account controls, and table columns."""
        central_widget = QWidget(self)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        # 1. Shopee Account Section
        account_frame = QFrame(central_widget)
        account_frame.setFrameShape(QFrame.Shape.StyledPanel)
        account_frame.setStyleSheet(
            "QFrame { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 4px; }"
        )
        account_layout = QHBoxLayout(account_frame)
        account_layout.setContentsMargins(8, 6, 8, 6)
        account_layout.setSpacing(10)

        self.auth_title_label = QLabel("Tài khoản Shopee:", account_frame)
        self.auth_title_label.setStyleSheet("font-weight: bold; font-size: 13px; border: none;")
        account_layout.addWidget(self.auth_title_label)

        self.auth_status_label = QLabel(STATUS_NOT_LOGGED_IN, account_frame)
        self.auth_status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #616161; border: none;")
        account_layout.addWidget(self.auth_status_label)

        account_layout.addStretch(1)

        self.login_button = QPushButton("Đăng nhập Shopee", account_frame)
        self.login_button.setStyleSheet("font-weight: bold; padding: 4px 12px;")
        self.login_button.clicked.connect(self.handle_login)
        account_layout.addWidget(self.login_button)

        self.complete_login_button = QPushButton("Hoàn tất đăng nhập", account_frame)
        self.complete_login_button.setStyleSheet("font-weight: bold; padding: 4px 12px; background-color: #e8f5e9; color: #2e7d32;")
        self.complete_login_button.setEnabled(False)
        self.complete_login_button.clicked.connect(self.handle_complete_login)
        account_layout.addWidget(self.complete_login_button)

        self.logout_button = QPushButton("Đăng xuất", account_frame)
        self.logout_button.setStyleSheet("padding: 4px 12px;")
        self.logout_button.clicked.connect(self.handle_logout)
        account_layout.addWidget(self.logout_button)

        root_layout.addWidget(account_frame)

        # 2. URL Input Section
        self.url_label = QLabel("Link sản phẩm Shopee", central_widget)
        self.url_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        root_layout.addWidget(self.url_label)

        self.url_input = QPlainTextEdit(central_widget)
        self.url_input.setPlaceholderText("Dán mỗi link Shopee trên một dòng...")
        root_layout.addWidget(self.url_input, stretch=3)

        # 3. Output Folder Selection Section
        folder_layout = QHBoxLayout()
        folder_layout.setSpacing(8)

        self.output_folder_input = QLineEdit(central_widget)
        self.output_folder_input.setReadOnly(True)
        self.output_folder_input.setPlaceholderText("Đường dẫn thư mục lưu ảnh...")
        folder_layout.addWidget(self.output_folder_input, stretch=1)

        self.select_folder_button = QPushButton("Chọn thư mục", central_widget)
        self.select_folder_button.clicked.connect(self.handle_select_folder)
        folder_layout.addWidget(self.select_folder_button)

        root_layout.addLayout(folder_layout)

        # 4. Action Button & Execution Controls
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.start_button = QPushButton("Bắt đầu tải ảnh", central_widget)
        self.start_button.setMinimumHeight(34)
        self.start_button.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.start_button.clicked.connect(self.handle_start_validation)
        action_layout.addWidget(self.start_button)

        root_layout.addLayout(action_layout)

        # 5. Progress & Status Section
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)

        self.progress_bar = QProgressBar(central_widget)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar, stretch=1)

        self.status_label = QLabel("Sẵn sàng", central_widget)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        progress_layout.addWidget(self.status_label)

        root_layout.addLayout(progress_layout)

        # 6. Results Table Section
        self.results_table = QTableWidget(central_widget)
        self.results_table.setColumnCount(len(self.TABLE_HEADERS))
        self.results_table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.results_table.setAlternatingRowColors(True)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        root_layout.addWidget(self.results_table, stretch=2)

        self.setCentralWidget(central_widget)

    def _restore_settings(self) -> None:
        """Restore persisted user preferences and check initial Shopee session status."""
        saved_folder = self.settings_manager.get_output_folder()
        if saved_folder:
            self.output_folder_input.setText(saved_folder)

        self.auth_status_label.setText(STATUS_CHECKING_SESSION)
        initial_status = self.session_manager.get_session_status()
        if initial_status == STATUS_LOGGED_IN:
            username = self.session_manager.get_authenticated_username()
            display_text = username if username else STATUS_LOGGED_IN
            self._update_auth_ui_state(STATUS_LOGGED_IN, display_text=display_text)
        else:
            self._update_auth_ui_state(initial_status)

    def _update_auth_ui_state(self, status: str, display_text: str | None = None) -> None:
        """Update account status label styling and button enabled states."""
        label_text = display_text or status
        self.auth_status_label.setText(label_text)
        if status == STATUS_LOGGED_IN:
            self.auth_status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #2e7d32; border: none;")
            self.logout_button.setEnabled(True)
            self.login_button.setEnabled(True)
            self.complete_login_button.setEnabled(False)
        elif status == STATUS_SESSION_EXPIRED:
            self.auth_status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #d32f2f; border: none;")
            self.logout_button.setEnabled(True)
            self.login_button.setEnabled(True)
        else:
            self.auth_status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #616161; border: none;")
            self.logout_button.setEnabled(False)
            self.login_button.setEnabled(True)

    def handle_login(self) -> None:
        """Launch dedicated Google Chrome process for interactive manual login."""
        self.login_button.setEnabled(False)
        self.complete_login_button.setEnabled(True)
        self.auth_status_label.setText(STATUS_WAITING_FOR_LOGIN)
        self.status_label.setText("Vui lòng đăng nhập Shopee trên Chrome, sau đó nhấn 'Hoàn tất đăng nhập'...")

        if self._auth_worker and self._auth_worker.isRunning():
            self._auth_worker.cancel()
            self._auth_worker.wait(1000)

        self._auth_worker = AuthLoginWorker(
            session_manager=self.session_manager,
            parent=self,
        )
        self._auth_worker.status_updated.connect(self._on_auth_status_updated)
        self._auth_worker.username_detected.connect(self._on_auth_username_detected)
        self._auth_worker.login_finished.connect(self._on_auth_login_finished)
        self._auth_worker.start()

    def _on_auth_username_detected(self, username: str) -> None:
        """Immediately display detected username in the account section."""
        self.auth_status_label.setText(username)
        self.auth_status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #2e7d32; border: none;")
        self.status_label.setText(f"Đã phát hiện tài khoản: {username}. Vui lòng nhấn 'Hoàn tất đăng nhập' khi sẵn sàng.")

    def _on_auth_status_updated(self, status_text: str) -> None:
        """Update intermediate status during login without auto-closing browser."""
        self.status_label.setText(status_text)
        if "xác minh" in status_text.lower():
            self.auth_status_label.setText(STATUS_VERIFICATION_REQUIRED)
            self.auth_status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #e65100; border: none;")
        elif status_text in (STATUS_OPENING_CHROME, STATUS_WAITING_FOR_LOGIN):
            self.auth_status_label.setText(status_text)

    def _on_auth_login_finished(self, success: bool, message: str) -> None:
        """Handle background monitor lifecycle."""
        self.login_button.setEnabled(True)
        if not success and message:
            self.status_label.setText(message)

    def handle_complete_login(self) -> None:
        """Explicitly validate and finalize the Shopee session upon user request."""
        self.status_label.setText("Đang kiểm tra và lưu phiên Shopee...")
        success, username_or_status, message = self.session_manager.validate_and_finalize_session()

        if success:
            display_name = username_or_status if username_or_status != STATUS_LOGGED_IN else None
            self._update_auth_ui_state(STATUS_LOGGED_IN, display_text=display_name)
            self.complete_login_button.setEnabled(False)
            self.login_button.setEnabled(True)
            self.status_label.setText(message)
            if self._auth_worker and self._auth_worker.isRunning():
                self._auth_worker.cancel()
        else:
            self.status_label.setText(message)
            self.auth_status_label.setText(STATUS_SESSION_EXPIRED)
            self.complete_login_button.setEnabled(True)
            self.login_button.setEnabled(True)

    def handle_logout(self) -> None:
        """Safely clear Shopee persistent session and reset status to Chưa đăng nhập."""
        if self._auth_worker and self._auth_worker.isRunning():
            self._auth_worker.cancel()
            self._auth_worker.wait(1000)

        self.session_manager.logout()
        self._update_auth_ui_state(STATUS_NOT_LOGGED_IN)
        self.complete_login_button.setEnabled(False)
        self.status_label.setText("Đã đăng xuất Shopee")

    def handle_select_folder(self) -> None:
        """Open native directory picker to select and persist an output folder."""
        current_text = self.output_folder_input.text().strip()
        initial_dir = (
            current_text
            if (current_text and Path(current_text).is_dir())
            else str(Path.home())
        )

        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục lưu ảnh",
            initial_dir,
            QFileDialog.Option.ShowDirsOnly,
        )

        if selected_dir:
            normalized_path = str(Path(selected_dir))
            self.output_folder_input.setText(normalized_path)
            self.settings_manager.set_output_folder(normalized_path)

    def handle_start_validation(self) -> None:
        """Validate output directory, verify Shopee auth session, parse URLs, and start batch."""
        # 1. Output directory check
        output_folder = self.output_folder_input.text().strip()
        if not output_folder or not Path(output_folder).is_dir():
            self.status_label.setText("Vui lòng chọn thư mục lưu ảnh.")
            return

        # 2. Authentication session check BEFORE batch extraction loop
        if self.session_manager.get_session_status() != STATUS_LOGGED_IN:
            self.status_label.setText("Vui lòng đăng nhập Shopee trước.")
            return

        # 3. URL parsing and validation
        raw_text = self.url_input.toPlainText()
        parsed_items = parse_url_lines(raw_text)

        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(parsed_items))

        valid_items: list[tuple[int, str]] = []
        for row_idx, item in enumerate(parsed_items):
            stt_item = QTableWidgetItem(str(row_idx + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            url_item = QTableWidgetItem(item.url)
            status_item = QTableWidgetItem(item.status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item = QTableWidgetItem("-")
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.results_table.setItem(row_idx, 0, stt_item)
            self.results_table.setItem(row_idx, 1, url_item)
            self.results_table.setItem(row_idx, 2, status_item)
            self.results_table.setItem(row_idx, 3, count_item)

            if item.is_valid:
                valid_items.append((row_idx, item.url))

        if not parsed_items:
            self.status_label.setText("Chưa nhập link")
            return

        if not valid_items:
            self.status_label.setText("Đã nhận 0 link hợp lệ")
            return

        # Start background worker for product metadata extraction
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Đang xử lý {len(valid_items)} link...")

        self._worker = MetadataExtractorWorker(
            items=valid_items,
            extractor=self.extractor,
            session_manager=self.session_manager,
            parent=self,
        )
        self._worker.item_started.connect(self._on_item_started)
        self._worker.item_status_updated.connect(self._on_item_status_updated)
        self._worker.item_completed.connect(self._on_item_completed)
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.batch_finished.connect(self._on_batch_finished)
        self._worker.start()

    def _on_item_started(self, row_idx: int, url: str) -> None:
        """Handle signal when worker begins processing a URL."""
        status_item = self.results_table.item(row_idx, 2)
        if status_item:
            status_item.setText(STATUS_RESOLVING)
        self.status_label.setText(f"Đang xử lý link dòng {row_idx + 1}...")

    def _on_item_status_updated(self, row_idx: int, status_text: str) -> None:
        """Handle signal when worker updates intermediate status for a row."""
        status_item = self.results_table.item(row_idx, 2)
        if status_item:
            status_item.setText(status_text)
        self.status_label.setText(f"{status_text} dòng {row_idx + 1}...")

    def _on_item_completed(self, row_idx: int, result: ProductMetadata) -> None:
        """Handle signal when worker completes metadata extraction for a single row."""
        status_item = self.results_table.item(row_idx, 2)
        link_item = self.results_table.item(row_idx, 1)

        if result.error is None and result.product_name:
            if link_item:
                link_item.setText(result.product_name)

            if status_item:
                status_item.setText(STATUS_COMPLETED)

            tooltip_parts = []
            if result.product_name:
                tooltip_parts.append(f"Tên sản phẩm: {result.product_name}")
            if result.shop_id:
                tooltip_parts.append(f"Shop ID: {result.shop_id}")
            if result.item_id:
                tooltip_parts.append(f"Item ID: {result.item_id}")
            if result.final_url:
                tooltip_parts.append(f"URL: {result.final_url}")
            if tooltip_parts:
                tooltip_text = "\n".join(tooltip_parts)
                if status_item:
                    status_item.setToolTip(tooltip_text)
                if link_item:
                    link_item.setToolTip(tooltip_text)
        else:
            err_msg = result.error or ERROR_PRODUCT_NOT_FOUND
            if status_item:
                status_item.setText(err_msg)
                status_item.setToolTip(err_msg)

    def _on_progress_updated(self, completed: int, total: int) -> None:
        """Handle signal updating the progress bar during batch processing."""
        percent = int((completed / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)

    def _on_batch_finished(self, results: list[ProductMetadata]) -> None:
        """Handle signal when all items in the extraction queue have completed."""
        self.start_button.setEnabled(True)
        self.progress_bar.setValue(100)
        success_count = sum(
            1 for r in results if r.error is None and r.product_name
        )
        total_count = len(results)
        self.status_label.setText(f"Đã lấy thông tin {success_count}/{total_count} sản phẩm")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure background workers are cleanly interrupted on window close."""
        if self._auth_worker and self._auth_worker.isRunning():
            self._auth_worker.cancel()
            self._auth_worker.wait(1000)
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(1000)
        self.session_manager.close_auth_browser()
        super().closeEvent(event)
