"""Unit and integration tests for the active BatchQueueManager."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    ItemState,
    QueueState,
    STATUS_DISPLAY_CANCELLED,
    STATUS_DISPLAY_FAILED,
    STATUS_DISPLAY_NAVIGATING,
    STATUS_DISPLAY_SCANNING,
    STATUS_DISPLAY_SUCCESS,
    STATUS_DISPLAY_TIMEOUT,
    STATUS_DISPLAY_VERIFICATION,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.image_downloader import (
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
)
from shopee_image_downloader.core.url_validator import parse_url_lines


@pytest.fixture
def queue_manager(qtbot) -> BatchQueueManager:
    """Fixture providing a BatchQueueManager instance with short timeout."""
    manager = BatchQueueManager(item_timeout_ms=500)
    manager.item_download_requested.connect(
        lambda _row, product: manager.handle_download_result(
            _with_successful_download(product)
        )
    )
    return manager


def _with_successful_download(product: BridgeProductData) -> BridgeProductData:
    total = len(product.images)
    padding = max(2, len(str(total)))
    results = tuple(
        ImageDownloadResult(
            index=index,
            source_url=url,
            target_path=Path(f"{index:0{padding}d}.jpg"),
            status=ImageDownloadStatus.SUCCESS,
            attempts=1,
        )
        for index, url in enumerate(product.images, start=1)
    )
    return replace(
        product,
        download_result=ProductDownloadResult.from_items(total, results),
    )


def test_three_valid_urls_processed_sequentially(qtbot, queue_manager) -> None:
    """Verify 3 valid URLs are processed sequentially (FIFO queue)."""
    valid_items = [
        (0, "https://shopee.vn/product-1"),
        (1, "https://shopee.vn/product-2"),
        (2, "https://shopee.vn/product-3"),
    ]

    started_items = []
    completed_items = []
    progress_updates = []
    batch_finished_events = []

    queue_manager.item_started.connect(lambda row, url, req: started_items.append((row, url, req)))
    queue_manager.item_completed.connect(lambda row, data: completed_items.append((row, data)))
    queue_manager.progress_updated.connect(lambda fin, tot: progress_updates.append((fin, tot)))
    queue_manager.batch_finished.connect(lambda s, f, items: batch_finished_events.append((s, f, items)))

    # 1. Start batch
    started = queue_manager.start_batch(valid_items)
    assert started is True
    assert queue_manager.state == QueueState.RUNNING
    assert len(started_items) == 1
    assert started_items[0][0] == 0  # Row 0 started

    req1 = started_items[0][2]

    # Progress stages for item 1
    queue_manager.handle_process_progress(req1, "scanning_gallery")
    assert queue_manager.current_item.state == ItemState.SCANNING

    # Complete item 1
    data1 = BridgeProductData(
        url="https://shopee.vn/product-1",
        product_name="Product 1",
        shop_id="101",
        item_id="201",
        images=["https://img.com/1.jpg"],
        request_id=req1,
    )
    queue_manager.handle_product_result(data1)

    assert len(completed_items) == 1
    assert completed_items[0][0] == 0
    assert len(started_items) == 2  # Item 2 automatically started
    assert started_items[1][0] == 1  # Row 1 started

    req2 = started_items[1][2]

    # Complete item 2
    data2 = BridgeProductData(
        url="https://shopee.vn/product-2",
        product_name="Product 2",
        shop_id="102",
        item_id="202",
        images=["https://img.com/2.jpg"],
        request_id=req2,
    )
    queue_manager.handle_product_result(data2)

    assert len(completed_items) == 2
    assert len(started_items) == 3  # Item 3 automatically started
    assert started_items[2][0] == 2

    req3 = started_items[2][2]

    # Complete item 3
    data3 = BridgeProductData(
        url="https://shopee.vn/product-3",
        product_name="Product 3",
        shop_id="103",
        item_id="203",
        images=["https://img.com/3.jpg"],
        request_id=req3,
    )
    queue_manager.handle_product_result(data3)

    assert len(completed_items) == 3
    assert len(batch_finished_events) == 1
    success_cnt, fail_cnt, all_items = batch_finished_events[0]
    assert success_cnt == 3
    assert fail_cnt == 0
    assert queue_manager.state == QueueState.IDLE


def test_url_failure_does_not_stop_batch(qtbot, queue_manager) -> None:
    """Verify that if URL #2 fails, URL #3 still processes to completion."""
    valid_items = [
        (0, "https://shopee.vn/product-1"),
        (1, "https://shopee.vn/product-2"),
        (2, "https://shopee.vn/product-3"),
    ]

    failed_items = []
    completed_items = []
    finished_summary = []

    queue_manager.item_failed.connect(lambda row, code, msg: failed_items.append((row, code, msg)))
    queue_manager.item_completed.connect(lambda row, data: completed_items.append((row, data)))
    queue_manager.batch_finished.connect(lambda s, f, items: finished_summary.append((s, f)))

    queue_manager.start_batch(valid_items)

    # Complete item 1
    req1 = queue_manager.current_item.request_id
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/product-1",
            product_name="Product 1",
            shop_id="101",
            item_id="201",
            images=["https://img.com/1.jpg"],
            request_id=req1,
        )
    )

    # Item 2 fails
    req2 = queue_manager.current_item.request_id
    queue_manager.handle_process_error(req2, "https://shopee.vn/product-2", "NOT_FOUND", "Không tìm thấy sản phẩm")

    assert len(failed_items) == 1
    assert failed_items[0][0] == 1
    assert failed_items[0][1] == "NOT_FOUND"

    # Item 3 should be started now
    assert queue_manager.current_item.row_idx == 2
    req3 = queue_manager.current_item.request_id

    # Complete item 3
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/product-3",
            product_name="Product 3",
            shop_id="103",
            item_id="203",
            images=["https://img.com/3.jpg"],
            request_id=req3,
        )
    )

    assert len(completed_items) == 2
    assert len(failed_items) == 1
    assert finished_summary == [(2, 1)]


def test_exact_duplicate_input_urls_queued_once() -> None:
    """Verify that exact duplicate input URLs are deduplicated before queue creation."""
    raw_input = """
    https://shopee.vn/product-1
    https://shopee.vn/product-2
    https://shopee.vn/product-1
    https://shopee.vn/product-2
    """
    parsed = parse_url_lines(raw_input)
    assert len(parsed) == 2
    assert parsed[0].url == "https://shopee.vn/product-1"
    assert parsed[1].url == "https://shopee.vn/product-2"


def test_request_id_correlation_and_stale_results(qtbot, queue_manager) -> None:
    """Verify results for incorrect or stale request_ids are rejected safely."""
    valid_items = [
        (0, "https://shopee.vn/product-1"),
        (1, "https://shopee.vn/product-2"),
    ]

    completed_events = []
    queue_manager.item_completed.connect(lambda row, data: completed_events.append((row, data)))

    queue_manager.start_batch(valid_items)
    req1 = queue_manager.current_item.request_id

    # 1. Send stale result with bogus request_id
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/old",
            product_name="Old Stale",
            shop_id="1",
            item_id="2",
            images=[],
            request_id="stale-req-999",
        )
    )
    # Stale result ignored
    assert len(completed_events) == 0
    assert queue_manager.current_item.row_idx == 0

    # 2. Send correct result
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/product-1",
            product_name="Product 1",
            shop_id="101",
            item_id="201",
            images=["https://img.com/1.jpg"],
            request_id=req1,
        )
    )
    assert len(completed_events) == 1
    assert completed_events[0][0] == 0


def test_batch_cannot_start_twice(qtbot, queue_manager) -> None:
    """Verify that start_batch returns False while a batch is already RUNNING."""
    valid_items = [(0, "https://shopee.vn/product-1")]

    started_1 = queue_manager.start_batch(valid_items)
    assert started_1 is True
    assert queue_manager.state == QueueState.RUNNING

    # Attempt to start second batch
    started_2 = queue_manager.start_batch(valid_items)
    assert started_2 is False


def test_per_item_timeout_advances_queue(qtbot) -> None:
    """Verify that bounded per-item timeout marks item as TIMEOUT and advances to next."""
    # Fast 50ms timeout for unit test
    manager = BatchQueueManager(item_timeout_ms=50)

    valid_items = [
        (0, "https://shopee.vn/slow-item"),
        (1, "https://shopee.vn/normal-item"),
    ]

    failed_items = []
    manager.item_failed.connect(lambda row, code, msg: failed_items.append((row, code, msg)))

    manager.start_batch(valid_items)

    # Wait for timeout to fire for item 1
    qtbot.waitUntil(lambda: len(failed_items) == 1, timeout=1000)

    assert failed_items[0][0] == 0
    assert failed_items[0][1] == "TIMEOUT"
    assert failed_items[0][2] == STATUS_DISPLAY_TIMEOUT

    # Manager should now be on item 2
    assert manager.current_item.row_idx == 1


def test_verification_pauses_and_resume_continues_current_item(qtbot, queue_manager) -> None:
    """Verify verification challenge pauses queue and resume re-processes the SAME item."""
    valid_items = [
        (0, "https://shopee.vn/needs-verify"),
        (1, "https://shopee.vn/next-item"),
    ]

    verification_events = []
    queue_manager.verification_required.connect(lambda row, url, msg: verification_events.append((row, url, msg)))

    queue_manager.start_batch(valid_items)
    req1 = queue_manager.current_item.request_id

    # Emit verification required error
    queue_manager.handle_process_error(req1, "https://shopee.vn/needs-verify", "VERIFICATION_REQUIRED", "Shopee yêu cầu xác minh")

    assert queue_manager.state == QueueState.PAUSED_VERIFICATION
    assert len(verification_events) == 1
    assert verification_events[0][0] == 0  # Row 0
    assert queue_manager.current_item.row_idx == 0  # Still row 0!

    # Resume after user solves captcha
    resumed = queue_manager.resume_verification()
    assert resumed is True
    assert queue_manager.state == QueueState.RUNNING
    assert queue_manager.current_item.row_idx == 0  # Re-processes item 0

    # Now complete item 0
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/needs-verify",
            product_name="Verified Product",
            shop_id="555",
            item_id="666",
            images=["https://img.com/v.jpg"],
            request_id=queue_manager.current_item.request_id,
        )
    )

    # Now queue advances to item 1
    assert queue_manager.current_item.row_idx == 1


def test_cancel_batch_stops_queue_and_resets(qtbot, queue_manager) -> None:
    """Verify cancel_batch stops further processing and emits batch_finished."""
    valid_items = [
        (0, "https://shopee.vn/item-1"),
        (1, "https://shopee.vn/item-2"),
    ]

    cancelled_events = []
    batch_finished_events = []

    queue_manager.send_cancel_requested.connect(lambda req: cancelled_events.append(req))
    queue_manager.batch_finished.connect(lambda s, f, items: batch_finished_events.append((s, f, items)))

    queue_manager.start_batch(valid_items)
    assert queue_manager.state == QueueState.RUNNING

    queue_manager.cancel_batch()

    assert queue_manager.state == QueueState.IDLE
    assert len(cancelled_events) == 1
    assert len(batch_finished_events) == 1
    s, f, items = batch_finished_events[0]
    assert s == 0
    assert f == 1  # In-flight item counted as cancelled/failed


def test_batch_queue_accepts_authoritative_9_images(qtbot, queue_manager) -> None:
    """Verify queue manager stores authoritative 9 images payload in product model."""
    valid_items = [(0, "https://shopee.vn/product-i.78513158.28469164720")]
    completed_events = []
    queue_manager.item_completed.connect(lambda row, prod: completed_events.append((row, prod)))

    queue_manager.start_batch(valid_items)
    req_id = queue_manager.current_item.request_id

    prod_data = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Áo Thun Nam Cao Cấp",
        shop_id="78513158",
        item_id="28469164720",
        images=[f"https://img.com/{i}.jpg" for i in range(1, 10)],
        image_count=9,
        request_id=req_id,
    )
    queue_manager.handle_product_result(prod_data)

    assert len(completed_events) == 1
    row_idx, completed_prod = completed_events[0]
    assert row_idx == 0
    assert len(completed_prod.images) == 9
    assert completed_prod.image_count == 9
    assert completed_prod.images[8] == "https://img.com/9.jpg"


def test_batch_queue_rejects_image_count_mismatch_as_protocol_integrity_error(qtbot, queue_manager) -> None:
    """Verify queue manager rejects payload when image_count does not match len(images)."""
    valid_items = [(0, "https://shopee.vn/product-i.78513158.28469164720")]
    failed_events = []
    completed_events = []
    queue_manager.item_failed.connect(lambda row, code, msg: failed_events.append((row, code, msg)))
    queue_manager.item_completed.connect(lambda row, prod: completed_events.append((row, prod)))

    queue_manager.start_batch(valid_items)
    req_id = queue_manager.current_item.request_id

    # 4 images but image_count declares 9
    mismatched_prod = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Áo Thun Nam Cao Cấp",
        shop_id="78513158",
        item_id="28469164720",
        images=[f"https://img.com/{i}.jpg" for i in range(1, 5)],
        image_count=9,
        request_id=req_id,
    )
    queue_manager.handle_product_result(mismatched_prod)

    # Must NOT report success
    assert len(completed_events) == 0
    # Must fail with PROTOCOL_INTEGRITY_ERROR
    assert len(failed_events) == 1
    row, code, msg = failed_events[0]
    assert row == 0
    assert code == "PROTOCOL_INTEGRITY_ERROR"
    assert msg == "Lỗi đồng bộ dữ liệu ảnh"


def test_batch_queue_emits_open_product_signal(qtbot, queue_manager) -> None:
    """Verify queue emits send_open_product_requested with (request_id, url) for each batch item."""
    valid_items = [(0, "https://shopee.vn/product-1"), (1, "https://shopee.vn/product-2")]
    open_requests = []
    queue_manager.send_open_product_requested.connect(lambda req, url: open_requests.append((req, url)))

    queue_manager.start_batch(valid_items)

    assert len(open_requests) == 1
    req1, url1 = open_requests[0]
    assert url1 == "https://shopee.vn/product-1"
    assert req1 == queue_manager.current_item.request_id

    # Complete item 1
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/product-1",
            product_name="Product 1",
            shop_id="101",
            item_id="201",
            images=["https://img.com/1.jpg"],
            image_count=1,
            request_id=req1,
        )
    )

    # Item 2 should emit open_product
    assert len(open_requests) == 2
    req2, url2 = open_requests[1]
    assert url2 == "https://shopee.vn/product-2"
    assert req2 != req1


def test_stale_event_after_advancing_is_ignored(qtbot, queue_manager) -> None:
    """Verify that a stale event from item A arriving after item B has started is ignored."""
    valid_items = [(0, "https://shopee.vn/product-1"), (1, "https://shopee.vn/product-2")]
    completed_events = []
    queue_manager.item_completed.connect(lambda row, prod: completed_events.append((row, prod)))

    queue_manager.start_batch(valid_items)
    req1 = queue_manager.current_item.request_id

    # Complete item 1
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/product-1",
            product_name="Product 1",
            shop_id="101",
            item_id="201",
            images=["https://img.com/1.jpg"],
            image_count=1,
            request_id=req1,
        )
    )

    assert len(completed_events) == 1
    assert queue_manager.current_item.row_idx == 1
    req2 = queue_manager.current_item.request_id

    # Stale duplicate event for req1 arrives while item 2 is in-flight
    queue_manager.handle_product_result(
        BridgeProductData(
            url="https://shopee.vn/product-1",
            product_name="Stale Product 1",
            shop_id="101",
            item_id="201",
            images=["https://img.com/1.jpg"],
            image_count=1,
            request_id=req1,
        )
    )

    # Queue must still be on item 2 and completed_events must still have length 1
    assert len(completed_events) == 1
    assert queue_manager.current_item.row_idx == 1
    assert queue_manager.current_item.request_id == req2


def test_queue_does_not_advance_until_image_download_finishes(qtbot) -> None:
    manager = BatchQueueManager(item_timeout_ms=500)
    started_rows: list[int] = []
    requested_products: list[BridgeProductData] = []
    manager.item_started.connect(
        lambda row, _url, _request: started_rows.append(row)
    )
    manager.item_download_requested.connect(
        lambda _row, product: requested_products.append(product)
    )
    manager.start_batch(
        [
            (0, "https://shopee.vn/product-1"),
            (1, "https://shopee.vn/product-2"),
        ]
    )
    request_id = manager.current_item.request_id
    product = BridgeProductData(
        url="https://shopee.vn/product-1",
        product_name="Product 1",
        shop_id="101",
        item_id="201",
        images=["https://img.example/1.jpg"],
        image_count=1,
        request_id=request_id,
    )

    manager.handle_product_result(product)

    assert manager.current_item.state == ItemState.DOWNLOADING
    assert started_rows == [0]
    assert requested_products == [product]
    assert manager.get_finished_count() == 0

    manager.handle_download_result(_with_successful_download(product))

    assert started_rows == [0, 1]
    assert manager.current_item.row_idx == 1


def test_partial_image_failure_is_completed_with_errors_and_batch_continues(
    qtbot,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=500)
    completed: list[BridgeProductData] = []
    manager.item_completed.connect(lambda _row, product: completed.append(product))
    manager.start_batch(
        [
            (0, "https://shopee.vn/product-1"),
            (1, "https://shopee.vn/product-2"),
        ]
    )
    request_id = manager.current_item.request_id
    product = BridgeProductData(
        url="https://shopee.vn/product-1",
        product_name="Product 1",
        shop_id="101",
        item_id="201",
        images=[
            "https://img.example/1.jpg",
            "https://img.example/2.jpg",
        ],
        image_count=2,
        request_id=request_id,
    )
    manager.handle_product_result(product)
    per_image = (
        ImageDownloadResult(
            index=1,
            source_url=product.images[0],
            target_path=Path("01.jpg"),
            status=ImageDownloadStatus.SUCCESS,
            attempts=1,
        ),
        ImageDownloadResult(
            index=2,
            source_url=product.images[1],
            target_path=Path("02.jpg"),
            status=ImageDownloadStatus.FAILED,
            attempts=3,
            error="HTTP 500",
        ),
    )
    completed_product = replace(
        product,
        download_result=ProductDownloadResult.from_items(2, per_image),
    )

    manager.handle_download_result(completed_product)

    assert len(completed) == 1
    assert manager._items[0].state == ItemState.COMPLETED_WITH_ERRORS
    assert manager.current_item.row_idx == 1
    assert manager.get_success_count() == 1
    assert manager.get_fail_count() == 0
