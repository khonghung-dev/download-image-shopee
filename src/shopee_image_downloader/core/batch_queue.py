"""Deterministic batch orchestration for Shopee Image Downloader."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import logging
import uuid

from PySide6.QtCore import QObject, QTimer, Signal

from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.error_policy import (
    AppError,
    ErrorCategory,
    ErrorStage,
    RetryPolicy,
    classify_error_code,
    error_from_exception,
)

logger = logging.getLogger(__name__)

DEFAULT_ITEM_TIMEOUT_MS: int = 35000


class QueueState(str, Enum):
    """Overall state of the single active batch execution."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED_VERIFICATION = "PAUSED_VERIFICATION"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ItemState(str, Enum):
    """Lifecycle state of one immutable queue input."""

    PENDING = "PENDING"
    OPENING_PRODUCT = "OPENING_PRODUCT"
    WAITING_EXTRACTION = "WAITING_EXTRACTION"
    WAITING_RETRY = "WAITING_RETRY"
    CREATING_FOLDER = "CREATING_FOLDER"
    DOWNLOADING = "DOWNLOADING"
    SUCCESS = "SUCCESS"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_ITEM_STATES: frozenset[ItemState] = frozenset(
    {
        ItemState.SUCCESS,
        ItemState.SKIPPED_DUPLICATE,
        ItemState.COMPLETED_WITH_ERRORS,
        ItemState.FAILED,
        ItemState.CANCELLED,
    }
)

_ALLOWED_ITEM_TRANSITIONS: dict[ItemState, frozenset[ItemState]] = {
    ItemState.PENDING: frozenset(
        {ItemState.OPENING_PRODUCT, ItemState.CANCELLED}
    ),
    ItemState.OPENING_PRODUCT: frozenset(
        {
            ItemState.WAITING_EXTRACTION,
            ItemState.WAITING_RETRY,
            ItemState.CREATING_FOLDER,
            ItemState.SKIPPED_DUPLICATE,
            ItemState.FAILED,
            ItemState.CANCELLED,
        }
    ),
    ItemState.WAITING_EXTRACTION: frozenset(
        {
            ItemState.OPENING_PRODUCT,
            ItemState.WAITING_RETRY,
            ItemState.CREATING_FOLDER,
            ItemState.SKIPPED_DUPLICATE,
            ItemState.FAILED,
            ItemState.CANCELLED,
        }
    ),
    ItemState.WAITING_RETRY: frozenset(
        {
            ItemState.OPENING_PRODUCT,
            ItemState.FAILED,
            ItemState.CANCELLED,
        }
    ),
    ItemState.CREATING_FOLDER: frozenset(
        {
            ItemState.DOWNLOADING,
            ItemState.FAILED,
            ItemState.CANCELLED,
        }
    ),
    ItemState.DOWNLOADING: frozenset(
        {
            ItemState.SUCCESS,
            ItemState.COMPLETED_WITH_ERRORS,
            ItemState.FAILED,
            ItemState.CANCELLED,
        }
    ),
    ItemState.SUCCESS: frozenset(),
    ItemState.SKIPPED_DUPLICATE: frozenset(),
    ItemState.COMPLETED_WITH_ERRORS: frozenset(),
    ItemState.FAILED: frozenset(),
    ItemState.CANCELLED: frozenset(),
}


STATUS_DISPLAY_NAVIGATING: str = "Đang mở sản phẩm"
STATUS_DISPLAY_WAITING: str = "Đang chờ Shopee tải"
STATUS_DISPLAY_SCANNING: str = "Đang quét toàn bộ ảnh"
STATUS_DISPLAY_CREATING_FOLDER: str = "Đang tạo thư mục"
STATUS_DISPLAY_DOWNLOADING: str = "Đang tải ảnh"
STATUS_DISPLAY_SUCCESS: str = "Đã tải ảnh"
STATUS_DISPLAY_SKIPPED_DUPLICATE: str = "Trùng - đã bỏ qua"
STATUS_DISPLAY_VERIFICATION: str = "Shopee yêu cầu xác minh"
STATUS_DISPLAY_TIMEOUT: str = "Hết thời gian chờ Shopee."
STATUS_DISPLAY_FAILED: str = "Không thể tải trang"
STATUS_DISPLAY_CANCELLED: str = "Đã hủy"


@dataclass
class QueueItem:
    """One queued input with stable identity and mutable lifecycle fields."""

    request_id: str
    row_idx: int
    input_url: str
    state: ItemState = ItemState.PENDING
    stage: str = ""
    product_data: BridgeProductData | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_stage: ErrorStage | None = None
    attempt: int = 1
    max_attempts: int = 1
    next_retry_delay: float | None = None
    last_error: AppError | None = None

    @property
    def url(self) -> str:
        """Compatibility alias for the stable original input URL."""
        return self.input_url

    @property
    def is_finished(self) -> bool:
        """Return whether this item is in a terminal state."""
        return self.state in TERMINAL_ITEM_STATES


class BatchQueueManager(QObject):
    """Authoritative owner of one strictly sequential product queue."""

    state_changed = Signal(str)
    item_started = Signal(int, str, str)  # row, input_url, request_id
    item_progress = Signal(int, str, str)  # row, stage, display text
    item_download_requested = Signal(int, object)  # row, extracted product
    item_completed = Signal(int, object)  # row, completed product
    item_skipped_duplicate = Signal(int, object)  # row, reused product
    item_failed = Signal(int, str, str)  # row, error code, message
    verification_required = Signal(int, str, str)
    progress_updated = Signal(int, int)  # finalized, total
    batch_finished = Signal(int, int, list)  # success, failed, item snapshot
    send_open_product_requested = Signal(str, str)
    send_cancel_requested = Signal(str)
    cancel_download_requested = Signal(str)

    def __init__(
        self,
        item_timeout_ms: int = DEFAULT_ITEM_TIMEOUT_MS,
        retry_policy: RetryPolicy | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.item_timeout_ms = item_timeout_ms
        self.retry_policy = retry_policy or RetryPolicy.product_default()
        self._state = QueueState.IDLE
        self._items: list[QueueItem] = []
        self._current_index = -1
        self._known_request_ids: set[str] = set()
        self._reusable_products_by_key: dict[str, BridgeProductData] = {}

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_item_timeout)

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._on_retry_timeout)

    @property
    def state(self) -> QueueState:
        """Return the overall queue state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Return whether normal processing callbacks may advance the queue."""
        return self._state == QueueState.RUNNING

    @property
    def is_active(self) -> bool:
        """Return whether a batch owns the UI, including pause/cancellation."""
        return self._state in {
            QueueState.RUNNING,
            QueueState.PAUSED_VERIFICATION,
            QueueState.CANCELLING,
        }

    @property
    def is_paused_for_verification(self) -> bool:
        """Return whether the current product awaits user verification."""
        return self._state == QueueState.PAUSED_VERIFICATION

    @property
    def total_count(self) -> int:
        """Return the stable number of queued inputs."""
        return len(self._items)

    @property
    def items(self) -> tuple[QueueItem, ...]:
        """Return an immutable view of the ordered queue container."""
        return tuple(self._items)

    @property
    def current_item(self) -> QueueItem | None:
        """Return the one current item, if an index is active."""
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return None

    def is_known_request(self, request_id: str | None) -> bool:
        """Return whether a request ID was issued by this manager this session."""
        return bool(request_id and request_id in self._known_request_ids)

    def get_finished_count(self) -> int:
        """Return the number of finalized queue items."""
        return sum(item.is_finished for item in self._items)

    def get_success_count(self) -> int:
        """Return products that completed the image loop under 007B semantics."""
        return sum(
            item.state in {ItemState.SUCCESS, ItemState.COMPLETED_WITH_ERRORS}
            for item in self._items
        )

    def get_fail_count(self) -> int:
        """Return product-level failures, excluding cancellation."""
        return sum(item.state == ItemState.FAILED for item in self._items)

    def get_duplicate_count(self) -> int:
        """Return same-batch inputs handled by a prior successful product."""
        return sum(
            item.state == ItemState.SKIPPED_DUPLICATE for item in self._items
        )

    def get_cancelled_count(self) -> int:
        """Return cancelled current and pending items."""
        return sum(item.state == ItemState.CANCELLED for item in self._items)

    def _set_state(self, new_state: QueueState) -> None:
        if self._state == new_state:
            return
        self._state = new_state
        logger.info("BatchQueueManager state -> %s", new_state.value)
        self.state_changed.emit(new_state.value)

    @staticmethod
    def _transition_item(item: QueueItem, new_state: ItemState) -> bool:
        """Apply one validated item transition or log and reject it."""
        if new_state == item.state:
            return True
        if new_state not in _ALLOWED_ITEM_TRANSITIONS[item.state]:
            logger.warning(
                "Bỏ qua chuyển trạng thái không hợp lệ cho %s: %s -> %s",
                item.request_id,
                item.state.value,
                new_state.value,
            )
            return False
        item.state = new_state
        return True

    def start_batch(self, valid_items: list[tuple[int, str]]) -> bool:
        """Create and start one ordered queue from a snapshot of valid inputs."""
        if self.is_active:
            logger.warning("Không thể bắt đầu batch mới khi batch cũ đang chạy")
            return False

        input_snapshot = tuple(valid_items)
        if not input_snapshot:
            logger.warning("Danh sách items rỗng")
            return False

        new_items: list[QueueItem] = []
        for row_idx, input_url in input_snapshot:
            request_id = f"req-{uuid.uuid4().hex[:12]}"
            new_items.append(
                QueueItem(
                    request_id=request_id,
                    row_idx=row_idx,
                    input_url=str(input_url),
                    max_attempts=self.retry_policy.max_attempts,
                )
            )
            self._known_request_ids.add(request_id)

        self._items = new_items
        self._reusable_products_by_key.clear()
        self._current_index = 0
        self._set_state(QueueState.RUNNING)
        self.progress_updated.emit(0, len(self._items))
        self._process_current_item()
        return True

    def _process_current_item(self, *, verification_resume: bool = False) -> None:
        """Dispatch current once, except an explicit verification resume."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if item is None:
            self._finish_batch()
            return

        if verification_resume:
            if item.state not in {
                ItemState.WAITING_EXTRACTION,
                ItemState.WAITING_RETRY,
            }:
                logger.warning(
                    "Không thể gửi lại %s từ trạng thái %s",
                    item.request_id,
                    item.state.value,
                )
                return
        elif item.state != ItemState.PENDING:
            logger.warning(
                "Bỏ qua dispatch lặp lại cho %s ở trạng thái %s",
                item.request_id,
                item.state.value,
            )
            return

        if not self._transition_item(item, ItemState.OPENING_PRODUCT):
            return
        item.stage = "opening_product"
        item.error_code = None
        item.error_message = None
        item.error_stage = None
        item.next_retry_delay = None
        logger.info(
            "Bắt đầu sản phẩm [%d/%d]: row=%d, req=%s, attempt=%d/%d",
            self._current_index + 1,
            len(self._items),
            item.row_idx,
            item.request_id,
            item.attempt,
            item.max_attempts,
        )
        self.item_started.emit(item.row_idx, item.input_url, item.request_id)
        self.item_progress.emit(
            item.row_idx,
            item.stage,
            STATUS_DISPLAY_NAVIGATING,
        )
        self.send_open_product_requested.emit(item.request_id, item.input_url)
        if (
            self.item_timeout_ms > 0
            and self._state == QueueState.RUNNING
            and item is self.current_item
            and item.state
            in {ItemState.OPENING_PRODUCT, ItemState.WAITING_EXTRACTION}
        ):
            self._timeout_timer.start(self.item_timeout_ms)

    def handle_process_progress(self, request_id: str, stage: str) -> None:
        """Accept correlated extraction progress without allowing regression."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if item is None or item.request_id != request_id:
            logger.debug("Bỏ qua process_progress cũ/lệch: %s", request_id)
            return
        if item.state not in {
            ItemState.OPENING_PRODUCT,
            ItemState.WAITING_EXTRACTION,
        }:
            logger.debug(
                "Bỏ qua process_progress %s trong trạng thái %s",
                request_id,
                item.state.value,
            )
            return

        display_text = STATUS_DISPLAY_WAITING
        normalized_stage = stage
        if stage == "navigating":
            if item.state == ItemState.WAITING_EXTRACTION:
                logger.debug("Bỏ qua acknowledgement navigating đến muộn")
                return
            display_text = STATUS_DISPLAY_NAVIGATING
        elif stage == "waiting_page":
            display_text = STATUS_DISPLAY_WAITING
            self._transition_item(item, ItemState.WAITING_EXTRACTION)
        elif stage == "scanning_gallery":
            display_text = STATUS_DISPLAY_SCANNING
            self._transition_item(item, ItemState.WAITING_EXTRACTION)
        elif stage == "complete":
            normalized_stage = "waiting_result"
            display_text = STATUS_DISPLAY_WAITING
            self._transition_item(item, ItemState.WAITING_EXTRACTION)

        item.stage = normalized_stage
        self.item_progress.emit(item.row_idx, normalized_stage, display_text)

    def handle_product_result(self, product_data: BridgeProductData) -> None:
        """Accept one correlated extraction result and request its worker pipeline."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if item is None or product_data.request_id != item.request_id:
            logger.warning(
                "Bỏ qua product_result cũ/thiếu request_id: %s (hiện tại: %s)",
                product_data.request_id,
                item.request_id if item else None,
            )
            return
        if item.state not in {
            ItemState.OPENING_PRODUCT,
            ItemState.WAITING_EXTRACTION,
        }:
            logger.debug(
                "Bỏ qua product_result lặp lại cho %s ở trạng thái %s",
                item.request_id,
                item.state.value,
            )
            return
        if (
            product_data.image_count is not None
            and product_data.image_count != len(product_data.images)
        ):
            logger.error(
                "Lỗi toàn vẹn ảnh cho %s: image_count=%s, images=%d",
                item.request_id,
                product_data.image_count,
                len(product_data.images),
            )
            self.handle_process_error(
                item.request_id,
                item.input_url,
                "PROTOCOL_INTEGRITY_ERROR",
                "Lỗi đồng bộ dữ liệu ảnh",
            )
            return

        try:
            product_key = product_data.product_key
        except ValueError as exc:
            self.handle_process_error(
                item.request_id,
                item.input_url,
                "MALFORMED_PRODUCT_RESULT",
                str(exc),
            )
            return

        self._timeout_timer.stop()
        reusable = self._reusable_products_by_key.get(product_key)
        if reusable is not None:
            if not self._transition_item(item, ItemState.SKIPPED_DUPLICATE):
                return
            item.stage = "skipped_duplicate"
            item.product_data = replace(
                product_data,
                images=list(product_data.images),
                product_folder=reusable.product_folder,
                download_result=reusable.download_result,
            )
            logger.info(
                "Bỏ qua sản phẩm trùng trong batch: req=%s product=%s folder=%s",
                item.request_id,
                product_key,
                reusable.product_folder,
            )
            self.item_skipped_duplicate.emit(item.row_idx, item.product_data)
            self.progress_updated.emit(
                self.get_finished_count(), len(self._items)
            )
            self._advance_queue(item.request_id)
            return

        if not self._transition_item(item, ItemState.CREATING_FOLDER):
            return

        product_snapshot = replace(
            product_data,
            images=list(product_data.images),
            input_url=item.input_url,
            product_folder=None,
            download_result=None,
        )
        item.stage = "creating_folder"
        item.product_data = product_snapshot
        logger.info(
            "Nhận model req=%s, product=%s, images=%d",
            item.request_id,
            product_snapshot.product_key,
            len(product_snapshot.images),
        )
        self.item_progress.emit(
            item.row_idx,
            item.stage,
            STATUS_DISPLAY_CREATING_FOLDER,
        )
        self.item_download_requested.emit(item.row_idx, product_snapshot)

    def handle_product_folder_ready(self, product_data: BridgeProductData) -> None:
        """Enter downloading after the worker creates the correlated folder."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if not self._matches_product(item, product_data, require_folder=False):
            logger.warning("Bỏ qua folder_ready cũ/lệch")
            return
        if item is None or item.state != ItemState.CREATING_FOLDER:
            return
        if product_data.product_folder is None:
            self.handle_pipeline_failure(
                product_data,
                "PRODUCT_FOLDER_ERROR",
                "Không thể tạo thư mục sản phẩm.",
            )
            return
        if not self._transition_item(item, ItemState.DOWNLOADING):
            return

        item.stage = "downloading"
        item.product_data = replace(
            product_data,
            images=list(product_data.images),
            download_result=None,
        )
        self.item_progress.emit(
            item.row_idx,
            item.stage,
            f"{STATUS_DISPLAY_DOWNLOADING} 0/{len(product_data.images)}",
        )

    def handle_download_progress(
        self,
        product_data: BridgeProductData,
        completed: int,
        total: int,
    ) -> None:
        """Accept progress only for the owned request, product, and folder."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if (
            item is None
            or item.state != ItemState.DOWNLOADING
            or not self._matches_product(item, product_data, require_folder=True)
        ):
            logger.debug("Bỏ qua tiến độ tải ảnh cũ/lệch")
            return
        expected_total = len(item.product_data.images) if item.product_data else -1
        if total != expected_total or completed < 0 or completed > total:
            logger.warning(
                "Bỏ qua tiến độ tải ảnh không hợp lệ cho %s: %d/%d",
                item.request_id,
                completed,
                total,
            )
            return
        self.item_progress.emit(
            item.row_idx,
            "downloading",
            f"{STATUS_DISPLAY_DOWNLOADING} {completed}/{total}",
        )

    def handle_download_result(self, product_data: BridgeProductData) -> None:
        """Finalize only after the correlated worker is fully cleaned."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if (
            item is None
            or item.state != ItemState.DOWNLOADING
            or not self._matches_product(item, product_data, require_folder=True)
        ):
            logger.warning("Bỏ qua kết quả tải ảnh cũ/lệch")
            return

        result = product_data.download_result
        if not self._download_result_matches_product(product_data):
            self.handle_pipeline_failure(
                product_data,
                "IMAGE_DOWNLOAD_ERROR",
                "Kết quả tải ảnh không đầy đủ.",
            )
            return

        new_state = (
            ItemState.COMPLETED_WITH_ERRORS
            if result.failed
            else ItemState.SUCCESS
        )
        if not self._transition_item(item, new_state):
            return
        item.stage = "complete"
        item.product_data = replace(
            product_data,
            images=list(product_data.images),
        )
        if new_state == ItemState.SUCCESS:
            self._reusable_products_by_key[
                item.product_data.product_key
            ] = item.product_data
        self.item_completed.emit(item.row_idx, item.product_data)
        self.progress_updated.emit(self.get_finished_count(), len(self._items))
        self._advance_queue(item.request_id)

    def handle_pipeline_failure(
        self,
        product_data: BridgeProductData,
        error_code: str,
        message: str,
    ) -> None:
        """Finalize a correlated folder/downloader failure and continue."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if (
            item is None
            or item.state not in {
                ItemState.CREATING_FOLDER,
                ItemState.DOWNLOADING,
            }
            or not self._matches_product(
                item,
                product_data,
                require_folder=item.state == ItemState.DOWNLOADING,
            )
        ):
            logger.warning("Bỏ qua lỗi worker cũ/lệch: %s", error_code)
            return
        stage = (
            ErrorStage.FOLDER
            if item.state == ItemState.CREATING_FOLDER
            else ErrorStage.DOWNLOAD
        )
        self._fail_current_item(
            classify_error_code(
                error_code,
                stage=stage,
                technical_message=message,
            )
        )

    def handle_download_failure(self, request_id: str, message: str) -> None:
        """Handle a synchronous controller start failure."""
        item = self.current_item
        if (
            self._state != QueueState.RUNNING
            or item is None
            or item.request_id != request_id
            or item.state != ItemState.CREATING_FOLDER
        ):
            return
        self._fail_current_item(
            classify_error_code(
                "INTERNAL_ERROR",
                stage=ErrorStage.DOWNLOAD,
                technical_message=message,
            )
        )

    def handle_process_error(
        self,
        request_id: str,
        url: str,
        error_code: str,
        message: str,
    ) -> None:
        """Handle one correlated extraction failure or verification challenge."""
        if self._state not in {
            QueueState.RUNNING,
            QueueState.PAUSED_VERIFICATION,
        }:
            return
        item = self.current_item
        if item is None or item.request_id != request_id:
            logger.debug("Bỏ qua process_error cũ/lệch: %s", request_id)
            return
        if item.state not in {
            ItemState.OPENING_PRODUCT,
            ItemState.WAITING_EXTRACTION,
        }:
            logger.debug(
                "Bỏ qua process_error trong trạng thái %s", item.state.value
            )
            return

        self._timeout_timer.stop()
        error = classify_error_code(
            error_code,
            stage=ErrorStage.EXTRACTION,
            technical_message=message,
        )
        if error.category == ErrorCategory.USER_ACTION_REQUIRED:
            if item.state == ItemState.OPENING_PRODUCT:
                self._transition_item(item, ItemState.WAITING_EXTRACTION)
            item.stage = "waiting_verification"
            item.error_code = error.error_code
            item.error_message = error.user_message
            item.error_stage = error.stage
            item.last_error = error
            self._set_state(QueueState.PAUSED_VERIFICATION)
            self.verification_required.emit(
                item.row_idx,
                url,
                item.error_message,
            )
            return

        if self.retry_policy.should_retry(error, item.attempt):
            self._schedule_retry(error)
            return
        self._fail_current_item(error)

    def resume_verification(self) -> bool:
        """Explicitly redispatch the same request after verification."""
        if self._state != QueueState.PAUSED_VERIFICATION:
            return False
        item = self.current_item
        if item is None or item.state != ItemState.WAITING_EXTRACTION:
            logger.warning("Không có item xác minh hợp lệ để tiếp tục")
            return False
        self._set_state(QueueState.RUNNING)
        self._process_current_item(verification_resume=True)
        return True

    def cancel_batch(self) -> bool:
        """Begin deterministic cooperative cancellation of the active batch."""
        if self._state not in {
            QueueState.RUNNING,
            QueueState.PAUSED_VERIFICATION,
        }:
            return False

        logger.info("Yêu cầu hủy batch từ người dùng")
        self._timeout_timer.stop()
        self._retry_timer.stop()
        self._set_state(QueueState.CANCELLING)
        item = self.current_item

        if item is not None and not item.is_finished:
            self.send_cancel_requested.emit(item.request_id)

        for queued_item in self._items[self._current_index + 1 :]:
            self._cancel_item(queued_item)

        if item is None or item.is_finished:
            self._finish_cancelled_batch()
            return True

        if item.state in {
            ItemState.CREATING_FOLDER,
            ItemState.DOWNLOADING,
        }:
            self.cancel_download_requested.emit(item.request_id)
            return True

        self._cancel_item(item)
        self._finish_cancelled_batch()
        return True

    def handle_download_cancelled(self, product_data: BridgeProductData) -> None:
        """Finish cancellation after the owned worker exits cleanly."""
        if self._state != QueueState.CANCELLING:
            return
        item = self.current_item
        if not self._matches_product(
            item,
            product_data,
            require_folder=bool(
                item
                and item.product_data
                and item.product_data.product_folder is not None
            ),
        ):
            logger.warning("Bỏ qua callback hủy worker cũ/lệch")
            return
        if item is not None and not item.is_finished:
            self._cancel_item(item)
        self._finish_cancelled_batch()

    def handle_internal_failure(
        self,
        request_id: str | None,
        stage: ErrorStage,
        exc: BaseException,
    ) -> None:
        """Turn one unexpected boundary exception into a controlled failure."""
        item = self.current_item
        if (
            self._state != QueueState.RUNNING
            or item is None
            or item.request_id != request_id
            or item.is_finished
        ):
            return
        logger.exception(
            "Lỗi queue ngoài dự kiến: req=%s row=%d attempt=%d stage=%s",
            item.request_id,
            item.row_idx,
            item.attempt,
            stage.value,
        )
        self._timeout_timer.stop()
        self._retry_timer.stop()
        self._fail_current_item(
            error_from_exception(exc, stage=stage, default_code="INTERNAL_ERROR")
        )

    def _fail_current_item(self, error: AppError) -> None:
        item = self.current_item
        if item is None or not self._transition_item(item, ItemState.FAILED):
            return
        item.stage = "failed"
        item.error_code = error.error_code
        item.error_message = error.user_message
        item.error_stage = error.stage
        item.last_error = error
        item.next_retry_delay = None
        logger.warning(
            "Item %d thất bại: req=%s code=%s category=%s stage=%s "
            "attempt=%d/%d technical=%s",
            item.row_idx + 1,
            item.request_id,
            error.error_code,
            error.category.value,
            error.stage.value,
            item.attempt,
            item.max_attempts,
            error.technical_message,
        )
        self.item_failed.emit(
            item.row_idx,
            error.error_code,
            error.user_message,
        )
        self.progress_updated.emit(self.get_finished_count(), len(self._items))
        self._advance_queue(item.request_id)

    def _cancel_item(self, item: QueueItem) -> None:
        if item.is_finished or not self._transition_item(item, ItemState.CANCELLED):
            return
        item.stage = "cancelled"
        item.error_code = "CANCELLED"
        item.error_message = STATUS_DISPLAY_CANCELLED
        item.error_stage = ErrorStage.CANCEL
        item.next_retry_delay = None
        item.last_error = classify_error_code(
            "CANCELLED",
            stage=ErrorStage.CANCEL,
            technical_message="User cancelled the batch",
        )
        self.item_failed.emit(
            item.row_idx,
            item.error_code,
            item.error_message,
        )

    def _on_item_timeout(self) -> None:
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if item is None or item.state not in {
            ItemState.OPENING_PRODUCT,
            ItemState.WAITING_EXTRACTION,
        }:
            return
        logger.warning(
            "Hết thời gian xử lý (%dms) cho item %d",
            self.item_timeout_ms,
            item.row_idx + 1,
        )
        error = classify_error_code(
            "TIMEOUT",
            stage=ErrorStage.EXTRACTION,
            technical_message=(
                f"Desktop extraction timeout after {self.item_timeout_ms}ms"
            ),
        )
        if self.retry_policy.should_retry(error, item.attempt):
            self._schedule_retry(error)
            return
        self._fail_current_item(error)

    def _schedule_retry(self, error: AppError) -> None:
        """Move the same logical item into event-driven extraction backoff."""
        item = self.current_item
        if (
            item is None
            or item.state
            not in {ItemState.OPENING_PRODUCT, ItemState.WAITING_EXTRACTION}
            or not self._transition_item(item, ItemState.WAITING_RETRY)
        ):
            return
        delay = self.retry_policy.get_delay(item.attempt, error)
        item.stage = "waiting_retry"
        item.error_code = error.error_code
        item.error_message = error.user_message
        item.error_stage = error.stage
        item.last_error = error
        item.next_retry_delay = delay
        next_attempt = item.attempt + 1
        logger.warning(
            "Chờ thử lại: req=%s row=%d code=%s stage=%s attempt=%d/%d "
            "delay=%.3fs technical=%s",
            item.request_id,
            item.row_idx,
            error.error_code,
            error.stage.value,
            item.attempt,
            item.max_attempts,
            delay,
            error.technical_message,
        )
        self.item_progress.emit(
            item.row_idx,
            item.stage,
            f"Đang thử lại {next_attempt}/{item.max_attempts}...",
        )
        self._retry_timer.start(max(0, round(delay * 1000)))

    def _on_retry_timeout(self) -> None:
        """Start the next transport generation for the same queue item."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if item is None or item.state != ItemState.WAITING_RETRY:
            return
        item.attempt += 1
        item.request_id = f"req-{uuid.uuid4().hex[:12]}"
        self._known_request_ids.add(item.request_id)
        self._process_current_item(verification_resume=True)

    def _advance_queue(self, finalized_request_id: str) -> None:
        """Advance exactly once from the current terminal item."""
        if self._state != QueueState.RUNNING:
            return
        item = self.current_item
        if (
            item is None
            or item.request_id != finalized_request_id
            or not item.is_finished
        ):
            logger.warning("Bỏ qua advance không hợp lệ: %s", finalized_request_id)
            return
        self._current_index += 1
        if self._current_index < len(self._items):
            self._process_current_item()
        else:
            self._finish_batch()

    def _finish_batch(self) -> None:
        self._timeout_timer.stop()
        self._retry_timer.stop()
        if self._state != QueueState.RUNNING:
            return
        success_count = self.get_success_count()
        fail_count = self.get_fail_count()
        logger.info(
            "Hoàn tất batch: %d thành công, %d trùng, %d thất bại, "
            "%d đã hủy / %d",
            success_count,
            self.get_duplicate_count(),
            fail_count,
            self.get_cancelled_count(),
            len(self._items),
        )
        self._set_state(QueueState.COMPLETED)
        self.batch_finished.emit(
            success_count,
            fail_count,
            list(self._items),
        )
        self._set_state(QueueState.IDLE)

    def _finish_cancelled_batch(self) -> None:
        self._timeout_timer.stop()
        self._retry_timer.stop()
        if self._state != QueueState.CANCELLING:
            return
        self.progress_updated.emit(self.get_finished_count(), len(self._items))
        self._set_state(QueueState.CANCELLED)
        self.batch_finished.emit(
            self.get_success_count(),
            self.get_fail_count(),
            list(self._items),
        )
        self._set_state(QueueState.IDLE)

    @staticmethod
    def _matches_product(
        item: QueueItem | None,
        product_data: BridgeProductData,
        *,
        require_folder: bool,
    ) -> bool:
        """Correlate request, identity, images, and optionally folder."""
        if item is None or item.product_data is None:
            return False
        expected = item.product_data
        if (
            product_data.request_id != item.request_id
            or product_data.product_key != expected.product_key
            or product_data.product_name != expected.product_name
            or list(product_data.images) != list(expected.images)
        ):
            return False
        if require_folder:
            return (
                expected.product_folder is not None
                and product_data.product_folder == expected.product_folder
            )
        return True

    @staticmethod
    def _download_result_matches_product(
        product_data: BridgeProductData,
    ) -> bool:
        """Validate aggregate counters and ordered per-image ownership."""
        result = product_data.download_result
        if result is None or result.total != len(product_data.images):
            return False
        if result.successful + result.failed + result.skipped != result.total:
            return False
        if len(result.items) != result.total:
            return False
        return all(
            image_result.index == index
            and image_result.source_url == product_data.images[index - 1]
            for index, image_result in enumerate(result.items, start=1)
        )
