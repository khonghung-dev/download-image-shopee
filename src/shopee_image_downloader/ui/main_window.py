"""Main window implementation for Shopee Image Downloader."""

from dataclasses import replace
import logging
from pathlib import Path

from PySide6.QtCore import Qt
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
from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    QueueState,
    STATUS_DISPLAY_NAVIGATING,
    STATUS_DISPLAY_SUCCESS,
    STATUS_DISPLAY_VERIFICATION,
)
from shopee_image_downloader.core.bridge_protocol import (
    BridgeProductData,
    create_batch_finished_message,
    create_cancel_processing_message,
    create_open_product_message,
)
from shopee_image_downloader.core.url_validator import parse_url_lines
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.storage.product_folder import (
    ProductFolderError,
    ensure_product_folder,
)
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer

logger = logging.getLogger(__name__)

STATUS_BRIDGE_DISCONNECTED: str = "🔴 Chưa kết nối"
STATUS_BRIDGE_CONNECTED: str = "🟢 Đã kết nối"
STATUS_BRIDGE_LOST: str = "🔴 Mất kết nối"


class MainWindow(QMainWindow):
    """The main application window for Shopee Image Downloader."""

    TABLE_HEADERS: list[str] = ["STT", "Sản phẩm / Link", "Trạng thái", "Số ảnh"]

    def __init__(
        self,
        parent: QWidget | None = None,
        settings_manager: SettingsManager | None = None,
        bridge_server: ExtensionBridgeServer | None = None,
        start_bridge: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Shopee Image Downloader")
        self.resize(850, 650)
        self.setMinimumSize(650, 500)
        self.settings_manager = settings_manager or SettingsManager()
        self.bridge_server = bridge_server or ExtensionBridgeServer(parent=self)
        self.queue_manager = BatchQueueManager(parent=self)
        self._start_bridge = start_bridge
        self._bridge_has_connected_before: bool = False
        self._rows_by_request_id: dict[str, int] = {}
        self._rows_by_product_key: dict[str, int] = {}
        self._products_by_product_key: dict[str, BridgeProductData] = {}

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
        self.queue_manager.item_started.connect(self._on_queue_item_started)
        self.queue_manager.item_progress.connect(self._on_queue_item_progress)
        self.queue_manager.item_completed.connect(self._on_queue_item_completed)
        self.queue_manager.item_failed.connect(self._on_queue_item_failed)
        self.queue_manager.verification_required.connect(self._on_queue_verification_required)
        self.queue_manager.progress_updated.connect(self._on_queue_progress_updated)
        self.queue_manager.batch_finished.connect(self._on_queue_batch_finished)

        if self._start_bridge:
            self.bridge_server.start_server()

    def _init_ui(self) -> None:
        """Initialize all UI widgets, layouts, and table columns."""
        central_widget = QWidget(self)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        # 1. Chrome Extension Bridge Section
        bridge_frame = QFrame(central_widget)
        bridge_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bridge_frame.setStyleSheet(
            "QFrame { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 4px; }"
        )
        bridge_layout = QHBoxLayout(bridge_frame)
        bridge_layout.setContentsMargins(8, 6, 8, 6)
        bridge_layout.setSpacing(10)

        self.bridge_title_label = QLabel("Chrome Extension:", bridge_frame)
        self.bridge_title_label.setStyleSheet("font-weight: bold; font-size: 13px; border: none;")
        bridge_layout.addWidget(self.bridge_title_label)

        self.bridge_status_label = QLabel(STATUS_BRIDGE_DISCONNECTED, bridge_frame)
        self.bridge_status_label.setStyleSheet("font-weight: bold; font-size: 13px; border: none;")
        bridge_layout.addWidget(self.bridge_status_label)

        bridge_layout.addStretch(1)
        root_layout.addWidget(bridge_frame)

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
        """Restore persisted user preferences."""
        saved_folder = self.settings_manager.get_output_folder()
        if saved_folder:
            self.output_folder_input.setText(saved_folder)

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
        """Handle start, cancel, or resume batch processing actions."""
        # 1. If currently RUNNING, action button acts as Cancel
        if self.queue_manager.state == QueueState.RUNNING:
            self.queue_manager.cancel_batch()
            return

        # 2. If PAUSED_VERIFICATION, action button acts as Resume (Tiếp tục)
        if self.queue_manager.state == QueueState.PAUSED_VERIFICATION:
            self.queue_manager.resume_verification()
            return

        # 3. Output directory check
        output_folder = self.output_folder_input.text().strip()
        if not output_folder or not Path(output_folder).is_dir():
            self.status_label.setText("Vui lòng chọn thư mục lưu ảnh.")
            return

        # 4. URL parsing and table population
        raw_text = self.url_input.toPlainText()
        parsed_items = parse_url_lines(raw_text)

        self._rows_by_request_id.clear()
        self._rows_by_product_key.clear()
        self._products_by_product_key.clear()
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

        # 5. Chrome Extension bridge connection check
        if not self.bridge_server.has_connected_clients:
            self.status_label.setText("Chrome Extension chưa kết nối.")
            return

        # 6. Start sequential batch queue
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Đang xử lý 1/{len(valid_items)} sản phẩm...")
        self.queue_manager.start_batch(valid_items)

    def _on_queue_state_changed(self, new_state_str: str) -> None:
        """Update Start/Cancel/Resume button text according to queue state."""
        if new_state_str == QueueState.RUNNING.value:
            self.start_button.setText("Hủy")
            self.start_button.setEnabled(True)
        elif new_state_str == QueueState.PAUSED_VERIFICATION.value:
            self.start_button.setText("Tiếp tục")
            self.start_button.setEnabled(True)
        else:
            self.start_button.setText("Bắt đầu tải ảnh")
            self.start_button.setEnabled(True)

    def _on_queue_send_open_product(self, request_id: str, url: str) -> None:
        """Send open_product message to Chrome Extension via bridge."""
        msg = create_open_product_message(request_id, url)
        self.bridge_server.send_message(msg)

    def _on_queue_send_cancel(self, request_id: str) -> None:
        """Send cancel_processing message to Chrome Extension via bridge."""
        msg = create_cancel_processing_message(request_id)
        self.bridge_server.send_message(msg)

    def _on_bridge_process_progress_received(self, request_id: str, stage: str) -> None:
        """Forward process progress message from bridge to queue manager."""
        self.queue_manager.handle_process_progress(request_id, stage)

    def _on_bridge_process_error_received(self, request_id: str, url: str, error_code: str, message: str) -> None:
        """Forward process error message from bridge to queue manager."""
        self.queue_manager.handle_process_error(request_id, url, error_code, message)

    def _on_queue_item_started(self, row_idx: int, url: str, request_id: str) -> None:
        """Handle item start event from queue manager."""
        self._rows_by_request_id[request_id] = row_idx
        status_item = self.results_table.item(row_idx, 2)
        if status_item:
            status_item.setText(STATUS_DISPLAY_NAVIGATING)
        total = self.queue_manager.total_count
        cur_idx = self.queue_manager.get_finished_count() + 1
        self.status_label.setText(f"Đang xử lý {cur_idx}/{total} sản phẩm...")

    def _on_queue_item_progress(self, row_idx: int, stage: str, display_text: str) -> None:
        """Handle item progress stage update."""
        status_item = self.results_table.item(row_idx, 2)
        if status_item:
            status_item.setText(display_text)

    def _update_table_row(
        self,
        row_idx: int,
        product_data: BridgeProductData,
        status_text: str = STATUS_DISPLAY_SUCCESS,
    ) -> None:
        """Update an existing table row with authoritative product data and bind indexes."""
        if row_idx < 0 or row_idx >= self.results_table.rowCount():
            return

        link_item = self.results_table.item(row_idx, 1)
        if link_item:
            link_item.setText(product_data.product_name)

        status_item = self.results_table.item(row_idx, 2)
        if status_item:
            status_item.setText(status_text)

        count_item = self.results_table.item(row_idx, 3)
        if count_item:
            count_item.setText(str(len(product_data.images)))

        # Bind indexes
        key = product_data.product_key
        if key:
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
        for col in range(4):
            item = self.results_table.item(row_idx, col)
            if item:
                item.setToolTip(tooltip_text)

        finished = self.queue_manager.get_finished_count()
        total = self.queue_manager.total_count
        if total > 0:
            self.status_label.setText(f"Đang xử lý {finished}/{total} sản phẩm")

    def _on_queue_item_completed(self, row_idx: int, product_data: BridgeProductData) -> None:
        """Handle item completion from queue manager."""
        self._update_table_row(row_idx, product_data, status_text=STATUS_DISPLAY_SUCCESS)

    def _on_queue_item_failed(self, row_idx: int, error_code: str, error_message: str) -> None:
        """Handle item failure from queue manager."""
        status_item = self.results_table.item(row_idx, 2)
        if status_item:
            status_item.setText(error_message)
            status_item.setToolTip(f"Lỗi: {error_code} - {error_message}")

        finished = self.queue_manager.get_finished_count()
        total = self.queue_manager.total_count
        self.status_label.setText(f"Đang xử lý {finished}/{total} sản phẩm")

    def _on_queue_verification_required(self, row_idx: int, url: str, message: str) -> None:
        """Handle verification challenge pause."""
        status_item = self.results_table.item(row_idx, 2)
        if status_item:
            status_item.setText(STATUS_DISPLAY_VERIFICATION)
            status_item.setToolTip(message)
        self.status_label.setText("Shopee yêu cầu xác minh trên Chrome. Vui lòng giải quyết trên Chrome rồi nhấn 'Tiếp tục'.")

    def _on_queue_progress_updated(self, finished: int, total: int) -> None:
        """Update progress bar with finished/total fraction."""
        percent = int((finished / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)

    def _on_queue_batch_finished(self, success_count: int, fail_count: int, items: list) -> None:
        """Handle overall batch completion."""
        self.start_button.setText("Bắt đầu tải ảnh")
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Hoàn tất: {success_count} thành công, {fail_count} lỗi")
        # Notify Chrome Extension to restore user's original tab
        msg = create_batch_finished_message(success_count, fail_count)
        self.bridge_server.send_message(msg)

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

    def _on_bridge_error(self, error_message: str) -> None:
        """Handle errors reported by the WebSocket bridge."""
        self.status_label.setText(f"Lỗi Bridge: {error_message}")

    def _on_bridge_product_received(self, product_data: BridgeProductData) -> None:
        """Handle product result received from the Chrome Extension bridge.

        Updates existing rows matched by request_id or product_key without appending duplicates.
        """
        # Validate integrity
        if product_data.image_count is not None and product_data.image_count != len(product_data.images):
            logger.error(
                "Lỗi đồng bộ dữ liệu ảnh: image_count=%s != len(images)=%d",
                product_data.image_count,
                len(product_data.images),
            )
            self.status_label.setText("Lỗi đồng bộ dữ liệu ảnh từ Chrome")
            return

        key = product_data.product_key
        req_id = product_data.request_id

        # Batch results are owned by BatchQueueManager. It performs request
        # correlation and emits the single table-update event on success.
        if self.queue_manager.is_running:
            current_item = self.queue_manager.current_item
            if (
                current_item is not None
                and product_data.request_id
                and product_data.request_id != current_item.request_id
            ):
                self.queue_manager.handle_product_result(product_data)
                return
            try:
                product_data = self._with_product_folder(product_data)
            except ProductFolderError as exc:
                logger.exception("Không thể tạo thư mục sản phẩm: %s", exc)
                if current_item is not None:
                    self.queue_manager.handle_process_error(
                        current_item.request_id,
                        current_item.url,
                        "PRODUCT_FOLDER_ERROR",
                        "Không thể tạo thư mục sản phẩm.",
                    )
                return
            self.queue_manager.handle_product_result(product_data)
            return

        try:
            product_data = self._with_product_folder(product_data)
        except ProductFolderError as exc:
            logger.exception("Không thể tạo thư mục sản phẩm: %s", exc)
            self.status_label.setText("Không thể tạo thư mục sản phẩm.")
            return

        self._products_by_product_key[product_data.product_key] = product_data

        # Determine target row_idx
        row_idx: int | None = None
        if req_id and req_id in self._rows_by_request_id:
            row_idx = self._rows_by_request_id[req_id]
        elif key and key in self._rows_by_product_key:
            row_idx = self._rows_by_product_key[key]

        if row_idx is not None and row_idx < self.results_table.rowCount():
            self._update_table_row(row_idx, product_data, status_text="Đã nhận từ Chrome")
            self.status_label.setText(f"Đã nhận từ Chrome: {product_data.product_name}")
        else:
            row_idx = self.results_table.rowCount()
            self.results_table.insertRow(row_idx)

            stt_item = QTableWidgetItem(str(row_idx + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            link_item = QTableWidgetItem(product_data.product_name)

            status_item = QTableWidgetItem("Đã nhận từ Chrome")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            count_item = QTableWidgetItem(str(len(product_data.images)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.results_table.setItem(row_idx, 0, stt_item)
            self.results_table.setItem(row_idx, 1, link_item)
            self.results_table.setItem(row_idx, 2, status_item)
            self.results_table.setItem(row_idx, 3, count_item)

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
                f"Thư mục: {product_data.product_folder}",
            ]
            tooltip_text = "\n".join(tooltip_parts)
            for col in range(4):
                item = self.results_table.item(row_idx, col)
                if item:
                    item.setToolTip(tooltip_text)

            self.status_label.setText(
                f"Đã nhận từ Chrome: {product_data.product_name} ({len(product_data.images)} ảnh)"
            )

    def _with_product_folder(self, product_data: BridgeProductData) -> BridgeProductData:
        """Return the same product model with its desktop-owned folder attached."""
        product_folder = ensure_product_folder(
            self.output_folder_input.text().strip(),
            product_data.product_name,
            product_data.shop_id,
            product_data.item_id,
        )
        return replace(product_data, product_folder=product_folder)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure the queue and bridge server stop cleanly on window close."""
        self.queue_manager.cancel_batch()
        self.bridge_server.stop_server()
        super().closeEvent(event)
