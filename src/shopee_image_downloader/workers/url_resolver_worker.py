"""Background worker for asynchronous Shopee URL resolution."""

from PySide6.QtCore import QObject, QThread, Signal
from shopee_image_downloader.core.url_resolver import ResolvedUrl, ShopeeUrlResolver


class UrlResolverWorker(QThread):
    """QThread worker that resolves a queue of Shopee URLs without blocking the UI thread."""

    # Signals
    # row_index, original_url
    item_started = Signal(int, str)
    # row_index, ResolvedUrl object
    item_resolved = Signal(int, object)
    # completed_count, total_count
    progress_updated = Signal(int, int)
    # list of ResolvedUrl objects
    batch_finished = Signal(list)

    def __init__(
        self,
        items: list[tuple[int, str]],
        resolver: ShopeeUrlResolver | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.items = items
        self.resolver = resolver or ShopeeUrlResolver()
        self._is_cancelled: bool = False

    def cancel(self) -> None:
        """Request cancellation / interruption of the running batch."""
        self._is_cancelled = True
        self.requestInterruption()

    def run(self) -> None:
        """Execute URL resolution sequentially across all items in the queue."""
        results: list[ResolvedUrl] = []
        total_count = len(self.items)

        for completed_idx, (row_idx, url) in enumerate(self.items, start=1):
            if self.isInterruptionRequested() or self._is_cancelled:
                break

            self.item_started.emit(row_idx, url)

            try:
                result = self.resolver.resolve_url(url)
            except Exception as e:
                result = ResolvedUrl(
                    original_url=url,
                    error=f"Lỗi worker: {e}",
                )

            results.append(result)
            self.item_resolved.emit(row_idx, result)
            self.progress_updated.emit(completed_idx, total_count)

        self.batch_finished.emit(results)
