"""Batch URL queue orchestration and state management for Shopee Image Downloader."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import uuid

from PySide6.QtCore import QObject, QTimer, Signal

from shopee_image_downloader.core.bridge_protocol import BridgeProductData

logger = logging.getLogger(__name__)

# Default timeout per queue item (in milliseconds)
DEFAULT_ITEM_TIMEOUT_MS: int = 35000


class QueueState(str, Enum):
    """Overall state of the batch queue manager."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED_VERIFICATION = "PAUSED_VERIFICATION"
    COMPLETED = "COMPLETED"


class ItemState(str, Enum):
    """Lifecycle state of an individual item in the queue."""

    PENDING = "PENDING"
    NAVIGATING = "NAVIGATING"
    SCANNING = "SCANNING"
    DOWNLOADING = "DOWNLOADING"
    SUCCESS = "SUCCESS"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


# User-facing status labels
STATUS_DISPLAY_NAVIGATING: str = "Đang mở sản phẩm"
STATUS_DISPLAY_WAITING: str = "Đang chờ Shopee tải"
STATUS_DISPLAY_SCANNING: str = "Đang quét toàn bộ ảnh"
STATUS_DISPLAY_DOWNLOADING: str = "Đang tải ảnh"
STATUS_DISPLAY_SUCCESS: str = "Đã tải ảnh"
STATUS_DISPLAY_VERIFICATION: str = "Shopee yêu cầu xác minh"
STATUS_DISPLAY_TIMEOUT: str = "Hết thời gian xử lý"
STATUS_DISPLAY_FAILED: str = "Không thể tải trang"
STATUS_DISPLAY_CANCELLED: str = "Đã hủy"


@dataclass
class QueueItem:
    """Represents a single queued URL item."""

    request_id: str
    row_idx: int
    url: str
    state: ItemState = ItemState.PENDING
    stage: str = ""
    product_data: BridgeProductData | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def is_finished(self) -> bool:
        """Return True if the item has reached any terminal state."""
        return self.state in (
            ItemState.SUCCESS,
            ItemState.COMPLETED_WITH_ERRORS,
            ItemState.FAILED,
        )


class BatchQueueManager(QObject):
    """Authoritative owner of the batch URL queue.

    Sequences URLs one at a time to the Chrome Extension via the Native Messaging bridge,
    correlates results by request_id, tracks progress, detects Shopee verification,
    and supports pause/resume and cancellation.
    """

    state_changed = Signal(str)  # Emits new QueueState value
    item_started = Signal(int, str, str)  # (row_idx, url, request_id)
    item_progress = Signal(int, str, str)  # (row_idx, stage, display_text)
    item_download_requested = Signal(int, object)  # (row_idx, BridgeProductData)
    item_completed = Signal(int, object)  # (row_idx, BridgeProductData)
    item_failed = Signal(int, str, str)  # (row_idx, error_code, error_message)
    verification_required = Signal(int, str, str)  # (row_idx, url, message)
    progress_updated = Signal(int, int)  # (finished_count, total_count)
    batch_finished = Signal(int, int, list)  # (success_count, fail_count, items)
    send_open_product_requested = Signal(str, str)  # (request_id, url)
    send_cancel_requested = Signal(str)  # (request_id)

    def __init__(
        self,
        item_timeout_ms: int = DEFAULT_ITEM_TIMEOUT_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.item_timeout_ms = item_timeout_ms
        self._state: QueueState = QueueState.IDLE
        self._items: list[QueueItem] = []
        self._current_index: int = -1

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_item_timeout)

    @property
    def state(self) -> QueueState:
        """Return current overall queue state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Return whether queue is actively running."""
        return self._state == QueueState.RUNNING

    @property
    def is_paused_for_verification(self) -> bool:
        """Return whether queue is paused waiting for user verification."""
        return self._state == QueueState.PAUSED_VERIFICATION

    @property
    def total_count(self) -> int:
        """Return total number of items in queue."""
        return len(self._items)

    @property
    def current_item(self) -> QueueItem | None:
        """Return the item currently being processed, or None."""
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return None

    def get_finished_count(self) -> int:
        """Return number of items that have completed (SUCCESS or FAILED)."""
        return sum(1 for item in self._items if item.is_finished)

    def get_success_count(self) -> int:
        """Return products whose download phase reached a terminal result."""
        return sum(
            1
            for item in self._items
            if item.state in (ItemState.SUCCESS, ItemState.COMPLETED_WITH_ERRORS)
        )

    def get_fail_count(self) -> int:
        """Return number of failed items."""
        return sum(1 for item in self._items if item.state == ItemState.FAILED)

    def _set_state(self, new_state: QueueState) -> None:
        """Set new queue state and emit signal if changed."""
        if self._state != new_state:
            self._state = new_state
            logger.info(f"BatchQueueManager state -> {new_state.value}")
            self.state_changed.emit(new_state.value)

    def start_batch(self, valid_items: list[tuple[int, str]]) -> bool:
        """Initialize and start a sequential batch with given (row_idx, url) pairs.

        Returns False if a batch is already in progress.
        """
        if self._state in (QueueState.RUNNING, QueueState.PAUSED_VERIFICATION):
            logger.warning("Không thể bắt đầu batch mới khi batch cũ đang chạy")
            return False

        if not valid_items:
            logger.warning("Danh sách items rỗng")
            return False

        self._items.clear()

        for row_idx, url in valid_items:
            req_id = f"req-{uuid.uuid4().hex[:12]}"
            item = QueueItem(
                request_id=req_id,
                row_idx=row_idx,
                url=url,
                state=ItemState.PENDING,
            )
            self._items.append(item)

        self._current_index = 0
        self._set_state(QueueState.RUNNING)
        self.progress_updated.emit(0, len(self._items))
        self._process_current_item()
        return True

    def _process_current_item(self) -> None:
        """Dispatch the current item to the Chrome Extension and start safety timeout."""
        item = self.current_item
        if not item:
            self._finish_batch()
            return

        item.state = ItemState.NAVIGATING
        item.stage = "navigating"
        logger.info(f"Bắt đầu xử lý item [{self._current_index + 1}/{len(self._items)}]: row={item.row_idx}, req={item.request_id}")

        self.item_started.emit(item.row_idx, item.url, item.request_id)
        self.item_progress.emit(item.row_idx, "navigating", STATUS_DISPLAY_NAVIGATING)
        self.send_open_product_requested.emit(item.request_id, item.url)

        if self.item_timeout_ms > 0:
            self._timeout_timer.start(self.item_timeout_ms)

    def handle_process_progress(self, request_id: str, stage: str) -> None:
        """Handle progress notification from Chrome Extension."""
        if self._state != QueueState.RUNNING:
            return

        item = self.current_item
        if not item or item.request_id != request_id:
            logger.debug(f"Bỏ qua process_progress cho request_id không khớp: {request_id} (hiện tại: {item.request_id if item else None})")
            return

        if item.state == ItemState.DOWNLOADING:
            return

        item.stage = stage
        display_text = STATUS_DISPLAY_NAVIGATING
        if stage == "navigating":
            item.state = ItemState.NAVIGATING
            display_text = STATUS_DISPLAY_NAVIGATING
        elif stage == "waiting_page":
            item.state = ItemState.NAVIGATING
            display_text = STATUS_DISPLAY_WAITING
        elif stage == "scanning_gallery":
            item.state = ItemState.SCANNING
            display_text = STATUS_DISPLAY_SCANNING
        elif stage == "complete":
            display_text = STATUS_DISPLAY_SUCCESS

        self.item_progress.emit(item.row_idx, stage, display_text)

    def handle_product_result(self, product_data: BridgeProductData) -> None:
        """Accept extraction data and request background image downloading."""
        if self._state != QueueState.RUNNING:
            return

        item = self.current_item
        if not item:
            return

        # Correlate with request_id if available
        if product_data.request_id and product_data.request_id != item.request_id:
            logger.warning(f"Bỏ qua product_result với request_id cũ/lệch: {product_data.request_id} (hiện tại: {item.request_id})")
            return

        if item.state == ItemState.DOWNLOADING:
            logger.debug("Bỏ qua product_result lặp lại cho %s", item.request_id)
            return

        # Integrity Check: len(product_data.images) must match product_data.image_count if declared
        if product_data.image_count is not None and product_data.image_count != len(product_data.images):
            logger.error(
                f"Lỗi toàn vẹn dữ liệu ảnh: image_count={product_data.image_count} != len(images)={len(product_data.images)}"
            )
            self.handle_process_error(
                request_id=item.request_id,
                url=item.url,
                error_code="PROTOCOL_INTEGRITY_ERROR",
                message="Lỗi đồng bộ dữ liệu ảnh",
            )
            return

        self._timeout_timer.stop()

        item.state = ItemState.DOWNLOADING
        item.stage = "downloading"
        item.product_data = product_data

        logger.info(
            "[DESKTOP MODEL]\nproduct_key=%s\nstored_images=%d\ndisplayed_count=%d",
            product_data.product_key,
            len(product_data.images),
            len(product_data.images),
        )
        self.item_progress.emit(
            item.row_idx,
            "downloading",
            STATUS_DISPLAY_DOWNLOADING,
        )
        self.item_download_requested.emit(item.row_idx, product_data)

    def handle_download_result(self, product_data: BridgeProductData) -> None:
        """Finish the current item only after its image download loop completes."""
        if self._state != QueueState.RUNNING:
            return

        item = self.current_item
        if not item or item.state != ItemState.DOWNLOADING:
            return
        if product_data.request_id and product_data.request_id != item.request_id:
            logger.warning(
                "Bỏ qua kết quả tải ảnh với request_id cũ/lệch: %s",
                product_data.request_id,
            )
            return

        download_result = product_data.download_result
        if download_result is None or download_result.total != len(product_data.images):
            self.handle_download_failure(
                item.request_id,
                "Kết quả tải ảnh không đầy đủ.",
            )
            return

        item.state = (
            ItemState.COMPLETED_WITH_ERRORS
            if download_result.failed
            else ItemState.SUCCESS
        )
        item.stage = "complete"
        item.product_data = product_data

        self.item_completed.emit(item.row_idx, product_data)
        self.progress_updated.emit(self.get_finished_count(), len(self._items))
        self._advance_queue()

    def handle_download_failure(self, request_id: str, message: str) -> None:
        """Mark an unexpected product-level downloader failure and continue."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if not item or item.request_id != request_id:
            return

        item.state = ItemState.FAILED
        item.error_code = "IMAGE_DOWNLOAD_ERROR"
        item.error_message = message
        self.item_failed.emit(item.row_idx, "IMAGE_DOWNLOAD_ERROR", message)
        self.progress_updated.emit(self.get_finished_count(), len(self._items))

        self._advance_queue()

    def handle_process_error(
        self,
        request_id: str,
        url: str,
        error_code: str,
        message: str,
    ) -> None:
        """Handle process failure or verification challenge from Chrome Extension."""
        item = self.current_item
        if not item or item.request_id != request_id:
            logger.debug(f"Bỏ qua process_error cho request_id không khớp: {request_id}")
            return

        self._timeout_timer.stop()

        if error_code == "VERIFICATION_REQUIRED":
            logger.warning(f"Phát hiện yêu cầu xác minh tại item {item.row_idx + 1}")
            item.error_code = error_code
            item.error_message = message or STATUS_DISPLAY_VERIFICATION
            self._set_state(QueueState.PAUSED_VERIFICATION)
            self.verification_required.emit(item.row_idx, url, message or STATUS_DISPLAY_VERIFICATION)
            return

        # Standard error: mark as failed and continue batch
        item.state = ItemState.FAILED
        item.error_code = error_code
        item.error_message = message or STATUS_DISPLAY_FAILED

        logger.warning(f"Item {item.row_idx + 1} thất bại [{error_code}]: {message}")
        self.item_failed.emit(item.row_idx, error_code, message or STATUS_DISPLAY_FAILED)
        self.progress_updated.emit(self.get_finished_count(), len(self._items))

        self._advance_queue()

    def resume_verification(self) -> bool:
        """Resume batch processing after user manually completes verification."""
        if self._state != QueueState.PAUSED_VERIFICATION:
            logger.warning("Không thể resume khi queue không ở trạng thái PAUSED_VERIFICATION")
            return False

        item = self.current_item
        if not item:
            self._finish_batch()
            return False

        logger.info(f"Tiếp tục xử lý lại item {item.row_idx + 1} sau xác minh...")
        self._set_state(QueueState.RUNNING)
        self._process_current_item()
        return True

    def cancel_batch(self) -> None:
        """Cancel ongoing batch execution and safely abandon in-flight item."""
        if self._state not in (QueueState.RUNNING, QueueState.PAUSED_VERIFICATION):
            return

        logger.info("Yêu cầu hủy batch từ người dùng")
        self._timeout_timer.stop()

        item = self.current_item
        if item and item.state in (
            ItemState.PENDING,
            ItemState.NAVIGATING,
            ItemState.SCANNING,
            ItemState.DOWNLOADING,
        ):
            item.state = ItemState.FAILED
            item.error_code = "CANCELLED"
            item.error_message = STATUS_DISPLAY_CANCELLED
            self.item_failed.emit(item.row_idx, "CANCELLED", STATUS_DISPLAY_CANCELLED)
            self.send_cancel_requested.emit(item.request_id)

        self._set_state(QueueState.IDLE)
        self.batch_finished.emit(self.get_success_count(), self.get_fail_count(), self._items)

    def _on_item_timeout(self) -> None:
        """Handle bounded per-item safety timeout if extension stops responding."""
        if self._state != QueueState.RUNNING:
            return

        item = self.current_item
        if not item:
            return

        logger.warning(f"Hết thời gian xử lý ({self.item_timeout_ms}ms) cho item {item.row_idx + 1}")
        item.state = ItemState.FAILED
        item.error_code = "TIMEOUT"
        item.error_message = STATUS_DISPLAY_TIMEOUT

        self.item_failed.emit(item.row_idx, "TIMEOUT", STATUS_DISPLAY_TIMEOUT)
        self.progress_updated.emit(self.get_finished_count(), len(self._items))

        self._advance_queue()

    def _advance_queue(self) -> None:
        """Advance queue index and process next item or finish batch."""
        if self._state != QueueState.RUNNING:
            return

        self._current_index += 1
        if self._current_index < len(self._items):
            self._process_current_item()
        else:
            self._finish_batch()

    def _finish_batch(self) -> None:
        """Complete the batch, emit finished summary, and transition to IDLE."""
        self._timeout_timer.stop()
        success_count = self.get_success_count()
        fail_count = self.get_fail_count()
        logger.info(f"Hoàn tất batch: {success_count} thành công, {fail_count} thất bại trên tổng số {len(self._items)} items")

        self._set_state(QueueState.COMPLETED)
        self.batch_finished.emit(success_count, fail_count, list(self._items))
        self._set_state(QueueState.IDLE)
