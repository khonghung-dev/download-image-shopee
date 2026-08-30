"""Background worker for asynchronous Shopee product metadata extraction."""

import logging
from PySide6.QtCore import QObject, QThread, Signal
from shopee_image_downloader.core.browser_session import (
    PlaywrightSessionManager,
)
from shopee_image_downloader.core.metadata_extractor import (
    ProductMetadata,
    ShopeeMetadataExtractor,
)
from shopee_image_downloader.core.url_resolver import ShopeeUrlResolver

logger = logging.getLogger(__name__)


class MetadataExtractorWorker(QThread):
    """QThread worker that extracts product metadata for a batch of Shopee URLs using a shared persistent browser profile."""

    # Signals
    # row_index, original_url
    item_started = Signal(int, str)
    # row_index, status_string
    item_status_updated = Signal(int, str)
    # row_index, ProductMetadata object
    item_completed = Signal(int, object)
    # completed_count, total_count
    progress_updated = Signal(int, int)
    # list of ProductMetadata objects
    batch_finished = Signal(list)

    def __init__(
        self,
        items: list[tuple[int, str]],
        extractor: ShopeeMetadataExtractor | None = None,
        session_manager: PlaywrightSessionManager | None = None,
        resolver: ShopeeUrlResolver | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.items = items
        self.resolver = resolver or ShopeeUrlResolver()
        self.session_manager = session_manager or PlaywrightSessionManager()
        self.extractor = extractor or ShopeeMetadataExtractor(
            resolver=self.resolver,
            session_manager=self.session_manager,
        )
        self._is_cancelled: bool = False

    def cancel(self) -> None:
        """Request cancellation / interruption of the running batch."""
        self._is_cancelled = True
        self.requestInterruption()

    def run(self) -> None:
        """Execute metadata extraction sequentially across all items in the queue using a shared persistent browser."""
        results: list[ProductMetadata] = []
        total_count = len(self.items)

        # 1. Initialize persistent browser context on the worker thread
        context = self.session_manager.start_context(headless=False)
        page = (context.pages[0] if context.pages else context.new_page()) if context else None

        for completed_idx, (row_idx, raw_url) in enumerate(self.items, start=1):
            if self.isInterruptionRequested() or self._is_cancelled:
                break

            logger.info("Processing product %s/%s: %s", completed_idx, total_count, raw_url)
            self.item_started.emit(row_idx, raw_url)
            self.item_status_updated.emit(row_idx, "Đang lấy thông tin")

            def on_status_change(status_text: str) -> None:
                self.item_status_updated.emit(row_idx, status_text)

            try:
                result = self.extractor.extract(
                    raw_url,
                    page=page,
                    on_status_change=on_status_change,
                )
            except Exception as e:
                result = ProductMetadata(
                    final_url=raw_url,
                    error=f"Lỗi extractor: {e}",
                )

            results.append(result)
            self.item_completed.emit(row_idx, result)
            self.progress_updated.emit(completed_idx, total_count)

            if page is not None and context is not None:
                logger.info("Reusing authenticated context for subsequent products.")

        # 2. Clean up persistent session context at end of batch
        self.session_manager.close()
        self.batch_finished.emit(results)
