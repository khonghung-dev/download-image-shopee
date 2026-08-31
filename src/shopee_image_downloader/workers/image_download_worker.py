"""Qt worker-thread boundary for product image downloads."""

from __future__ import annotations

import logging
from pathlib import Path
import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.image_downloader import (
    DownloadCancelledError,
    ImageDownloader,
    ProductDownloadResult,
)

logger = logging.getLogger(__name__)


class ImageDownloadWorker(QObject):
    """Run one product's sequential download loop outside the GUI thread."""

    progress = Signal(int, int)  # (completed image index, total)
    finished = Signal(object)  # ProductDownloadResult
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        product_data: BridgeProductData,
        downloader: ImageDownloader,
    ) -> None:
        super().__init__()
        self._product_data = product_data
        self._downloader = downloader
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation from any thread."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        """Execute the blocking network loop in the owning QThread."""
        product_folder = self._product_data.product_folder
        if product_folder is None:
            self.failed.emit("Thư mục sản phẩm chưa sẵn sàng.")
            return

        try:
            result = self._downloader.download_product_images(
                self._product_data.images,
                product_folder,
                progress_callback=self.progress.emit,
                cancel_check=self._cancel_event.is_set,
            )
        except DownloadCancelledError:
            self.cancelled.emit()
        except (OSError, RuntimeError, ValueError):
            logger.exception(
                "Lỗi không mong đợi khi tải ảnh cho %s",
                self._product_data.product_key,
            )
            self.failed.emit("Không thể hoàn tất tải ảnh sản phẩm.")
        else:
            self.finished.emit(result)


class ImageDownloadController(QObject):
    """Own one QThread at a time and expose product-scoped Qt signals."""

    started = Signal(object)  # BridgeProductData
    progress = Signal(object, int, int)  # (product, completed index, total)
    finished = Signal(object, object)  # (product, ProductDownloadResult)
    failed = Signal(object, str)  # (product, concise message)
    cancelled = Signal(object)  # BridgeProductData

    def __init__(
        self,
        downloader: ImageDownloader | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._downloader = downloader or ImageDownloader()
        self._thread: QThread | None = None
        self._worker: ImageDownloadWorker | None = None
        self._active_product: BridgeProductData | None = None

    @property
    def is_busy(self) -> bool:
        """Return whether one product download is active or cleaning up."""
        return self._active_product is not None or self._thread is not None

    def start(self, product_data: BridgeProductData) -> bool:
        """Start one product download, returning False when already busy."""
        if self.is_busy:
            logger.warning("Bỏ qua yêu cầu tải ảnh đồng thời cho %s", product_data.product_key)
            return False

        product_folder = product_data.product_folder
        if product_folder is None or not Path(product_folder).is_dir():
            self.failed.emit(product_data, "Thư mục sản phẩm chưa sẵn sàng.")
            return False

        thread = QThread(self)
        worker = ImageDownloadWorker(product_data, self._downloader)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._active_product = product_data
        self._thread = thread
        self._worker = worker
        self.started.emit(product_data)
        thread.start()
        return True

    def cancel(self) -> None:
        """Cooperatively cancel the active image request."""
        if self._worker is not None:
            self._worker.cancel()

    @Slot(int, int)
    def _on_progress(self, index: int, total: int) -> None:
        product = self._active_product
        if product is not None:
            self.progress.emit(product, index, total)

    @Slot(object)
    def _on_finished(self, result: ProductDownloadResult) -> None:
        product = self._active_product
        if product is not None:
            self.finished.emit(product, result)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        product = self._active_product
        if product is not None:
            self.failed.emit(product, message)

    @Slot()
    def _on_cancelled(self) -> None:
        product = self._active_product
        if product is not None:
            self.cancelled.emit(product)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        self._active_product = None
