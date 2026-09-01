"""Main window implementation for Shopee Image Downloader."""

from dataclasses import replace
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
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
from shopee_image_downloader import __app_name__
from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    ItemState,
    QueueItem,
    QueueState,
)
from shopee_image_downloader.core.bridge_protocol import (
    BridgeProductData,
    create_batch_finished_message,
    create_cancel_processing_message,
    create_open_product_message,
)
from shopee_image_downloader.core.image_downloader import ProductDownloadResult
from shopee_image_downloader.core.error_policy import ErrorStage
from shopee_image_downloader.core.url_validator import ParsedUrl, parse_url_lines
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.ui.presentation import (
    APP_STYLE_SHEET,
    StatusTone,
    apply_table_status_tone,
    batch_summary_text,
    batch_summary_tone,
    download_status_text,
    image_count_text,
    item_progress_text,
    item_state_text,
    item_state_tone,
)
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer
from shopee_image_downloader.workers.image_download_worker import (
    ImageDownloadController,
)

logger = logging.getLogger(__name__)

STATUS_BRIDGE_DISCONNECTED: str = "🔴 Chưa kết nối"
STATUS_BRIDGE_CONNECTED: str = "🟢 Đã kết nối"
STATUS_BRIDGE_LOST: str = "🔴 Mất kết nối"


class MainWindow(QMainWindow):
    """The main application window for Shopee Image Downloader."""

    TABLE_HEADERS: list[str] = ["STT", "Sản phẩm", "Ảnh", "Trạng thái"]
    COL_NUMBER = 0
    COL_PRODUCT = 1
    COL_IMAGES = 2
    COL_STATUS = 3

    def __init__(
        self,
        parent: QWidget | None = None,
        settings_manager: SettingsManager | None = None,
        bridge_server: ExtensionBridgeServer | None = None,
        image_download_controller: ImageDownloadController | None = None,
        start_bridge: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(__app_name__)
        self.resize(850, 650)
        self.setMinimumSize(620, 480)
        self.settings_manager = settings_manager or SettingsManager()
        self.bridge_server = bridge_server or ExtensionBridgeServer(parent=self)
        self.queue_manager = BatchQueueManager(parent=self)
        self.image_download_controller = (
            image_download_controller or ImageDownloadController(parent=self)
        )
        self._start_bridge = start_bridge
        self._bridge_has_connected_before: bool = False
        self._close_requested: bool = False
        self._rows_by_request_id: dict[str, int] = {}
        self._rows_by_product_key: dict[str, int] = {}
        self._products_by_product_key: dict[str, BridgeProductData] = {}
        self._last_batch_finished: int = 0
        self._last_batch_total: int = 0

        self._init_ui()
        self._restore_settings()
        self._init_bridge()

    def _init_bridge(self) -> None:
        """Connect bridge signals and start the local WebSocket server."""
        self.bridge_server.connection_status_changed.connect(self._on_bridge_status_changed)
        self.bridge_server.product_received.connect(self._on_bridge_product_received)
        self.bridge_server.process_progress_received.connect(self._on_bridge_process_progress_received)
        self.bridge_server.process_error_received.connect(self._on_bridge_process_error_received)
        self.bridge_server.error_occurred.connect(self._on_bridge_error)

        # Connect BatchQueueManager signals
        self.queue_manager.state_changed.connect(self._on_queue_state_changed)
        self.queue_manager.send_open_product_requested.connect(self._on_queue_send_open_product)
        self.queue_manager.send_cancel_requested.connect(self._on_queue_send_cancel)
        self.queue_manager.cancel_download_requested.connect(
            self._on_queue_cancel_download
        )
        self.queue_manager.item_started.connect(self._on_queue_item_started)
        self.queue_manager.item_progress.connect(self._on_queue_item_progress)
        self.queue_manager.item_image_progress.connect(
            self._on_queue_item_image_progress
        )
        self.queue_manager.item_download_requested.connect(
            self._on_queue_item_download_requested
        )
        self.queue_manager.item_completed.connect(self._on_queue_item_completed)
        self.queue_manager.item_skipped_duplicate.connect(
            self._on_queue_item_skipped_duplicate
        )
        self.queue_manager.item_failed.connect(self._on_queue_item_failed)
        self.queue_manager.verification_required.connect(self._on_queue_verification_required)
        self.queue_manager.progress_updated.connect(self._on_queue_progress_updated)
        self.queue_manager.batch_finished.connect(self._on_queue_batch_finished)

        self.image_download_controller.progress.connect(
            self._on_image_download_progress
        )
        metadata_signal = getattr(
            self.image_download_controller,
            "metadata_started",
            None,
        )
        if metadata_signal is not None:
            metadata_signal.connect(self._on_metadata_started)
        self.image_download_controller.folder_ready.connect(
            self._on_product_folder_ready
        )
        self.image_download_controller.finished.connect(
            self._on_image_download_finished
        )
        self.image_download_controller.failed.connect(self._on_image_download_failed)
        self.image_download_controller.cancelled.connect(
            self._on_image_download_cancelled
        )
        idle_signal = getattr(self.image_download_controller, "idle", None)
        if idle_signal is not None:
            idle_signal.connect(self._on_download_controller_idle)

        if self._start_bridge:
            self.bridge_server.start_server()

    def _init_ui(self) -> None:
        """Initialize all UI widgets, layouts, and table columns."""
        central_widget = QWidget(self)
        central_widget.setStyleSheet(APP_STYLE_SHEET)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        # 1. URL input
        url_header_layout = QHBoxLayout()
        self.url_label = QLabel("Link sản phẩm Shopee", central_widget)
        self.url_label.setProperty("role", "sectionTitle")
        url_header_layout.addWidget(self.url_label)
        url_header_layout.addStretch(1)
        self.url_count_label = QLabel("0 link hợp lệ", central_widget)
        self.url_count_label.setObjectName("urlCountLabel")
        url_header_layout.addWidget(self.url_count_label)
        root_layout.addLayout(url_header_layout)

        self.url_input = QPlainTextEdit(central_widget)
        self.url_input.setPlaceholderText(
            "Dán link sản phẩm Shopee tại đây, mỗi dòng một link..."
        )
        self.url_input.setMinimumHeight(82)
        self.url_input.setAccessibleName("Link sản phẩm Shopee")
        self.url_input.textChanged.connect(self._update_url_count)
        self.url_label.setBuddy(self.url_input)
        root_layout.addWidget(self.url_input, stretch=1)

        # 2. Output folder
        self.output_folder_label = QLabel("Thư mục lưu ảnh", central_widget)
        self.output_folder_label.setProperty("role", "sectionTitle")
        root_layout.addWidget(self.output_folder_label)

        folder_layout = QHBoxLayout()
        folder_layout.setSpacing(8)

        self.output_folder_input = QLineEdit(central_widget)
        self.output_folder_input.setReadOnly(True)
        self.output_folder_input.setPlaceholderText("Đường dẫn thư mục lưu ảnh...")
        self.output_folder_input.setAccessibleName("Thư mục lưu ảnh")
        self.output_folder_input.textChanged.connect(
            self._update_output_path_tooltip
        )
        self.output_folder_label.setBuddy(self.output_folder_input)
        folder_layout.addWidget(self.output_folder_input, stretch=1)

        self.select_folder_button = QPushButton("Chọn thư mục", central_widget)
        self.select_folder_button.clicked.connect(self.handle_select_folder)
        folder_layout.addWidget(self.select_folder_button)

        root_layout.addLayout(folder_layout)

        # 3. Primary and secondary actions, with compact bridge state
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.start_button = QPushButton("Bắt đầu tải ảnh", central_widget)
        self.start_button.setObjectName("startButton")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.handle_start_validation)
        action_layout.addWidget(self.start_button)

        self.cancel_button = QPushButton("Hủy", central_widget)
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.handle_cancel)
        action_layout.addWidget(self.cancel_button)

        self.continue_button = QPushButton("Tiếp tục", central_widget)
        self.continue_button.setObjectName("continueButton")
        self.continue_button.setEnabled(False)
        self.continue_button.setVisible(False)
        self.continue_button.clicked.connect(self.handle_continue)
        action_layout.addWidget(self.continue_button)

        action_layout.addStretch(1)

        bridge_frame = QFrame(central_widget)
        bridge_frame.setObjectName("bridgeFrame")
        bridge_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bridge_layout = QHBoxLayout(bridge_frame)
        bridge_layout.setContentsMargins(8, 4, 8, 4)
        bridge_layout.setSpacing(6)
        self.bridge_title_label = QLabel("Chrome Extension:", bridge_frame)
        self.bridge_title_label.setObjectName("bridgeTitleLabel")
        bridge_layout.addWidget(self.bridge_title_label)
        self.bridge_status_label = QLabel(STATUS_BRIDGE_DISCONNECTED, bridge_frame)
        bridge_layout.addWidget(self.bridge_status_label)
        action_layout.addWidget(bridge_frame)

        root_layout.addLayout(action_layout)

        # 4. Overall batch progress and current-product status
        progress_header_layout = QHBoxLayout()
        progress_title = QLabel("Tiến độ batch", central_widget)
        progress_title.setProperty("role", "sectionTitle")
        progress_header_layout.addWidget(progress_title)
        progress_header_layout.addStretch(1)
        self.batch_progress_label = QLabel("Sản phẩm 0/0", central_widget)
        self.batch_progress_label.setObjectName("batchProgressLabel")
        progress_header_layout.addWidget(self.batch_progress_label)
        root_layout.addLayout(progress_header_layout)

        self.progress_bar = QProgressBar(central_widget)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAccessibleName("Tiến độ batch")
        root_layout.addWidget(self.progress_bar)

        self.current_product_label = QLabel("Chưa bắt đầu xử lý.", central_widget)
        self.current_product_label.setObjectName("currentProductLabel")
        self.current_product_label.setWordWrap(True)
        root_layout.addWidget(self.current_product_label)

        # 5. Product results
        self.results_table = QTableWidget(central_widget)
        self.results_table.setColumnCount(len(self.TABLE_HEADERS))
        self.results_table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setWordWrap(False)
        self.results_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setAccessibleName("Kết quả sản phẩm")
        self.results_table.setMinimumHeight(145)

        header = self.results_table.horizontalHeader()
        header.setMinimumSectionSize(44)
        header.setSectionResizeMode(
            self.COL_NUMBER,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            self.COL_PRODUCT,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            self.COL_IMAGES,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            self.COL_STATUS,
            QHeaderView.ResizeMode.Interactive,
        )
        self.results_table.setColumnWidth(self.COL_STATUS, 220)

        root_layout.addWidget(self.results_table, stretch=3)

        # 6. Final status / summary
        self.status_label = QLabel(
            "Chưa có sản phẩm nào được xử lý.",
            central_widget,
        )
        self.status_label.setObjectName("summaryLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("statusTone", StatusTone.NEUTRAL.value)
        root_layout.addWidget(self.status_label)

        self.setCentralWidget(central_widget)
        QWidget.setTabOrder(self.url_input, self.select_folder_button)
        QWidget.setTabOrder(self.select_folder_button, self.start_button)
        QWidget.setTabOrder(self.start_button, self.cancel_button)
        QWidget.setTabOrder(self.cancel_button, self.continue_button)
        QWidget.setTabOrder(self.continue_button, self.results_table)
        self._update_url_count()
        self._update_output_path_tooltip()

    def _restore_settings(self) -> None:
        """Restore persisted user preferences."""
        saved_folder = self.settings_manager.get_output_folder()
        if saved_folder:
            self.output_folder_input.setText(saved_folder)

    def _update_url_count(self) -> None:
        """Show the valid count produced by the existing canonical parser."""
        parsed_items = parse_url_lines(self.url_input.toPlainText())
        valid_count = sum(item.is_valid for item in parsed_items)
        self.url_count_label.setText(f"{valid_count} link hợp lệ")

    def _update_output_path_tooltip(self) -> None:
        """Keep the full flexible path available without widening the layout."""
        path_text = self.output_folder_input.text().strip()
        self.output_folder_input.setToolTip(path_text)

    def _set_summary(self, text: str, tone: StatusTone) -> None:
        """Update the final-status area through one centralized tone property."""
        self.status_label.setText(text)
        self.status_label.setProperty("statusTone", tone.value)
        style = self.status_label.style()
        style.unpolish(self.status_label)
        style.polish(self.status_label)

    def _set_row_status(
        self,
        row_idx: int,
        text: str,
        tone: StatusTone,
        *,
        tooltip: str = "",
    ) -> None:
        """Set one user-facing status without using table text as state."""
        status_item = self.results_table.item(row_idx, self.COL_STATUS)
        if status_item is None:
            return
        status_item.setText(text)
        status_item.setToolTip(tooltip)
        apply_table_status_tone(status_item, tone)

    def _queue_item_for_row(self, row_idx: int) -> QueueItem | None:
        """Resolve a presentation row from the authoritative queue model."""
        return next(
            (item for item in self.queue_manager.items if item.row_idx == row_idx),
            None,
        )

    def _current_product_position(self) -> tuple[int, int]:
        """Return one-based current position without deriving it from UI text."""
        total = self.queue_manager.total_count
        current = self.queue_manager.current_item
        if current is None:
            return 0, total
        for index, item in enumerate(self.queue_manager.items, start=1):
            if item is current:
                return index, total
        return 0, total

    def _refresh_controls(self) -> None:
        """Apply Start/Cancel/Continue and input locking from runtime state."""
        state = self.queue_manager.state
        queue_active = state in {
            QueueState.RUNNING,
            QueueState.PAUSED_VERIFICATION,
            QueueState.CANCELLING,
        }
        controller_busy = bool(self.image_download_controller.is_busy)
        controls_locked = queue_active or controller_busy

        self.start_button.setText("Bắt đầu tải ảnh")
        self.start_button.setEnabled(
            not self._close_requested and not controls_locked
        )
        self.cancel_button.setEnabled(
            not self._close_requested
            and state in {QueueState.RUNNING, QueueState.PAUSED_VERIFICATION}
        )
        verification = state == QueueState.PAUSED_VERIFICATION
        self.continue_button.setVisible(verification)
        self.continue_button.setEnabled(
            verification and not self._close_requested
        )
        input_enabled = not controls_locked and not self._close_requested
        self.url_input.setEnabled(input_enabled)
        self.output_folder_input.setEnabled(input_enabled)
        self.select_folder_button.setEnabled(input_enabled)

    def _populate_result_rows(
        self,
        parsed_items: list[ParsedUrl],
    ) -> list[tuple[int, str]]:
        """Create one stable row per parser result and return valid queue inputs."""
        self._rows_by_request_id.clear()
        self._rows_by_product_key.clear()
        self._products_by_product_key.clear()
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(parsed_items))

        valid_items: list[tuple[int, str]] = []
        for row_idx, parsed in enumerate(parsed_items):
            number_item = QTableWidgetItem(str(row_idx + 1))
            number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            product_item = QTableWidgetItem(parsed.url)
            product_item.setToolTip(parsed.url)
            count_item = QTableWidgetItem("-")
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.results_table.setItem(
                row_idx,
                self.COL_NUMBER,
                number_item,
            )
            self.results_table.setItem(
                row_idx,
                self.COL_PRODUCT,
                product_item,
            )
            self.results_table.setItem(
                row_idx,
                self.COL_IMAGES,
                count_item,
            )
            self.results_table.setItem(
                row_idx,
                self.COL_STATUS,
                status_item,
            )

            if parsed.is_valid:
                valid_items.append((row_idx, parsed.url))
                self._set_row_status(
                    row_idx,
                    item_state_text(ItemState.PENDING),
                    item_state_tone(ItemState.PENDING),
                )
            else:
                self._set_row_status(
                    row_idx,
                    parsed.status,
                    StatusTone.ERROR,
                    tooltip="Vui lòng kiểm tra lại link Shopee.",
                )
        return valid_items

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
        """Validate current inputs and start one sequential batch snapshot."""
        if self._close_requested:
            return
        if self.queue_manager.is_active:
            return

        if self.image_download_controller.is_busy:
            self._set_summary(
                "Đang dừng hoặc hoàn tất tải ảnh hiện tại.",
                StatusTone.WARNING,
            )
            return

        # Reuse Task 003 parsing and exact-deduplication behavior.
        raw_text = self.url_input.toPlainText()
        parsed_items = parse_url_lines(raw_text)
        if not parsed_items:
            self.results_table.setRowCount(0)
            self._set_summary(
                "Vui lòng nhập ít nhất một link Shopee hợp lệ.",
                StatusTone.WARNING,
            )
            return

        valid_items = [
            (row_idx, item.url)
            for row_idx, item in enumerate(parsed_items)
            if item.is_valid
        ]
        if not valid_items:
            self._populate_result_rows(parsed_items)
            self._set_summary(
                "Vui lòng nhập ít nhất một link Shopee hợp lệ.",
                StatusTone.WARNING,
            )
            return

        output_folder = self.output_folder_input.text().strip()
        if not output_folder or not Path(output_folder).is_dir():
            self._set_summary(
                "Vui lòng chọn thư mục lưu ảnh.",
                StatusTone.WARNING,
            )
            return

        valid_items = self._populate_result_rows(parsed_items)
        if not self.bridge_server.has_connected_clients:
            self._set_summary(
                "Chrome Extension chưa kết nối.",
                StatusTone.WARNING,
            )
            return

        # Start sequential batch queue from the validated snapshot.
        self.progress_bar.setValue(0)
        self.batch_progress_label.setText(
            f"Sản phẩm 0/{len(valid_items)}"
        )
        self.current_product_label.setText(
            f"Chuẩn bị xử lý {len(valid_items)} sản phẩm..."
        )
        self._set_summary("Đang xử lý...", StatusTone.ACTIVE)
        if not self.queue_manager.start_batch(valid_items):
            self._set_summary(
                "Không thể bắt đầu batch mới lúc này.",
                StatusTone.WARNING,
            )

    def handle_cancel(self) -> None:
        """Request cancellation exactly once while a batch owns the UI."""
        if self._close_requested or not self.cancel_button.isEnabled():
            return
        self.cancel_button.setEnabled(False)
        self.queue_manager.cancel_batch()

    def handle_continue(self) -> None:
        """Resume only the existing verification-paused queue item."""
        if (
            self._close_requested
            or self.queue_manager.state != QueueState.PAUSED_VERIFICATION
        ):
            return
        self.continue_button.setEnabled(False)
        self.queue_manager.resume_verification()

    def _on_queue_state_changed(self, new_state_str: str) -> None:
        """Reflect the authoritative queue state in all processing controls."""
        state = QueueState(new_state_str)
        self._refresh_controls()
        if state == QueueState.CANCELLING:
            self.current_product_label.setText("Đang hủy an toàn...")

    def _on_queue_send_open_product(self, request_id: str, url: str) -> None:
        """Send open_product message to Chrome Extension via bridge."""
        msg = create_open_product_message(request_id, url)
        sent = self.bridge_server.send_message(msg)
        if sent is False:
            self.queue_manager.handle_process_error(
                request_id,
                url,
                "BRIDGE_DISCONNECTED",
                "Native Host/Extension bridge is unavailable",
            )

    def _on_queue_send_cancel(self, request_id: str) -> None:
        """Send cancel_processing message to Chrome Extension via bridge."""
        msg = create_cancel_processing_message(request_id)
        self.bridge_server.send_message(msg)

    def _on_queue_cancel_download(self, request_id: str) -> None:
        """Cooperatively stop only the worker owned by this request."""
        self.image_download_controller.cancel(request_id)

    def _on_bridge_process_progress_received(self, request_id: str, stage: str) -> None:
        """Forward process progress message from bridge to queue manager."""
        try:
            self.queue_manager.handle_process_progress(request_id, stage)
        except Exception as exc:
            self.queue_manager.handle_internal_failure(
                request_id,
                ErrorStage.EXTRACTION,
                exc,
            )

    def _on_bridge_process_error_received(self, request_id: str, url: str, error_code: str, message: str) -> None:
        """Forward process error message from bridge to queue manager."""
        try:
            self.queue_manager.handle_process_error(
                request_id,
                url,
                error_code,
                message,
            )
        except Exception as exc:
            self.queue_manager.handle_internal_failure(
                request_id,
                ErrorStage.EXTRACTION,
                exc,
            )

    def _on_queue_item_started(self, row_idx: int, url: str, request_id: str) -> None:
        """Handle item start event from queue manager."""
        self._rows_by_request_id[request_id] = row_idx
        item = self._queue_item_for_row(row_idx)
        if item is not None:
            self._set_row_status(
                row_idx,
                item_progress_text(item),
                item_state_tone(item.state),
            )
        position, total = self._current_product_position()
        self.current_product_label.setText(
            f"Đang mở sản phẩm {position}/{total}..."
        )

    def _on_queue_item_progress(self, row_idx: int, stage: str, display_text: str) -> None:
        """Render progress from the current queue item rather than raw enum text."""
        item = self._queue_item_for_row(row_idx)
        if item is None:
            return
        text = item_progress_text(item)
        self._set_row_status(row_idx, text, item_state_tone(item.state))
        position, total = self._current_product_position()
        self.current_product_label.setText(
            f"Sản phẩm {position}/{total} — {text}"
        )

    def _on_queue_item_image_progress(
        self,
        row_idx: int,
        completed: int,
        total: int,
    ) -> None:
        """Show authoritative per-image progress separately from batch progress."""
        count_item = self.results_table.item(row_idx, self.COL_IMAGES)
        if count_item is not None:
            count_item.setText(f"{completed}/{total}")
        item = self._queue_item_for_row(row_idx)
        if item is None or item.state != ItemState.DOWNLOADING:
            return
        self._set_row_status(
            row_idx,
            "Đang tải ảnh",
            StatusTone.ACTIVE,
        )
        position, batch_total = self._current_product_position()
        self.current_product_label.setText(
            f"Sản phẩm {position}/{batch_total} — "
            f"Đang tải ảnh {completed}/{total}..."
        )

    def _on_queue_item_download_requested(
        self,
        row_idx: int,
        product_data: BridgeProductData,
    ) -> None:
        """Start the current batch item's download through the QThread controller."""
        self._update_table_row(
            row_idx,
            product_data,
            status_text=item_state_text(ItemState.CREATING_FOLDER),
            status_tone=item_state_tone(ItemState.CREATING_FOLDER),
        )
        try:
            started = self.image_download_controller.start(
                product_data,
                self.output_folder_input.text().strip(),
            )
        except Exception:
            logger.exception(
                "Không thể khởi động worker cho %s", product_data.product_key
            )
            started = False
        if not started:
            request_id = product_data.request_id
            if request_id:
                self.queue_manager.handle_download_failure(
                    request_id,
                    "Không thể bắt đầu tải ảnh sản phẩm.",
                )

    def _update_table_row(
        self,
        row_idx: int,
        product_data: BridgeProductData,
        status_text: str = "Hoàn tất",
        *,
        status_tone: StatusTone = StatusTone.SUCCESS,
        bind_product_index: bool = True,
    ) -> None:
        """Update an existing table row with authoritative product data and bind indexes."""
        if row_idx < 0 or row_idx >= self.results_table.rowCount():
            return

        product_item = self.results_table.item(row_idx, self.COL_PRODUCT)
        if product_item:
            product_item.setText(product_data.product_name)

        self._set_row_status(row_idx, status_text, status_tone)

        count_item = self.results_table.item(row_idx, self.COL_IMAGES)
        if count_item:
            count_item.setText(
                image_count_text(
                    product_data.download_result,
                    len(product_data.images),
                )
            )

        # Bind indexes
        key = product_data.product_key
        if key and bind_product_index:
            self._rows_by_product_key[key] = row_idx
            self._products_by_product_key[key] = product_data
        if product_data.request_id:
            self._rows_by_request_id[product_data.request_id] = row_idx

        logger.info(
            "[DESKTOP]\nrequest_id=%s\nproduct_key=%s\nreceived=%d\nstored=%d\nrow=%d",
            product_data.request_id or "N/A",
            product_data.product_key,
            len(product_data.images),
            len(product_data.images),
            row_idx,
        )

        tooltip_parts = [
            f"Tên sản phẩm: {product_data.product_name}",
            f"Shop ID: {product_data.shop_id}",
            f"Item ID: {product_data.item_id}",
            f"URL: {product_data.url or product_data.final_url}",
            f"Số ảnh: {len(product_data.images)}",
        ]
        if product_data.product_folder is not None:
            tooltip_parts.append(f"Thư mục: {product_data.product_folder}")
        tooltip_text = "\n".join(tooltip_parts)
        if product_item is not None:
            product_item.setToolTip(tooltip_text)

    def _on_queue_item_completed(self, row_idx: int, product_data: BridgeProductData) -> None:
        """Handle item completion from queue manager."""
        item = self._queue_item_for_row(row_idx)
        tone = (
            item_state_tone(item.state)
            if item is not None
            else StatusTone.SUCCESS
        )
        self._update_table_row(
            row_idx,
            product_data,
            status_text=download_status_text(product_data.download_result),
            status_tone=tone,
        )

    def _on_queue_item_skipped_duplicate(
        self,
        row_idx: int,
        product_data: BridgeProductData,
    ) -> None:
        """Present a handled duplicate without replacing the successful row index."""
        self._update_table_row(
            row_idx,
            product_data,
            status_text=item_state_text(ItemState.SKIPPED_DUPLICATE),
            status_tone=item_state_tone(ItemState.SKIPPED_DUPLICATE),
            bind_product_index=False,
        )

    def _on_queue_item_failed(self, row_idx: int, error_code: str, error_message: str) -> None:
        """Handle item failure from queue manager."""
        item = self._queue_item_for_row(row_idx)
        cancelled = item is not None and item.state == ItemState.CANCELLED
        tone = StatusTone.CANCELLED if cancelled else StatusTone.ERROR
        text = item_state_text(ItemState.CANCELLED) if cancelled else error_message
        tooltip_parts = [text, f"Mã lỗi: {error_code}"]
        if item is not None and item.last_error is not None:
            technical = item.last_error.technical_message.strip()
            if technical and technical != text:
                tooltip_parts.append(f"Chi tiết: {technical[:400]}")
        self._set_row_status(
            row_idx,
            text,
            tone,
            tooltip="\n".join(tooltip_parts),
        )

    def _on_queue_verification_required(self, row_idx: int, url: str, message: str) -> None:
        """Handle verification challenge pause."""
        self._set_row_status(
            row_idx,
            "Cần xác minh trên Chrome",
            StatusTone.WARNING,
            tooltip=message,
        )
        verification_text = (
            "Shopee yêu cầu xác minh trên Chrome.\n"
            "Hãy hoàn tất xác minh rồi tiếp tục."
        )
        self.current_product_label.setText(verification_text)
        self._set_summary(verification_text, StatusTone.WARNING)

    def _on_queue_progress_updated(self, finished: int, total: int) -> None:
        """Update progress bar with finished/total fraction."""
        percent = int((finished / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)
        self.batch_progress_label.setText(f"Sản phẩm {finished}/{total}")
        self._last_batch_finished = finished
        self._last_batch_total = total

    def _on_queue_batch_finished(
        self,
        success_count: int,
        fail_count: int,
        items: list[QueueItem],
    ) -> None:
        """Handle overall batch completion."""
        total = len(items)
        terminal = sum(item.is_finished for item in items)
        percent = int((terminal / total) * 100) if total else 0
        self.progress_bar.setValue(percent)
        self.batch_progress_label.setText(f"Sản phẩm {terminal}/{total}")
        self._set_summary(
            batch_summary_text(items),
            batch_summary_tone(items),
        )
        if any(item.state == ItemState.CANCELLED for item in items):
            self.current_product_label.setText("Batch đã được hủy an toàn.")
        else:
            self.current_product_label.setText(
                f"Đã xử lý {terminal}/{total} sản phẩm."
            )
        self._refresh_controls()
        # Notify Chrome Extension to restore user's original tab
        msg = create_batch_finished_message(success_count, fail_count)
        self.bridge_server.send_message(msg)

    def _on_image_download_progress(
        self,
        product_data: BridgeProductData,
        index: int,
        total: int,
    ) -> None:
        """Show product image progress emitted from the background worker."""
        if self.queue_manager.is_known_request(product_data.request_id):
            self.queue_manager.handle_download_progress(
                product_data,
                index,
                total,
            )
            return
        row_idx = self._row_for_product(product_data)
        if row_idx is not None:
            count_item = self.results_table.item(row_idx, self.COL_IMAGES)
            if count_item is not None:
                count_item.setText(f"{index}/{total}")
            self._set_row_status(
                row_idx,
                "Đang tải ảnh",
                StatusTone.ACTIVE,
            )
            self.current_product_label.setText(
                f"Đang tải ảnh {index}/{total} — {product_data.product_name}"
            )

    def _on_metadata_started(self, product_data: BridgeProductData) -> None:
        """Present the existing product.json phase without changing its policy."""
        if self.queue_manager.is_known_request(product_data.request_id):
            self.queue_manager.handle_metadata_started(product_data)
            return
        row_idx = self._row_for_product(product_data)
        if row_idx is not None:
            self._set_row_status(
                row_idx,
                "Đang lưu thông tin",
                StatusTone.ACTIVE,
            )
        self.current_product_label.setText(
            f"Đang lưu thông tin — {product_data.product_name}"
        )

    def _on_product_folder_ready(
        self,
        product_data: BridgeProductData,
    ) -> None:
        """Publish a worker-created folder only to its correlated owner."""
        if self.queue_manager.is_known_request(product_data.request_id):
            self.queue_manager.handle_product_folder_ready(product_data)
            return
        row_idx = self._row_for_product(product_data)
        if row_idx is not None:
            self._update_table_row(
                row_idx,
                product_data,
                status_text="Đang tải ảnh",
                status_tone=StatusTone.ACTIVE,
            )
            count_item = self.results_table.item(row_idx, self.COL_IMAGES)
            if count_item is not None:
                count_item.setText(f"0/{len(product_data.images)}")

    def _on_image_download_finished(
        self,
        product_data: BridgeProductData,
        result: object,
    ) -> None:
        """Attach a structured result and complete batch or manual presentation."""
        if not isinstance(result, ProductDownloadResult):
            self._on_image_download_failed(
                product_data,
                "IMAGE_DOWNLOAD_ERROR",
                "Kết quả tải ảnh không hợp lệ.",
            )
            return

        completed_product = replace(product_data, download_result=result)
        if self.queue_manager.is_known_request(completed_product.request_id):
            self.queue_manager.handle_download_result(completed_product)
            return

        row_idx = self._row_for_product(completed_product)
        if row_idx is not None:
            status_text = download_status_text(completed_product.download_result)
            tone = (
                StatusTone.WARNING
                if completed_product.download_result
                and completed_product.download_result.failed
                else StatusTone.SUCCESS
            )
            self._update_table_row(
                row_idx,
                completed_product,
                status_text=status_text,
                status_tone=tone,
            )
            self._set_summary(status_text, tone)
            self.current_product_label.setText(
                f"Đã xử lý — {completed_product.product_name}"
            )
        self._refresh_controls()

    def _on_image_download_failed(
        self,
        product_data: BridgeProductData,
        error_code: str,
        message: str,
    ) -> None:
        """Handle an unexpected product-level worker failure without a traceback."""
        if self.queue_manager.is_known_request(product_data.request_id):
            self.queue_manager.handle_pipeline_failure(
                product_data,
                error_code,
                message,
            )
            return

        row_idx = self._row_for_product(product_data)
        if row_idx is not None:
            self._set_row_status(
                row_idx,
                message,
                StatusTone.ERROR,
                tooltip=f"Mã lỗi: {error_code}",
            )
        self._set_summary(message, StatusTone.ERROR)
        self.current_product_label.setText("Không thể hoàn tất sản phẩm.")
        self._refresh_controls()

    def _on_image_download_cancelled(self, product_data: BridgeProductData) -> None:
        """Keep queue cancellation authoritative; update standalone manual work."""
        if self.queue_manager.is_known_request(product_data.request_id):
            self.queue_manager.handle_download_cancelled(product_data)
            return
        row_idx = self._row_for_product(product_data)
        if row_idx is not None:
            self._set_row_status(
                row_idx,
                item_state_text(ItemState.CANCELLED),
                StatusTone.CANCELLED,
            )
        self._set_summary("Đã hủy.", StatusTone.CANCELLED)
        self.current_product_label.setText("Đã hủy tải ảnh.")
        self._refresh_controls()

    def _row_for_product(self, product_data: BridgeProductData) -> int | None:
        """Resolve the existing table row without creating a duplicate model."""
        if product_data.request_id:
            row_idx = self._rows_by_request_id.get(product_data.request_id)
            if row_idx is not None:
                return row_idx
        return self._rows_by_product_key.get(product_data.product_key)

    def _on_bridge_status_changed(self, connected: bool) -> None:
        """Update Chrome Extension connection state in the UI."""
        if connected:
            self._bridge_has_connected_before = True
            self.bridge_status_label.setText(STATUS_BRIDGE_CONNECTED)
        else:
            if self._bridge_has_connected_before:
                self.bridge_status_label.setText(STATUS_BRIDGE_LOST)
            else:
                self.bridge_status_label.setText(STATUS_BRIDGE_DISCONNECTED)
            current = self.queue_manager.current_item
            if (
                self.queue_manager.state == QueueState.RUNNING
                and current is not None
                and current.state.value
                in {"OPENING_PRODUCT", "WAITING_EXTRACTION"}
            ):
                self.queue_manager.handle_process_error(
                    current.request_id,
                    current.input_url,
                    "BRIDGE_DISCONNECTED",
                    "Native Host/Extension bridge disconnected",
                )

    def _on_bridge_error(self, error_message: str) -> None:
        """Handle errors reported by the WebSocket bridge."""
        self._set_summary(
            f"Lỗi kết nối Chrome: {error_message}",
            StatusTone.ERROR,
        )

    def _on_bridge_product_received(self, product_data: BridgeProductData) -> None:
        """Handle product result received from the Chrome Extension bridge.

        Updates existing rows matched by request_id or product_key without appending duplicates.
        """
        req_id = product_data.request_id
        if self.queue_manager.is_known_request(req_id):
            try:
                self.queue_manager.handle_product_result(product_data)
            except Exception as exc:
                self.queue_manager.handle_internal_failure(
                    req_id,
                    ErrorStage.PROTOCOL,
                    exc,
                )
            return

        if self.queue_manager.is_active:
            logger.warning(
                "Bỏ qua product_result không tương quan khi batch đang chạy: %s",
                req_id,
            )
            return

        if (
            product_data.image_count is not None
            and product_data.image_count != len(product_data.images)
        ):
            logger.error(
                "Lỗi đồng bộ dữ liệu ảnh: image_count=%s != len(images)=%d",
                product_data.image_count,
                len(product_data.images),
            )
            self._set_summary(
                "Lỗi đồng bộ dữ liệu ảnh từ Chrome.",
                StatusTone.ERROR,
            )
            return

        key = product_data.product_key
        self._products_by_product_key[product_data.product_key] = product_data

        # Determine target row_idx
        row_idx: int | None = None
        if req_id and req_id in self._rows_by_request_id:
            row_idx = self._rows_by_request_id[req_id]
        elif key and key in self._rows_by_product_key:
            row_idx = self._rows_by_product_key[key]

        if row_idx is not None and row_idx < self.results_table.rowCount():
            self._update_table_row(
                row_idx,
                product_data,
                status_text="Đã nhận từ Chrome",
                status_tone=StatusTone.ACTIVE,
            )
            self._set_summary(
                f"Đã nhận từ Chrome: {product_data.product_name}",
                StatusTone.ACTIVE,
            )
        else:
            row_idx = self.results_table.rowCount()
            self.results_table.insertRow(row_idx)

            stt_item = QTableWidgetItem(str(row_idx + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            link_item = QTableWidgetItem(product_data.product_name)

            count_item = QTableWidgetItem(str(len(product_data.images)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            status_item = QTableWidgetItem("Đã nhận từ Chrome")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            apply_table_status_tone(status_item, StatusTone.ACTIVE)

            self.results_table.setItem(row_idx, self.COL_NUMBER, stt_item)
            self.results_table.setItem(row_idx, self.COL_PRODUCT, link_item)
            self.results_table.setItem(row_idx, self.COL_IMAGES, count_item)
            self.results_table.setItem(row_idx, self.COL_STATUS, status_item)

            if key:
                self._rows_by_product_key[key] = row_idx
            if req_id:
                self._rows_by_request_id[req_id] = row_idx

            logger.info(
                "[DESKTOP INSERT]\nrequest_id=%s\nproduct_key=%s\nreceived=%d\nstored=%d\nrow=%d",
                req_id or "N/A",
                product_data.product_key,
                len(product_data.images),
                len(product_data.images),
                row_idx,
            )

            tooltip_parts = [
                f"Tên sản phẩm: {product_data.product_name}",
                f"Shop ID: {product_data.shop_id}",
                f"Item ID: {product_data.item_id}",
                f"URL: {product_data.url or product_data.final_url}",
                f"Số ảnh: {len(product_data.images)}",
            ]
            tooltip_text = "\n".join(tooltip_parts)
            link_item.setToolTip(tooltip_text)

            self._set_summary(
                f"Đã nhận từ Chrome: {product_data.product_name} "
                f"({len(product_data.images)} ảnh)",
                StatusTone.ACTIVE,
            )

        self._update_table_row(
            row_idx,
            product_data,
            status_text=item_state_text(ItemState.CREATING_FOLDER),
            status_tone=StatusTone.ACTIVE,
        )
        try:
            started = self.image_download_controller.start(
                product_data,
                self.output_folder_input.text().strip(),
            )
        except Exception:
            logger.exception(
                "Không thể khởi động worker thủ công cho %s",
                product_data.product_key,
            )
            started = False
        if not started:
            self._on_image_download_failed(
                product_data,
                "INTERNAL_ERROR",
                "Lỗi nội bộ khi xử lý sản phẩm.",
            )
        else:
            self._refresh_controls()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cooperatively close after any owned worker exits."""
        self._close_requested = True
        self._refresh_controls()
        self.queue_manager.cancel_batch()
        self.image_download_controller.cancel()
        self.bridge_server.stop_server()
        if self.image_download_controller.is_busy:
            self._set_summary(
                "Đang dừng tải ảnh để đóng ứng dụng...",
                StatusTone.CANCELLED,
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _on_download_controller_idle(self) -> None:
        """Retry a deferred close only after QThread cleanup is complete."""
        self._refresh_controls()
        if self._close_requested:
            QTimer.singleShot(0, self.close)
