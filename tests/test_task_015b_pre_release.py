"""Task 015B pre-release safety, UX, and performance regressions."""

from __future__ import annotations

import re
from pathlib import Path
import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLineEdit

from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    DEFAULT_ITEM_TIMEOUT_MS,
    ItemState,
    QueueState,
)
from shopee_image_downloader.core.image_downloader import (
    DownloadCancelledError,
    DownloadConfig,
    ImageDownloader,
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
    MAX_IMAGE_DOWNLOAD_WORKERS,
)
from shopee_image_downloader.core.error_policy import (
    DEFAULT_PRODUCT_ATTEMPT_TIMEOUT_MS,
    RetryPolicy,
)
from shopee_image_downloader.core.product_metadata import (
    PRODUCT_METADATA_FILENAME,
)
from shopee_image_downloader.storage.product_folder import (
    PRODUCT_ID_MARKER_FILENAME,
    ProductFolderError,
    ensure_product_folder,
)
from shopee_image_downloader.storage.product_registry import (
    ProductIdentityRegistry,
    ProductRegistryError,
)
from shopee_image_downloader.workers.image_download_worker import (
    ImageDownloadController,
)
from shopee_image_downloader.ui.url_table import UrlTableView


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_default_product_retry_budget_is_about_thirty_seconds() -> None:
    """Model the policy without making the test sleep in real time."""
    policy = RetryPolicy.product_default()
    modeled_seconds = (
        (DEFAULT_PRODUCT_ATTEMPT_TIMEOUT_MS / 1000) * policy.max_attempts
        + sum(
            policy.get_delay(
                attempt,
                # A timeout has no Retry-After override.
                _timeout_error(),
            )
            for attempt in range(1, policy.max_attempts)
        )
    )

    assert DEFAULT_ITEM_TIMEOUT_MS == DEFAULT_PRODUCT_ATTEMPT_TIMEOUT_MS
    assert policy.max_attempts == 3
    assert 25 <= modeled_seconds <= 35
    assert modeled_seconds == 30


def test_extension_and_desktop_extraction_timeouts_stay_aligned() -> None:
    background = (
        REPOSITORY_ROOT / "chrome_extension" / "background.js"
    ).read_text(encoding="utf-8")
    match = re.search(r"PRODUCT_TIMEOUT_MS\s*=\s*(\d+)", background)

    assert match is not None
    assert int(match.group(1)) == DEFAULT_PRODUCT_ATTEMPT_TIMEOUT_MS


def test_verification_stops_timeout_without_consuming_attempt() -> None:
    manager = BatchQueueManager()
    assert manager.start_batch([(0, "https://shopee.vn/verification")])
    item = manager.current_item
    assert item is not None
    original_attempt = item.attempt

    manager.handle_process_error(
        item.request_id,
        item.input_url,
        "VERIFICATION_REQUIRED",
        "verification required",
    )

    assert manager.state == QueueState.PAUSED_VERIFICATION
    assert item.state == ItemState.WAITING_EXTRACTION
    assert item.attempt == original_attempt
    assert not manager._timeout_timer.isActive()
    assert not manager._retry_timer.isActive()


def test_user_pause_during_extraction_stops_before_worker_start() -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    worker_starts: list[BridgeProductData] = []
    manager.item_download_requested.connect(
        lambda _row, product: worker_starts.append(product)
    )
    assert manager.start_batch([(0, "https://shopee.vn/pause")])
    item = manager.current_item
    assert item is not None

    assert manager.request_user_pause()
    assert manager.state == QueueState.PAUSE_REQUESTED
    manager.handle_product_result(_product(item.request_id, "1"))

    assert manager.state == QueueState.PAUSED_USER
    assert item.state == ItemState.CREATING_FOLDER
    assert worker_starts == []

    assert manager.resume_user_pause()
    assert manager.state == QueueState.RUNNING
    assert len(worker_starts) == 1
    assert worker_starts[0].request_id == item.request_id


def test_user_pause_between_products_resumes_without_duplicate_row(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    opened_rows: list[int] = []
    manager.item_started.connect(
        lambda row, _url, _request: opened_rows.append(row)
    )
    assert manager.start_batch(
        [(0, "https://shopee.vn/a"), (1, "https://shopee.vn/b")]
    )
    item = manager.current_item
    assert item is not None
    product = _product(item.request_id, "10")
    manager.handle_product_result(product)
    product = _with_folder(product, tmp_path)
    manager.handle_product_folder_ready(product)

    assert manager.request_user_pause()
    manager.handle_download_result(_with_success_result(product))

    assert manager.state == QueueState.PAUSED_USER
    assert opened_rows == [0]
    assert len(manager.items) == 2

    assert manager.resume_user_pause()
    assert manager.state == QueueState.RUNNING
    assert manager.current_item is manager.items[1]
    assert opened_rows == [0, 1]


def test_cancel_while_user_paused_finishes_and_allows_second_batch() -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    assert manager.start_batch(
        [(0, "https://shopee.vn/a"), (1, "https://shopee.vn/b")]
    )
    item = manager.current_item
    assert item is not None
    assert manager.request_user_pause()
    manager.handle_product_result(_product(item.request_id, "20"))
    assert manager.state == QueueState.PAUSED_USER

    assert manager.cancel_batch()
    assert manager.state == QueueState.IDLE
    assert [queued.state for queued in manager.items] == [
        ItemState.CANCELLED,
        ItemState.CANCELLED,
    ]
    assert manager.start_batch([(0, "https://shopee.vn/second")])
    assert manager.state == QueueState.RUNNING


def test_verification_resume_uses_one_fresh_generation_and_ignores_stale() -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    opened: list[str] = []
    manager.send_open_product_requested.connect(
        lambda request_id, _url: opened.append(request_id)
    )
    assert manager.start_batch([(0, "https://shopee.vn/verify")])
    item = manager.current_item
    assert item is not None
    stale_request_id = item.request_id
    manager.handle_process_error(
        stale_request_id,
        item.input_url,
        "VERIFICATION_REQUIRED",
        "verification required",
    )

    assert manager.resume_verification()
    resumed_request_id = item.request_id
    assert resumed_request_id != stale_request_id
    assert item.attempt == 1
    assert opened == [stale_request_id, resumed_request_id]

    manager.handle_product_result(_product(stale_request_id, "30"))
    assert item.state == ItemState.OPENING_PRODUCT
    manager.handle_product_result(_product(resumed_request_id, "30"))
    assert item.state == ItemState.CREATING_FOLDER


class _BoundaryDownloader(ImageDownloader):
    def __init__(self) -> None:
        super().__init__()
        self.started_indexes: list[int] = []
        self.first_started = threading.Event()
        self.release_first = threading.Event()

    def download_product_images(
        self,
        images,
        product_folder,
        *,
        progress_callback=None,
        cancel_check=None,
    ) -> ProductDownloadResult:
        results: list[ImageDownloadResult] = []
        total = len(images)
        folder = Path(product_folder)
        for index, source_url in enumerate(images, start=1):
            if self._pause_waiter is not None:
                self._pause_waiter()
            if cancel_check is not None and cancel_check():
                raise RuntimeError("cancelled")
            self.started_indexes.append(index)
            if index == 1:
                self.first_started.set()
                self.release_first.wait(timeout=2)
            results.append(
                ImageDownloadResult(
                    index=index,
                    source_url=source_url,
                    target_path=folder / f"{index:02d}.jpg",
                    status=ImageDownloadStatus.SUCCESS,
                    attempts=1,
                )
            )
            if progress_callback is not None:
                progress_callback(index, total)
        return ProductDownloadResult.from_items(total, results)


def test_worker_pause_finishes_current_image_and_blocks_next(
    tmp_path: Path,
    qtbot,
) -> None:
    downloader = _BoundaryDownloader()
    controller = ImageDownloadController(downloader=downloader)
    product = BridgeProductData(
        url="https://shopee.vn/pause-boundary",
        product_name="Pause boundary",
        shop_id="40",
        item_id="50",
        images=["https://img/1.jpg", "https://img/2.jpg"],
        image_count=2,
        request_id="req-pause-boundary",
    )
    paused: list[BridgeProductData] = []
    finished: list[ProductDownloadResult] = []
    controller.paused.connect(paused.append)
    controller.finished.connect(lambda _product, result: finished.append(result))

    assert controller.start(product, str(tmp_path))
    qtbot.waitUntil(downloader.first_started.is_set, timeout=2000)
    assert controller.pause(product.request_id)
    downloader.release_first.set()
    qtbot.waitUntil(lambda: len(paused) == 1, timeout=2000)
    assert downloader.started_indexes == [1]

    assert controller.resume(product.request_id)
    qtbot.waitUntil(lambda: len(finished) == 1, timeout=3000)
    assert downloader.started_indexes == [1, 2]
    assert [item.index for item in finished[0].items] == [1, 2]


def test_marker_off_registry_reuses_exact_folder_across_runs(
    tmp_path: Path,
) -> None:
    registry = ProductIdentityRegistry(tmp_path / "app-data" / "registry.json")
    output_root = tmp_path / "downloads"
    output_root.mkdir()

    first = ensure_product_folder(
        output_root,
        "Original title",
        "70",
        "80",
        create_marker=False,
        registry=registry,
    )
    second = ensure_product_folder(
        output_root,
        "Changed title",
        "70",
        "80",
        create_marker=False,
        registry=ProductIdentityRegistry(registry.path),
    )

    assert first == second
    assert not (first / PRODUCT_ID_MARKER_FILENAME).exists()
    assert registry.path.is_file()
    assert not list(registry.path.parent.glob("*.tmp"))


def test_stale_and_corrupt_registry_recover_without_adopting_user_folder(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "downloads"
    output_root.mkdir()
    user_folder = output_root / "Product"
    user_folder.mkdir()
    registry_path = tmp_path / "app-data" / "registry.json"
    registry = ProductIdentityRegistry(registry_path)
    registry.set_folder(output_root, "90:91", "Missing")

    resolved = ensure_product_folder(
        output_root,
        "Product",
        "90",
        "91",
        create_marker=False,
        registry=registry,
    )
    assert resolved == output_root / "Product [90-91]"
    assert user_folder.is_dir()

    registry_path.write_text("{broken", encoding="utf-8")
    recovered = ensure_product_folder(
        output_root,
        "Another",
        "92",
        "93",
        create_marker=False,
        registry=ProductIdentityRegistry(registry_path),
    )
    assert recovered == output_root / "Another"
    assert ProductIdentityRegistry(registry_path).get_folder(
        output_root,
        "92:93",
    ) == "Another"


def test_marker_wins_registry_disagreement_and_is_not_deleted_when_off(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "downloads"
    output_root.mkdir()
    marker_owned = ensure_product_folder(output_root, "Marker", "101", "202")
    registry_target = output_root / "Registry"
    registry_target.mkdir()
    registry = ProductIdentityRegistry(tmp_path / "app-data" / "registry.json")
    registry.set_folder(output_root, "101:202", registry_target.name)

    resolved = ensure_product_folder(
        output_root,
        "New title",
        "101",
        "202",
        create_marker=False,
        registry=registry,
    )

    assert resolved == marker_owned
    assert (marker_owned / PRODUCT_ID_MARKER_FILENAME).read_text(
        encoding="utf-8"
    ).strip() == "101:202"
    assert registry.get_folder(output_root, "101:202") == marker_owned.name


def test_marker_off_registry_failure_does_not_publish_unmanaged_folder(
    tmp_path: Path,
) -> None:
    class _FailingRegistry(ProductIdentityRegistry):
        def set_folder(self, output_root, product_key, folder_name) -> None:
            raise ProductRegistryError("registry denied")

    with pytest.raises(ProductFolderError):
        ensure_product_folder(
            tmp_path,
            "Unsafe without registry",
            "303",
            "404",
            create_marker=False,
            registry=_FailingRegistry(tmp_path / "registry.json"),
        )

    assert not (tmp_path / "Unsafe without registry").exists()


class _ImmediateDownloader(ImageDownloader):
    def download_product_images(
        self,
        images,
        product_folder,
        *,
        progress_callback=None,
        cancel_check=None,
    ) -> ProductDownloadResult:
        folder = Path(product_folder)
        items = [
            ImageDownloadResult(
                index=index,
                source_url=source_url,
                target_path=folder / f"{index:02d}.jpg",
                status=ImageDownloadStatus.SUCCESS,
                attempts=1,
            )
            for index, source_url in enumerate(images, start=1)
        ]
        if progress_callback is not None:
            for index in range(1, len(items) + 1):
                progress_callback(index, len(items))
        return ProductDownloadResult.from_items(len(items), items)


@pytest.mark.parametrize(
    ("metadata_on", "marker_on"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_worker_optional_output_combinations(
    tmp_path: Path,
    qtbot,
    metadata_on: bool,
    marker_on: bool,
) -> None:
    output_root = tmp_path / f"downloads-{int(metadata_on)}-{int(marker_on)}"
    output_root.mkdir()
    registry = ProductIdentityRegistry(
        tmp_path / f"registry-{int(metadata_on)}-{int(marker_on)}.json"
    )
    controller = ImageDownloadController(
        downloader=_ImmediateDownloader(),
        identity_registry=registry,
    )
    assert controller.set_output_options(
        export_metadata=metadata_on,
        export_identity_marker=marker_on,
    )
    finished: list[BridgeProductData] = []
    controller.finished.connect(lambda product, _result: finished.append(product))
    product = _product(
        f"req-options-{int(metadata_on)}-{int(marker_on)}",
        f"{int(metadata_on)}{int(marker_on)}5",
    )

    assert controller.start(product, str(output_root))
    qtbot.waitUntil(lambda: len(finished) == 1, timeout=3000)
    folder = finished[0].product_folder
    assert folder is not None
    assert (folder / PRODUCT_METADATA_FILENAME).exists() is metadata_on
    assert (folder / PRODUCT_ID_MARKER_FILENAME).exists() is marker_on
    assert registry.get_folder(output_root, product.product_key) == folder.name


def test_turning_optional_outputs_off_never_deletes_existing_files(
    tmp_path: Path,
    qtbot,
) -> None:
    output_root = tmp_path / "downloads"
    output_root.mkdir()
    registry = ProductIdentityRegistry(tmp_path / "registry.json")
    controller = ImageDownloadController(
        downloader=_ImmediateDownloader(),
        identity_registry=registry,
    )
    product = _product("req-options-on", "606")
    finished: list[BridgeProductData] = []
    controller.finished.connect(lambda completed, _result: finished.append(completed))

    controller.set_output_options(
        export_metadata=True,
        export_identity_marker=True,
    )
    assert controller.start(product, str(output_root))
    qtbot.waitUntil(lambda: len(finished) == 1, timeout=3000)
    folder = finished[-1].product_folder
    assert folder is not None
    metadata_before = (folder / PRODUCT_METADATA_FILENAME).read_bytes()
    marker_before = (folder / PRODUCT_ID_MARKER_FILENAME).read_bytes()

    from dataclasses import replace

    controller.set_output_options(
        export_metadata=False,
        export_identity_marker=False,
    )
    assert controller.start(
        replace(product, request_id="req-options-off"),
        str(output_root),
    )
    qtbot.waitUntil(lambda: len(finished) == 2, timeout=3000)

    assert (folder / PRODUCT_METADATA_FILENAME).read_bytes() == metadata_before
    assert (folder / PRODUCT_ID_MARKER_FILENAME).read_bytes() == marker_before


def test_url_grid_multiline_paste_and_exact_copy(qtbot) -> None:
    view = UrlTableView()
    qtbot.addWidget(view)
    view.resize(620, 240)
    view.show()
    view.setCurrentIndex(view.url_model.index(0, 0))
    QApplication.clipboard().setText("URL A\nURL B\nURL C")

    qtbot.keyClick(view, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert view.toPlainText() == "URL A\nURL B\nURL C"

    qtbot.keyClick(view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClick(view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "URL A\nURL B\nURL C"


def test_url_grid_copy_removes_only_the_structural_blank(qtbot) -> None:
    view = UrlTableView()
    qtbot.addWidget(view)
    view.setPlainText("URL A\n\n")

    view.selectAll()
    view.copy_selection()

    assert QApplication.clipboard().text() == "URL A\n"


def test_url_grid_click_edit_delete_and_enter_navigation(qtbot) -> None:
    view = UrlTableView()
    qtbot.addWidget(view)
    view.resize(620, 240)
    view.show()
    view.setPlainText("https://shopee.vn/a\nhttps://shopee.vn/b")
    first = view.url_model.index(0, 0)
    first_position = view.visualRect(first).center()

    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=first_position)
    assert view.currentIndex() == first
    assert view.state() != QAbstractItemView.State.EditingState

    qtbot.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=first_position)
    qtbot.waitUntil(
        lambda: view.state() == QAbstractItemView.State.EditingState,
        timeout=1000,
    )
    editor = view.findChild(QLineEdit)
    assert editor is not None
    editor.selectAll()
    qtbot.keyClicks(editor, "https://shopee.vn/edited")
    qtbot.keyPress(editor, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: view.currentIndex().row() == 1, timeout=1000)
    assert view.toPlainText().splitlines()[0] == "https://shopee.vn/edited"

    view.setCurrentIndex(view.url_model.index(1, 0))
    qtbot.keyPress(view, Qt.Key.Key_Delete)
    assert view.url_model.index(1, 0).data() == ""

    last_row = view.url_model.rowCount() - 1
    last = view.url_model.index(last_row, 0)
    view.setCurrentIndex(last)
    qtbot.keyPress(view, Qt.Key.Key_F2)
    editor = view.findChild(QLineEdit)
    assert editor is not None
    qtbot.keyClicks(editor, "https://shopee.vn/new")
    qtbot.keyPress(editor, Qt.Key.Key_Return)
    qtbot.waitUntil(
        lambda: view.currentIndex().row() == last_row + 1,
        timeout=1000,
    )
    assert view.url_model.rowCount() >= last_row + 2


class _ConcurrentResponse:
    def __init__(
        self,
        body: bytes,
        content_type: str = "image/jpeg",
    ) -> None:
        self.status = 200
        self.headers = {"Content-Type": content_type}
        self._body = body
        self._offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._body):
            return b""
        end = len(self._body) if size < 0 else self._offset + size
        chunk = self._body[self._offset:end]
        self._offset += len(chunk)
        return chunk


class _BlockingConcurrentOpener:
    def __init__(self, expected_active: int) -> None:
        self.expected_active = expected_active
        self.release = threading.Event()
        self.enough_active = threading.Event()
        self._lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0
        self.calls: list[str] = []

    def __call__(self, request, *, timeout: float):
        del timeout
        with self._lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.calls.append(request.full_url)
            if self.active >= self.expected_active:
                self.enough_active.set()
        self.release.wait(timeout=3)
        with self._lock:
            self.active -= 1
        return _ConcurrentResponse(request.full_url.encode("utf-8"))


def _concurrent_config() -> DownloadConfig:
    return DownloadConfig(
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        overall_timeout_seconds=5,
        max_attempts=1,
        retry_backoff_seconds=0,
        chunk_size=64,
        max_workers=MAX_IMAGE_DOWNLOAD_WORKERS,
    )


def test_concurrent_downloader_is_bounded_and_preserves_index_order(
    tmp_path: Path,
) -> None:
    opener = _BlockingConcurrentOpener(MAX_IMAGE_DOWNLOAD_WORKERS)
    downloader = ImageDownloader(_concurrent_config(), open_url=opener)
    urls = [f"https://img/{index}.jpg" for index in range(1, 9)]
    results: list[ProductDownloadResult] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(downloader.download_product_images(urls, tmp_path))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert opener.enough_active.wait(timeout=2)
    assert 1 < opener.maximum_active <= MAX_IMAGE_DOWNLOAD_WORKERS
    opener.release.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
    assert [item.index for item in results[0].items] == list(range(1, 9))
    assert [item.target_path.name for item in results[0].items] == [
        f"{index:02d}.jpg" for index in range(1, 9)
    ]
    assert [path.read_bytes().decode("utf-8") for path in sorted(tmp_path.glob("*.jpg"))] == urls


def test_concurrent_pause_drains_active_set_before_submitting_more(
    tmp_path: Path,
) -> None:
    opener = _BlockingConcurrentOpener(MAX_IMAGE_DOWNLOAD_WORKERS)
    downloader = ImageDownloader(_concurrent_config(), open_url=opener)
    pause_requested = threading.Event()
    paused = threading.Event()
    resume = threading.Event()
    downloader.set_pause_control(
        pause_requested.is_set,
        lambda: (paused.set(), resume.wait(timeout=3)),
    )
    urls = [f"https://img/{index}.jpg" for index in range(1, 7)]
    finished: list[ProductDownloadResult] = []
    thread = threading.Thread(
        target=lambda: finished.append(
            downloader.download_product_images(urls, tmp_path)
        )
    )
    thread.start()
    assert opener.enough_active.wait(timeout=2)
    pause_requested.set()
    opener.release.set()
    assert paused.wait(timeout=2)
    assert len(opener.calls) == MAX_IMAGE_DOWNLOAD_WORKERS

    pause_requested.clear()
    resume.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(opener.calls) == len(urls)
    assert finished[0].total == len(urls)


def test_concurrent_cancellation_cleans_parts_and_stops_submission(
    tmp_path: Path,
) -> None:
    opener = _BlockingConcurrentOpener(MAX_IMAGE_DOWNLOAD_WORKERS)
    downloader = ImageDownloader(_concurrent_config(), open_url=opener)
    cancelled = threading.Event()
    errors: list[BaseException] = []
    urls = [f"https://img/{index}.jpg" for index in range(1, 9)]

    def run() -> None:
        try:
            downloader.download_product_images(
                urls,
                tmp_path,
                cancel_check=cancelled.is_set,
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert opener.enough_active.wait(timeout=2)
    cancelled.set()
    opener.release.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(opener.calls) == MAX_IMAGE_DOWNLOAD_WORKERS
    assert len(errors) == 1
    assert isinstance(errors[0], DownloadCancelledError)
    assert not list(tmp_path.glob("*.part"))


def test_concurrent_single_image_failure_does_not_corrupt_other_results(
    tmp_path: Path,
) -> None:
    def opener(request, *, timeout: float):
        del timeout
        if request.full_url.endswith("/2"):
            return _ConcurrentResponse(b"<html>blocked</html>", "text/html")
        return _ConcurrentResponse(request.full_url.encode("utf-8"))

    urls = [f"https://img/{index}" for index in range(1, 5)]
    result = ImageDownloader(
        _concurrent_config(),
        open_url=opener,
    ).download_product_images(urls, tmp_path)

    assert [item.index for item in result.items] == [1, 2, 3, 4]
    assert [item.status for item in result.items] == [
        ImageDownloadStatus.SUCCESS,
        ImageDownloadStatus.FAILED,
        ImageDownloadStatus.SUCCESS,
        ImageDownloadStatus.SUCCESS,
    ]
    assert result.failed == 1
    assert not list(tmp_path.glob("*.part"))


def _product(request_id: str, item_id: str) -> BridgeProductData:
    return BridgeProductData(
        url=f"https://shopee.vn/product-{item_id}",
        product_name=f"Product {item_id}",
        shop_id="100",
        item_id=item_id,
        images=[f"https://img/{item_id}.jpg"],
        image_count=1,
        request_id=request_id,
    )


def _with_folder(
    product: BridgeProductData,
    folder: Path,
) -> BridgeProductData:
    from dataclasses import replace

    return replace(product, product_folder=folder)


def _with_success_result(product: BridgeProductData) -> BridgeProductData:
    from dataclasses import replace

    assert product.product_folder is not None
    result = ProductDownloadResult.from_items(
        1,
        [
            ImageDownloadResult(
                index=1,
                source_url=product.images[0],
                target_path=product.product_folder / "01.jpg",
                status=ImageDownloadStatus.SUCCESS,
                attempts=1,
            )
        ],
    )
    return replace(product, download_result=result)


def _timeout_error():
    from shopee_image_downloader.core.error_policy import (
        ErrorStage,
        classify_error_code,
    )

    return classify_error_code("TIMEOUT", stage=ErrorStage.EXTRACTION)
