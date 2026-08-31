"""Task 010 regressions for sequential batch and worker reliability."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
from typing import Any, Sequence
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QTimer

from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    ItemState,
    QueueState,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.image_downloader import (
    DownloadCancelledError,
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
)
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.ui.main_window import MainWindow
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer
from shopee_image_downloader.workers.image_download_worker import (
    ImageDownloadController,
)


def _product(
    request_id: str,
    number: int,
    *,
    image_count: int = 3,
) -> BridgeProductData:
    images = [
        f"https://cdn.example/product-{number}/{index}.jpg"
        for index in range(1, image_count + 1)
    ]
    return BridgeProductData(
        url=f"https://shopee.vn/product-{number}",
        product_name=f"Product {number}",
        shop_id=str(1000 + number),
        item_id=str(2000 + number),
        images=images,
        image_count=image_count,
        request_id=request_id,
    )


def _folder_ready(product: BridgeProductData) -> BridgeProductData:
    return replace(
        product,
        product_folder=Path(f"product-folder-{product.item_id}"),
    )


def _successful(product: BridgeProductData) -> BridgeProductData:
    assert product.product_folder is not None
    total = len(product.images)
    padding = max(2, len(str(total)))
    results = tuple(
        ImageDownloadResult(
            index=index,
            source_url=source_url,
            target_path=product.product_folder / f"{index:0{padding}d}.jpg",
            status=ImageDownloadStatus.SUCCESS,
            attempts=1,
        )
        for index, source_url in enumerate(product.images, start=1)
    )
    return replace(
        product,
        download_result=ProductDownloadResult.from_items(total, results),
    )


def _complete_current(manager: BatchQueueManager, number: int) -> BridgeProductData:
    current = manager.current_item
    assert current is not None
    product = _product(current.request_id, number)
    manager.handle_product_result(product)
    assert manager.current_item is current
    assert current.state == ItemState.CREATING_FOLDER
    enriched = _folder_ready(product)
    manager.handle_product_folder_ready(enriched)
    assert current.state == ItemState.DOWNLOADING
    manager.handle_download_result(_successful(enriched))
    return enriched


def test_ten_products_finish_in_input_order_with_one_active_product(qtbot) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    inputs = [
        (index, f"https://shopee.vn/product-{index + 1}")
        for index in range(10)
    ]
    started_rows: list[int] = []
    completed_rows: list[int] = []
    progress: list[tuple[int, int]] = []
    active_products = 0
    max_active_products = 0

    def on_started(row: int, _url: str, _request_id: str) -> None:
        nonlocal active_products, max_active_products
        active_products += 1
        max_active_products = max(max_active_products, active_products)
        started_rows.append(row)

    def on_completed(row: int, _product_data: BridgeProductData) -> None:
        nonlocal active_products
        completed_rows.append(row)
        active_products -= 1

    manager.item_started.connect(on_started)
    manager.item_completed.connect(on_completed)
    manager.progress_updated.connect(
        lambda finished, total: progress.append((finished, total))
    )

    assert manager.start_batch(inputs)
    for number in range(1, 11):
        before_started = len(started_rows)
        current = manager.current_item
        assert current is not None
        product = _product(current.request_id, number)
        manager.handle_product_result(product)
        assert len(started_rows) == before_started
        enriched = _folder_ready(product)
        manager.handle_product_folder_ready(enriched)
        assert len(started_rows) == before_started
        manager.handle_download_result(_successful(enriched))

    assert started_rows == list(range(10))
    assert completed_rows == list(range(10))
    assert max_active_products == 1
    assert active_products == 0
    assert [item.state for item in manager.items] == [ItemState.SUCCESS] * 10
    assert progress[-1] == (10, 10)
    assert manager.state == QueueState.IDLE


@pytest.mark.parametrize(
    "failure_phase",
    ["extraction", "folder", "download"],
)
def test_middle_product_failure_continues_to_product_c(
    qtbot,
    failure_phase: str,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    manager.start_batch(
        [
            (0, "https://shopee.vn/a"),
            (1, "https://shopee.vn/b"),
            (2, "https://shopee.vn/c"),
        ]
    )
    _complete_current(manager, 1)

    item_b = manager.current_item
    assert item_b is not None
    product_b = _product(item_b.request_id, 2)
    if failure_phase == "extraction":
        manager.handle_process_error(
            item_b.request_id,
            item_b.input_url,
            "NOT_FOUND",
            "Không tìm thấy sản phẩm",
        )
    else:
        manager.handle_product_result(product_b)
        if failure_phase == "folder":
            manager.handle_pipeline_failure(
                product_b,
                "PRODUCT_FOLDER_ERROR",
                "Không thể tạo thư mục sản phẩm.",
            )
        else:
            enriched_b = _folder_ready(product_b)
            manager.handle_product_folder_ready(enriched_b)
            manager.handle_pipeline_failure(
                enriched_b,
                "IMAGE_DOWNLOAD_ERROR",
                "Không thể hoàn tất tải ảnh sản phẩm.",
            )

    assert manager.current_item is not None
    assert manager.current_item.row_idx == 2
    _complete_current(manager, 3)

    assert [item.state for item in manager.items] == [
        ItemState.SUCCESS,
        ItemState.FAILED,
        ItemState.SUCCESS,
    ]
    assert manager.get_success_count() == 2
    assert manager.get_fail_count() == 1
    assert manager.get_finished_count() == 3


def test_stale_product_and_worker_events_cannot_change_product_b(qtbot) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    progress_events: list[tuple[int, str]] = []
    manager.item_progress.connect(
        lambda row, _stage, text: progress_events.append((row, text))
    )
    manager.start_batch(
        [
            (0, "https://shopee.vn/a"),
            (1, "https://shopee.vn/b"),
        ]
    )
    product_a = _complete_current(manager, 1)
    item_b = manager.current_item
    assert item_b is not None
    b_state = item_b.state
    b_product = item_b.product_data
    event_count = len(progress_events)

    manager.handle_product_result(
        replace(product_a, product_name="Stale A", product_folder=None)
    )
    manager.handle_process_progress(product_a.request_id or "", "complete")
    manager.handle_download_progress(product_a, 3, 3)
    manager.handle_download_result(_successful(product_a))

    assert manager.current_item is item_b
    assert item_b.state == b_state == ItemState.OPENING_PRODUCT
    assert item_b.product_data is b_product is None
    assert len(progress_events) == event_count


def test_double_start_emits_only_one_open_product(qtbot) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    open_requests: list[tuple[str, str]] = []
    manager.send_open_product_requested.connect(
        lambda request_id, url: open_requests.append((request_id, url))
    )
    inputs = [(0, "https://shopee.vn/product-1")]

    assert manager.start_batch(inputs) is True
    first_items = manager.items
    assert manager.start_batch(inputs) is False

    assert len(open_requests) == 1
    assert manager.items == first_items
    assert manager.current_item is first_items[0]


def test_cancel_product_three_stops_before_product_four(qtbot) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    opened_rows: list[int] = []
    cancelled_workers: list[str] = []
    final_summaries: list[tuple[int, int, list[Any]]] = []
    manager.item_started.connect(
        lambda row, _url, _request: opened_rows.append(row)
    )
    manager.cancel_download_requested.connect(cancelled_workers.append)
    manager.batch_finished.connect(
        lambda success, failed, items: final_summaries.append(
            (success, failed, items)
        )
    )
    manager.start_batch(
        [
            (index, f"https://shopee.vn/product-{index + 1}")
            for index in range(10)
        ]
    )
    _complete_current(manager, 1)
    _complete_current(manager, 2)

    current = manager.current_item
    assert current is not None and current.row_idx == 2
    product_three = _product(current.request_id, 3)
    manager.handle_product_result(product_three)
    enriched_three = _folder_ready(product_three)
    manager.handle_product_folder_ready(enriched_three)
    assert current.state == ItemState.DOWNLOADING

    assert manager.cancel_batch() is True
    assert manager.state == QueueState.CANCELLING
    assert opened_rows == [0, 1, 2]
    assert cancelled_workers == [current.request_id]

    manager.handle_download_cancelled(enriched_three)

    assert manager.state == QueueState.IDLE
    assert opened_rows == [0, 1, 2]
    assert [item.state for item in manager.items[:2]] == [
        ItemState.SUCCESS,
        ItemState.SUCCESS,
    ]
    assert all(
        item.state == ItemState.CANCELLED for item in manager.items[2:]
    )
    assert manager.get_finished_count() == 10
    assert manager.get_cancelled_count() == 8
    assert final_summaries[-1][0:2] == (2, 0)


def test_product_models_do_not_share_mutable_image_lists(qtbot) -> None:
    shared_source = ["https://cdn.example/1.jpg"]
    product_a = BridgeProductData(
        url="https://shopee.vn/a",
        product_name="A",
        shop_id="1",
        item_id="1",
        images=shared_source,
    )
    product_b = BridgeProductData(
        url="https://shopee.vn/b",
        product_name="B",
        shop_id="2",
        item_id="2",
        images=shared_source,
    )

    shared_source.append("https://cdn.example/source-only.jpg")
    product_a.images.append("https://cdn.example/a-only.jpg")

    assert product_a.images == [
        "https://cdn.example/1.jpg",
        "https://cdn.example/a-only.jpg",
    ]
    assert product_b.images == ["https://cdn.example/1.jpg"]
    assert product_a.images is not product_b.images


class _BlockingDownloader:
    """Hold a worker while the GUI event loop proves it remains responsive."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.thread_ids: list[int] = []

    def download_product_images(
        self,
        images: Sequence[str],
        product_folder: str | Path,
        *,
        progress_callback: Any = None,
        cancel_check: Any = None,
    ) -> ProductDownloadResult:
        self.thread_ids.append(threading.get_ident())
        self.started.set()
        self.release.wait(timeout=2)
        if cancel_check is not None and cancel_check():
            raise DownloadCancelledError("cancelled")
        return ProductDownloadResult.from_items(len(images), ())


def test_long_download_keeps_gui_event_loop_responsive(tmp_path: Path, qtbot) -> None:
    downloader = _BlockingDownloader()
    controller = ImageDownloadController(downloader=downloader)
    product = _product("responsive-request", 1, image_count=0)
    timer_fired = threading.Event()

    assert controller.start(product, str(tmp_path))
    qtbot.waitUntil(downloader.started.is_set, timeout=1000)
    QTimer.singleShot(20, timer_fired.set)
    qtbot.waitUntil(timer_fired.is_set, timeout=1000)

    assert controller.is_busy
    assert downloader.thread_ids == [downloader.thread_ids[0]]
    assert downloader.thread_ids[0] != threading.get_ident()

    downloader.release.set()
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=2000)


class _CountingDownloader:
    def __init__(self) -> None:
        self.active = 0
        self.maximum_active = 0
        self.calls = 0

    def download_product_images(
        self,
        images: Sequence[str],
        product_folder: str | Path,
        *,
        progress_callback: Any = None,
        cancel_check: Any = None,
    ) -> ProductDownloadResult:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.calls += 1
        self.active -= 1
        return ProductDownloadResult.from_items(len(images), ())


def test_sequential_workers_release_all_owned_references(tmp_path: Path, qtbot) -> None:
    downloader = _CountingDownloader()
    controller = ImageDownloadController(downloader=downloader)
    products = [
        _product(f"cleanup-{index}", index, image_count=0)
        for index in range(1, 31)
    ]
    finished: list[str | None] = []

    def start_next(
        product: BridgeProductData,
        _result: ProductDownloadResult,
    ) -> None:
        assert not controller.is_busy
        finished.append(product.request_id)
        next_index = len(finished)
        if next_index < len(products):
            assert controller.start(products[next_index], str(tmp_path))

    controller.finished.connect(start_next)
    assert controller.start(products[0], str(tmp_path))
    qtbot.waitUntil(lambda: len(finished) == len(products), timeout=8000)

    assert downloader.calls == len(products)
    assert downloader.maximum_active == 1
    assert not controller.is_busy
    assert controller.active_request_id is None
    assert controller._thread is None
    assert controller._worker is None


class _CancelAwareDownloader:
    def __init__(self) -> None:
        self.started = threading.Event()

    def download_product_images(
        self,
        images: Sequence[str],
        product_folder: str | Path,
        *,
        progress_callback: Any = None,
        cancel_check: Any = None,
    ) -> ProductDownloadResult:
        self.started.set()
        while cancel_check is not None and not cancel_check():
            threading.Event().wait(0.005)
        raise DownloadCancelledError("cancelled")


def test_window_close_waits_for_cooperative_worker_cleanup(
    tmp_path: Path,
    qtbot,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    settings = SettingsManager(config_path=tmp_path / "settings.json")
    settings.set_output_folder(output_root)
    bridge = MagicMock(spec=ExtensionBridgeServer)
    bridge.has_connected_clients = True
    downloader = _CancelAwareDownloader()
    controller = ImageDownloadController(downloader=downloader)
    window = MainWindow(
        settings_manager=settings,
        bridge_server=bridge,
        image_download_controller=controller,
        start_bridge=False,
    )
    qtbot.addWidget(window)
    window.show()
    window.url_input.setPlainText("https://shopee.vn/product-1")
    window.start_button.click()
    current = window.queue_manager.current_item
    assert current is not None
    window._on_bridge_product_received(
        _product(current.request_id, 1, image_count=1)
    )
    qtbot.waitUntil(downloader.started.is_set, timeout=1000)

    window.close()
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=2000)
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=2000)

    assert window.queue_manager.state == QueueState.IDLE
    assert controller._thread is None
    assert controller._worker is None
    assert not list(output_root.rglob("*.part"))
