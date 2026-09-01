"""Worker-thread boundary for folder creation and product image downloads."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.error_policy import (
    AppError,
    AppErrorException,
    ErrorStage,
    classify_error_code,
    error_from_exception,
)
from shopee_image_downloader.core.image_downloader import (
    DownloadCancelledError,
    ImageDownloader,
    ProductDownloadResult,
)
from shopee_image_downloader.core.product_metadata import (
    build_product_metadata,
    write_product_metadata,
)
from shopee_image_downloader.storage.product_folder import (
    ProductFolderError,
    ensure_product_folder,
)
from shopee_image_downloader.storage.product_registry import (
    ProductIdentityRegistry,
)

logger = logging.getLogger(__name__)


@dataclass
class _DownloadRunContext:
    """Thread-shared outcome storage read only after QThread completion."""

    product: BridgeProductData
    output_root: str
    cancel_event: threading.Event
    run_event: threading.Event
    export_metadata: bool
    export_identity_marker: bool
    identity_registry: ProductIdentityRegistry
    terminal_kind: str | None = None
    result: ProductDownloadResult | None = None
    error_code: str | None = None
    error_message: str | None = None
    folder_published: bool = False


class ImageDownloadWorker(QObject):
    """Create one product folder, then run its background image pipeline."""

    folder_ready = Signal(object)
    progress = Signal(object, int, int)
    paused = Signal(object)
    metadata_started = Signal(object)
    done = Signal()

    def __init__(
        self,
        context: _DownloadRunContext,
        downloader: ImageDownloader,
    ) -> None:
        super().__init__()
        self._context = context
        self._downloader = downloader

    @Slot()
    def run(self) -> None:
        """Execute all meaningful filesystem/network work in this QThread."""
        try:
            self._raise_if_cancelled()
            try:
                product_folder = ensure_product_folder(
                    self._context.output_root,
                    self._context.product.product_name,
                    self._context.product.shop_id,
                    self._context.product.item_id,
                    create_marker=self._context.export_identity_marker,
                    registry=self._context.identity_registry,
                )
            except ProductFolderError as exc:
                logger.exception(
                    "Không thể tạo thư mục cho %s: code=%s stage=%s technical=%s",
                    self._context.product.product_key,
                    exc.error.error_code,
                    exc.error.stage.value,
                    exc.error.technical_message,
                )
                self._set_failure(exc.error)
                return

            self._context.product = replace(
                self._context.product,
                images=list(self._context.product.images),
                product_folder=product_folder,
            )
            self._raise_if_cancelled()
            self.folder_ready.emit(self._context.product)

            pause_setter = getattr(self._downloader, "set_pause_waiter", None)
            pause_controller = getattr(
                self._downloader,
                "set_pause_control",
                None,
            )
            try:
                if callable(pause_controller):
                    pause_controller(
                        lambda: not self._context.run_event.is_set(),
                        self._wait_if_paused,
                    )
                elif callable(pause_setter):
                    pause_setter(self._wait_if_paused)
                result = self._downloader.download_product_images(
                    self._context.product.images,
                    product_folder,
                    progress_callback=self._emit_progress,
                    cancel_check=self._context.cancel_event.is_set,
                )
            except DownloadCancelledError:
                self._context.terminal_kind = "cancelled"
            except AppErrorException as exc:
                logger.exception(
                    "Lỗi tải ảnh có kiểm soát cho %s: code=%s stage=%s technical=%s",
                    self._context.product.product_key,
                    exc.error.error_code,
                    exc.error.stage.value,
                    exc.error.technical_message,
                )
                self._set_failure(exc.error)
            except Exception as exc:
                logger.exception(
                    "Lỗi không mong đợi khi tải ảnh cho %s",
                    self._context.product.product_key,
                )
                self._set_failure(
                    error_from_exception(
                        exc,
                        stage=ErrorStage.DOWNLOAD,
                        default_code="INTERNAL_ERROR",
                    )
                )
            else:
                completed_product = replace(
                    self._context.product,
                    images=list(self._context.product.images),
                    download_result=result,
                )
                self._context.product = completed_product
                self._raise_if_cancelled()
                if self._context.export_metadata:
                    self.metadata_started.emit(completed_product)
                    try:
                        metadata = build_product_metadata(
                            completed_product,
                            result,
                        )
                        write_product_metadata(product_folder, metadata)
                    except AppErrorException as exc:
                        logger.exception(
                            "Không thể ghi metadata cho %s: "
                            "code=%s stage=%s technical=%s",
                            completed_product.product_key,
                            exc.error.error_code,
                            exc.error.stage.value,
                            exc.error.technical_message,
                        )
                        self._set_failure(exc.error)
                        return
                self._context.result = result
                self._context.terminal_kind = "finished"
            finally:
                if callable(pause_controller):
                    pause_controller(None, None)
                elif callable(pause_setter):
                    pause_setter(None)
        except DownloadCancelledError:
            self._context.terminal_kind = "cancelled"
        except Exception as exc:
            logger.exception(
                "Worker pipeline bị lỗi ngoài dự kiến cho %s",
                self._context.product.product_key,
            )
            self._set_failure(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="INTERNAL_ERROR",
                )
            )
        finally:
            if self._context.cancel_event.is_set():
                self._context.terminal_kind = "cancelled"
                self._context.result = None
                self._context.error_code = None
                self._context.error_message = None
            if self._context.terminal_kind is None:
                self._set_failure(
                    classify_error_code(
                        "INTERNAL_ERROR",
                        stage=ErrorStage.DOWNLOAD,
                        technical_message="Worker ended without a terminal result",
                    )
                )
            self.done.emit()

    def _emit_progress(self, completed: int, total: int) -> None:
        self.progress.emit(self._context.product, completed, total)

    def _set_failure(self, error: AppError) -> None:
        self._context.terminal_kind = "failed"
        self._context.error_code = error.error_code
        self._context.error_message = error.user_message

    def _raise_if_cancelled(self) -> None:
        if self._context.cancel_event.is_set():
            raise DownloadCancelledError("Đã hủy tải ảnh.")

    def _wait_if_paused(self) -> None:
        """Block only this worker thread at the boundary before a new image."""
        if self._context.run_event.is_set():
            return
        self.paused.emit(self._context.product)
        while not self._context.run_event.wait(timeout=0.1):
            self._raise_if_cancelled()
        self._raise_if_cancelled()


class ImageDownloadController(QObject):
    """Own and clean exactly one product pipeline QThread at a time."""

    started = Signal(object)
    folder_ready = Signal(object)
    progress = Signal(object, int, int)
    paused = Signal(object)
    metadata_started = Signal(object)
    finished = Signal(object, object)
    failed = Signal(object, str, str)
    cancelled = Signal(object)
    idle = Signal()

    def __init__(
        self,
        downloader: ImageDownloader | None = None,
        identity_registry: ProductIdentityRegistry | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._downloader = downloader or ImageDownloader()
        self._identity_registry = identity_registry or ProductIdentityRegistry()
        self._export_metadata = True
        self._export_identity_marker = True
        self._thread: QThread | None = None
        self._worker: ImageDownloadWorker | None = None
        self._context: _DownloadRunContext | None = None

    @property
    def is_busy(self) -> bool:
        """Return whether one pipeline is active or tearing down."""
        return self._context is not None or self._thread is not None

    @property
    def active_request_id(self) -> str | None:
        """Return the request owned by the active worker, if any."""
        if self._context is None:
            return None
        return self._context.product.request_id

    def start(self, product_data: BridgeProductData, output_root: str) -> bool:
        """Start one worker pipeline without doing filesystem work in the GUI."""
        if self.is_busy:
            logger.warning(
                "Bỏ qua yêu cầu tải ảnh đồng thời cho %s",
                product_data.product_key,
            )
            return False

        context = _DownloadRunContext(
            product=replace(
                product_data,
                images=list(product_data.images),
                product_folder=None,
                download_result=None,
            ),
            output_root=str(output_root),
            cancel_event=threading.Event(),
            run_event=threading.Event(),
            export_metadata=self._export_metadata,
            export_identity_marker=self._export_identity_marker,
            identity_registry=self._identity_registry,
        )
        context.run_event.set()
        thread = QThread(self)
        worker = ImageDownloadWorker(context, self._downloader)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.folder_ready.connect(self._on_folder_ready)
        worker.progress.connect(self._on_progress)
        worker.paused.connect(self._on_paused)
        worker.metadata_started.connect(self._on_metadata_started)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.destroyed.connect(self._on_thread_destroyed)

        self._context = context
        self._thread = thread
        self._worker = worker
        self.started.emit(context.product)
        thread.start()
        return True

    def set_output_options(
        self,
        *,
        export_metadata: bool,
        export_identity_marker: bool,
    ) -> bool:
        """Snapshot UI output flags for the next product pipeline."""
        if self.is_busy:
            return False
        self._export_metadata = bool(export_metadata)
        self._export_identity_marker = bool(export_identity_marker)
        return True

    def cancel(self, request_id: str | None = None) -> bool:
        """Request cooperative cancellation for the matching active pipeline."""
        context = self._context
        if context is None:
            return False
        if request_id is not None and context.product.request_id != request_id:
            logger.warning(
                "Bỏ qua yêu cầu hủy worker cũ/lệch: %s", request_id
            )
            return False
        context.cancel_event.set()
        context.run_event.set()
        return True

    def pause(self, request_id: str | None = None) -> bool:
        """Request a pause at the next image boundary for the active product."""
        context = self._context
        if context is None:
            return False
        if request_id is not None and context.product.request_id != request_id:
            return False
        context.run_event.clear()
        return True

    def resume(self, request_id: str | None = None) -> bool:
        """Wake the same paused product worker without starting a new one."""
        context = self._context
        if context is None:
            return False
        if request_id is not None and context.product.request_id != request_id:
            return False
        context.run_event.set()
        return True

    @Slot(object)
    def _on_folder_ready(self, product: BridgeProductData) -> None:
        context = self._context
        if context is None or not self._matches_context(context, product):
            logger.debug("Bỏ qua folder_ready của worker cũ")
            return
        context.product = product
        context.folder_published = True
        self.folder_ready.emit(product)

    @Slot(object, int, int)
    def _on_progress(
        self,
        product: BridgeProductData,
        completed: int,
        total: int,
    ) -> None:
        context = self._context
        if context is None or not self._matches_context(context, product):
            logger.debug("Bỏ qua progress của worker cũ")
            return
        self.progress.emit(product, completed, total)

    @Slot(object)
    def _on_paused(self, product: BridgeProductData) -> None:
        context = self._context
        if context is None or not self._matches_context(context, product):
            logger.debug("Bỏ qua paused của worker cũ")
            return
        self.paused.emit(product)

    @Slot(object)
    def _on_metadata_started(self, product: BridgeProductData) -> None:
        context = self._context
        if context is None or not self._matches_context(context, product):
            logger.debug("Bỏ qua metadata_started của worker cũ")
            return
        context.product = product
        self.metadata_started.emit(product)

    @Slot()
    def _on_thread_destroyed(self) -> None:
        """Publish the outcome only after QThread deleteLater has completed."""
        context = self._context
        self._worker = None
        self._thread = None
        self._context = None

        if context is None:
            self.idle.emit()
            return

        product = context.product
        if product.product_folder is not None and not context.folder_published:
            context.folder_published = True
            self.folder_ready.emit(product)
        if context.cancel_event.is_set() or context.terminal_kind == "cancelled":
            self.cancelled.emit(product)
        elif context.terminal_kind == "finished" and context.result is not None:
            self.finished.emit(product, context.result)
        else:
            self.failed.emit(
                product,
                context.error_code or "INTERNAL_ERROR",
                context.error_message or "Lỗi nội bộ khi xử lý sản phẩm.",
            )
        self.idle.emit()

    @staticmethod
    def _matches_context(
        context: _DownloadRunContext,
        product: BridgeProductData,
    ) -> bool:
        expected = context.product
        return (
            product.request_id == expected.request_id
            and product.product_key == expected.product_key
            and product.product_name == expected.product_name
            and list(product.images) == list(expected.images)
        )
