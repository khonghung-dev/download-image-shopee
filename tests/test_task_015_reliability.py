"""Task 015 deterministic stress and final reliability-gate regressions."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
import logging
from pathlib import Path
import threading
from typing import Any, Sequence
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest
from PySide6.QtCore import QTimer

from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    ItemState,
    QueueState,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.error_policy import RetryPolicy
from shopee_image_downloader.core.image_downloader import (
    DownloadCancelledError,
    DownloadConfig,
    ImageDownloader,
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
)
from shopee_image_downloader.core.product_metadata import (
    PRODUCT_METADATA_FILENAME,
    PRODUCT_METADATA_TEMP_FILENAME,
    build_product_metadata,
    write_product_metadata,
)
from shopee_image_downloader.core import product_metadata as metadata_module
from shopee_image_downloader.storage.product_folder import (
    MAX_PRODUCT_FOLDER_NAME_LENGTH,
    PRODUCT_ID_MARKER_FILENAME,
    ProductFolderError,
    ensure_product_folder,
    sanitize_product_folder_name,
)
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.ui.main_window import MainWindow
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer
from shopee_image_downloader.workers.image_download_worker import (
    ImageDownloadController,
)
from tests.test_ui import (
    ImmediateImageDownloadController,
    _create_window,
    _product as ui_product,
)


def _product(
    request_id: str,
    number: int,
    *,
    identity_number: int | None = None,
    image_count: int = 3,
    name: str | None = None,
) -> BridgeProductData:
    identity = identity_number if identity_number is not None else number
    shop_id = str(10_000 + identity)
    item_id = str(20_000 + identity)
    return BridgeProductData(
        url=f"https://shopee.vn/product-{number}-i.{shop_id}.{item_id}",
        input_url=f"https://shopee.vn/input-{number}",
        final_url=f"https://shopee.vn/product-{number}-i.{shop_id}.{item_id}",
        product_name=name or f"Product {number}",
        shop_id=shop_id,
        item_id=item_id,
        images=[
            f"https://cdn.example/{identity}/{index}.jpg"
            for index in range(1, image_count + 1)
        ],
        image_count=image_count,
        request_id=request_id,
    )


def _folder_ready(
    product: BridgeProductData,
    root: Path,
    *,
    label: str | None = None,
) -> BridgeProductData:
    folder = root / (label or f"folder-{product.product_key.replace(':', '-')}")
    folder.mkdir(exist_ok=True)
    return replace(product, product_folder=folder)


def _terminal_product(
    product: BridgeProductData,
    statuses: Sequence[ImageDownloadStatus] | None = None,
) -> BridgeProductData:
    assert product.product_folder is not None
    chosen = list(statuses or [ImageDownloadStatus.SUCCESS] * len(product.images))
    assert len(chosen) == len(product.images)
    items = tuple(
        ImageDownloadResult(
            index=index,
            source_url=source_url,
            target_path=product.product_folder / f"{index:02d}.jpg",
            status=chosen[index - 1],
            attempts=1,
            error=(
                "HTTP 404"
                if chosen[index - 1] == ImageDownloadStatus.FAILED
                else None
            ),
        )
        for index, source_url in enumerate(product.images, start=1)
    )
    return replace(
        product,
        download_result=ProductDownloadResult.from_items(len(items), items),
    )


def _complete_product(
    manager: BatchQueueManager,
    root: Path,
    number: int,
    *,
    identity_number: int | None = None,
    statuses: Sequence[ImageDownloadStatus] | None = None,
) -> BridgeProductData:
    item = manager.current_item
    assert item is not None
    extracted = _product(
        item.request_id,
        number,
        identity_number=identity_number,
        image_count=len(statuses) if statuses is not None else 3,
    )
    manager.handle_product_result(extracted)
    enriched = _folder_ready(extracted, root)
    manager.handle_product_folder_ready(enriched)
    manager.handle_download_result(_terminal_product(enriched, statuses))
    return enriched


def _assert_accounting(manager: BatchQueueManager) -> None:
    terminal = manager.get_finished_count()
    assert terminal <= manager.total_count
    assert (
        manager.get_success_count()
        + manager.get_fail_count()
        + manager.get_duplicate_count()
        + manager.get_cancelled_count()
        == terminal
    )
    if manager.state == QueueState.IDLE:
        assert terminal == manager.total_count


def test_100_product_success_preserves_fifo_single_pipeline_and_accounting(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    inputs = [
        (index, f"https://shopee.vn/product-{index + 1}")
        for index in range(100)
    ]
    started_rows: list[int] = []
    completed_rows: list[int] = []
    opened: list[tuple[str, str]] = []
    progress: list[tuple[int, int]] = []
    active_rows: set[int] = set()
    maximum_active = 0

    def on_started(row: int, _url: str, _request_id: str) -> None:
        nonlocal maximum_active
        active_rows.add(row)
        maximum_active = max(maximum_active, len(active_rows))
        started_rows.append(row)

    def on_completed(row: int, _product_data: BridgeProductData) -> None:
        completed_rows.append(row)
        active_rows.remove(row)

    manager.item_started.connect(on_started)
    manager.item_completed.connect(on_completed)
    manager.send_open_product_requested.connect(
        lambda request_id, url: opened.append((request_id, url))
    )
    manager.progress_updated.connect(
        lambda finished, total: progress.append((finished, total))
    )

    assert manager.start_batch(inputs)
    for number in range(1, 101):
        _complete_product(manager, tmp_path, number)
        assert manager.get_finished_count() == number
        _assert_accounting(manager)

    assert manager.state == QueueState.IDLE
    assert [item.state for item in manager.items] == [ItemState.SUCCESS] * 100
    assert started_rows == list(range(100))
    assert completed_rows == list(range(100))
    assert [url for _request_id, url in opened] == [url for _row, url in inputs]
    assert len({request_id for request_id, _url in opened}) == 100
    assert maximum_active == 1
    assert not active_rows
    assert progress[-1] == (100, 100)


def test_mixed_100_products_reach_exact_terminal_states_without_data_leak(
    tmp_path: Path,
) -> None:
    policy = RetryPolicy(
        max_attempts=3,
        initial_delay_seconds=60,
        max_delay_seconds=60,
    )
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=policy)
    inputs = [(row, f"https://shopee.vn/mixed-{row}") for row in range(100)]
    opened: list[str] = []
    download_rows: list[int] = []
    progress: list[tuple[int, int]] = []
    expected: list[ItemState] = []

    manager.send_open_product_requested.connect(
        lambda request_id, _url: opened.append(request_id)
    )
    manager.item_download_requested.connect(
        lambda row, _product_data: download_rows.append(row)
    )
    manager.progress_updated.connect(
        lambda finished, total: progress.append((finished, total))
    )

    assert manager.start_batch(inputs)
    for row in range(100):
        item = manager.current_item
        assert item is not None and item.row_idx == row
        case = row % 6

        if case == 1:
            manager.handle_process_error(
                item.request_id,
                item.input_url,
                "NOT_FOUND",
                "deterministic permanent failure",
            )
            expected.append(ItemState.FAILED)
        else:
            if case == 2:
                stale_request = item.request_id
                stale_product = _product(stale_request, row + 1)
                manager.handle_process_error(
                    stale_request,
                    item.input_url,
                    "PRODUCT_TIMEOUT",
                    "deterministic transient failure",
                )
                assert item.state == ItemState.WAITING_RETRY
                manager._retry_timer.stop()
                manager._on_retry_timeout()
                assert item.request_id != stale_request
                manager.handle_process_progress(stale_request, "complete")
                manager.handle_process_error(
                    stale_request,
                    item.input_url,
                    "NOT_FOUND",
                    "stale permanent error",
                )
                manager.handle_product_result(stale_product)
                assert item.state == ItemState.OPENING_PRODUCT

            identity = row + 1
            if case == 3:
                identity = row - 2  # row 3 reuses row 0, row 9 reuses row 6, ...
            product = _product(
                item.request_id,
                row + 1,
                identity_number=identity,
            )
            manager.handle_product_result(product)

            if case == 3:
                expected.append(ItemState.SKIPPED_DUPLICATE)
            else:
                enriched = _folder_ready(product, tmp_path)
                manager.handle_product_folder_ready(enriched)
                if case == 4:
                    statuses = [
                        ImageDownloadStatus.SUCCESS,
                        ImageDownloadStatus.FAILED,
                        ImageDownloadStatus.SUCCESS,
                    ]
                    expected.append(ItemState.COMPLETED_WITH_ERRORS)
                elif case == 5:
                    statuses = [ImageDownloadStatus.SKIPPED_EXISTING] * 3
                    expected.append(ItemState.SUCCESS)
                else:
                    statuses = [ImageDownloadStatus.SUCCESS] * 3
                    expected.append(ItemState.SUCCESS)
                manager.handle_download_result(
                    _terminal_product(enriched, statuses)
                )

        assert manager.items[row].state == expected[row]
        assert manager.get_finished_count() == row + 1
        assert manager.get_finished_count() <= manager.total_count

    assert manager.state == QueueState.IDLE
    assert [item.state for item in manager.items] == expected
    assert progress[-1] == (100, 100)
    assert len(download_rows) == sum(
        state
        not in {ItemState.FAILED, ItemState.SKIPPED_DUPLICATE}
        for state in expected
    )
    assert len(opened) == 100 + sum(row % 6 == 2 for row in range(100))
    assert len(opened) == len(set(opened))
    for row, item in enumerate(manager.items):
        if item.product_data is None:
            assert expected[row] == ItemState.FAILED
            continue
        expected_identity = row + 1 if row % 6 != 3 else row - 2
        assert item.product_data.product_key == (
            f"{10_000 + expected_identity}:{20_000 + expected_identity}"
        )
    _assert_accounting(manager)


def test_three_repeated_window_batches_ignore_old_callbacks_and_reset_rows(
    tmp_path: Path,
) -> None:
    controller = ImmediateImageDownloadController()
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
        image_download_controller=controller,
    )
    prior_products: list[BridgeProductData] = []

    for batch_number in range(3):
        urls = [
            f"https://shopee.vn/batch-{batch_number}-product-{index}"
            for index in range(10)
        ]
        window.url_input.setPlainText("\n".join(urls))
        window.start_button.click()
        assert window.queue_manager.state == QueueState.RUNNING
        assert window.results_table.rowCount() == 10

        if prior_products:
            current = window.queue_manager.current_item
            stale = prior_products[-1]
            window._on_bridge_product_received(stale)
            window._on_image_download_progress(stale, 999, 999)
            window._on_image_download_failed(
                stale,
                "NOT_FOUND",
                "stale failure from prior batch",
            )
            assert window.queue_manager.current_item is current
            assert current is not None and current.row_idx == 0

        current_batch: list[BridgeProductData] = []
        for index in range(10):
            current = window.queue_manager.current_item
            assert current is not None and current.row_idx == index
            product = ui_product(
                request_id=current.request_id,
                shop_id=str(50_000 + batch_number * 100 + index),
                item_id=str(60_000 + batch_number * 100 + index),
                image_count=2,
            )
            current_batch.append(product)
            window._on_bridge_product_received(product)

        assert window.queue_manager.state == QueueState.IDLE
        assert all(item.state == ItemState.SUCCESS for item in window.queue_manager.items)
        assert window.results_table.rowCount() == 10
        assert window.batch_progress_label.text() == "Sản phẩm 10/10"
        assert window.start_button.isEnabled()
        assert not window.cancel_button.isEnabled()
        assert not window.queue_manager._timeout_timer.isActive()
        assert not window.queue_manager._retry_timer.isActive()
        assert len(window._rows_by_request_id) == 10
        assert len(window._rows_by_product_key) == 10
        prior_products.extend(current_batch)

    assert len(controller.start_calls) == 30
    assert len(window.queue_manager._known_request_ids) == 30
    window.close()


def test_retry_timer_from_cancelled_batch_cannot_fire_into_new_batch(
    qtbot,
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(
        item_timeout_ms=0,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=0.03,
            max_delay_seconds=0.03,
        ),
    )
    opened: list[tuple[str, str]] = []
    manager.send_open_product_requested.connect(
        lambda request_id, url: opened.append((request_id, url))
    )

    assert manager.start_batch([(0, "https://shopee.vn/batch-a")])
    batch_a_request = manager.current_item.request_id
    manager.handle_process_error(
        batch_a_request,
        manager.current_item.input_url,
        "PRODUCT_TIMEOUT",
        "retry then cancel",
    )
    assert manager._retry_timer.isActive()
    assert manager.cancel_batch()
    assert manager.state == QueueState.IDLE
    assert not manager._retry_timer.isActive()

    assert manager.start_batch([(0, "https://shopee.vn/batch-b")])
    batch_b_request = manager.current_item.request_id
    qtbot.wait(80)
    assert [request_id for request_id, _url in opened] == [
        batch_a_request,
        batch_b_request,
    ]
    _complete_product(manager, tmp_path, 2)
    assert manager.items[0].state == ItemState.SUCCESS


def test_stale_generations_are_rejected_repeatedly_across_many_items(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(
        item_timeout_ms=0,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_delay_seconds=60,
            max_delay_seconds=60,
        ),
    )
    download_starts: list[str | None] = []
    manager.item_download_requested.connect(
        lambda _row, product: download_starts.append(product.request_id)
    )
    assert manager.start_batch(
        [(row, f"https://shopee.vn/stale-{row}") for row in range(25)]
    )

    for row in range(25):
        item = manager.current_item
        assert item is not None and item.row_idx == row
        stale_request = item.request_id
        stale_product = _product(stale_request, row + 1)
        manager.handle_process_error(
            stale_request,
            item.input_url,
            "PRODUCT_TIMEOUT",
            "force next request generation",
        )
        manager._retry_timer.stop()
        manager._on_retry_timeout()
        current_request = item.request_id
        assert current_request != stale_request

        for _ in range(5):
            manager.handle_process_progress(stale_request, "scanning_gallery")
            manager.handle_process_error(
                stale_request,
                item.input_url,
                "NOT_FOUND",
                "stale error",
            )
            manager.handle_product_result(stale_product)
        assert item.state == ItemState.OPENING_PRODUCT
        assert item.request_id == current_request
        assert download_starts == [
            request_id for request_id in download_starts
            if request_id != stale_request
        ]

        _complete_product(manager, tmp_path, row + 1)

    assert manager.state == QueueState.IDLE
    assert len(download_starts) == 25
    assert len(set(download_starts)) == 25
    assert [item.attempt for item in manager.items] == [2] * 25


def test_rapid_duplicate_signals_transition_and_advance_exactly_once(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    started_rows: list[int] = []
    download_rows: list[int] = []
    completed_rows: list[int] = []
    progress_by_row: dict[int, list[tuple[int, int]]] = {}
    manager.item_started.connect(
        lambda row, _url, _request_id: started_rows.append(row)
    )
    manager.item_download_requested.connect(
        lambda row, _product_data: download_rows.append(row)
    )
    manager.item_completed.connect(
        lambda row, _product_data: completed_rows.append(row)
    )
    manager.item_image_progress.connect(
        lambda row, current, total: progress_by_row.setdefault(row, []).append(
            (current, total)
        )
    )
    assert manager.start_batch(
        [(row, f"https://shopee.vn/duplicate-signal-{row}") for row in range(30)]
    )

    for row in range(30):
        item = manager.current_item
        assert item is not None and item.row_idx == row
        product = _product(item.request_id, row + 1)
        for _ in range(10):
            manager.handle_product_result(product)
        assert item.state == ItemState.CREATING_FOLDER
        enriched = _folder_ready(product, tmp_path)
        for _ in range(10):
            manager.handle_product_folder_ready(enriched)
        assert item.state == ItemState.DOWNLOADING
        for index in range(1, 4):
            for _ in range(25):
                manager.handle_download_progress(enriched, index, 3)
        manager.handle_metadata_started(enriched)
        manager.handle_metadata_started(enriched)
        completed = _terminal_product(enriched)
        manager.handle_download_result(completed)
        for _ in range(10):
            manager.handle_download_result(completed)
            manager.handle_pipeline_failure(
                enriched,
                "IMAGE_DOWNLOAD_ERROR",
                "duplicate stale worker error",
            )

    assert manager.state == QueueState.IDLE
    assert started_rows == list(range(30))
    assert download_rows == list(range(30))
    assert completed_rows == list(range(30))
    assert all(item.state == ItemState.SUCCESS for item in manager.items)
    assert all(history[-1] == (3, 3) for history in progress_by_row.values())


@pytest.mark.parametrize(
    "stage",
    ["opening", "extraction", "retry", "folder", "download", "metadata"],
)
def test_cancel_at_each_queue_stage_stops_before_next_product(
    stage: str,
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(
        item_timeout_ms=60_000,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=60,
            max_delay_seconds=60,
        ),
    )
    started_rows: list[int] = []
    manager.item_started.connect(
        lambda row, _url, _request_id: started_rows.append(row)
    )
    assert manager.start_batch(
        [(0, "https://shopee.vn/a"), (1, "https://shopee.vn/b")]
    )
    item = manager.current_item
    assert item is not None
    product: BridgeProductData | None = None

    if stage == "extraction":
        manager.handle_process_progress(item.request_id, "waiting_page")
    elif stage == "retry":
        manager.handle_process_error(
            item.request_id,
            item.input_url,
            "PRODUCT_TIMEOUT",
            "waiting for retry",
        )
        assert manager._retry_timer.isActive()
    elif stage in {"folder", "download", "metadata"}:
        product = _product(item.request_id, 1)
        manager.handle_product_result(product)
        if stage in {"download", "metadata"}:
            product = _folder_ready(product, tmp_path)
            manager.handle_product_folder_ready(product)
        if stage == "metadata":
            manager.handle_metadata_started(product)

    assert manager.cancel_batch()
    if stage in {"folder", "download", "metadata"}:
        assert manager.state == QueueState.CANCELLING
        assert product is not None
        manager.handle_download_cancelled(product)

    assert manager.state == QueueState.IDLE
    assert [item.state for item in manager.items] == [
        ItemState.CANCELLED,
        ItemState.CANCELLED,
    ]
    assert started_rows == [0]
    assert not manager._timeout_timer.isActive()
    assert not manager._retry_timer.isActive()
    _assert_accounting(manager)


def test_cancel_then_new_batch_rejects_all_old_worker_callbacks(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    assert manager.start_batch(
        [(0, "https://shopee.vn/a-1"), (1, "https://shopee.vn/a-2")]
    )
    batch_a_item = manager.current_item
    batch_a_product = _product(batch_a_item.request_id, 1)
    manager.handle_product_result(batch_a_product)
    batch_a_product = _folder_ready(batch_a_product, tmp_path, label="batch-a")
    manager.handle_product_folder_ready(batch_a_product)
    assert manager.cancel_batch()
    manager.handle_download_cancelled(batch_a_product)
    assert manager.state == QueueState.IDLE

    assert manager.start_batch([(0, "https://shopee.vn/b-1")])
    batch_b_item = manager.current_item
    assert batch_b_item is not None
    batch_b_request = batch_b_item.request_id
    stale_completed = _terminal_product(batch_a_product)
    for _ in range(20):
        manager.handle_download_progress(batch_a_product, 1, 3)
        manager.handle_metadata_started(batch_a_product)
        manager.handle_download_result(stale_completed)
        manager.handle_pipeline_failure(
            batch_a_product,
            "IMAGE_DOWNLOAD_ERROR",
            "stale batch A callback",
        )
        manager.handle_process_error(
            batch_a_product.request_id or "",
            batch_a_product.input_url,
            "NOT_FOUND",
            "stale batch A extraction error",
        )
    assert manager.current_item is batch_b_item
    assert batch_b_item.request_id == batch_b_request
    assert batch_b_item.state == ItemState.OPENING_PRODUCT

    _complete_product(manager, tmp_path, 2)
    assert manager.state == QueueState.IDLE
    assert len(manager.items) == 1
    assert manager.items[0].state == ItemState.SUCCESS


def test_bridge_disconnect_retry_reconnect_rejects_pre_reconnect_result(
    tmp_path: Path,
) -> None:
    controller = ImmediateImageDownloadController()
    window, bridge, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
        image_download_controller=controller,
    )
    sent: list[str] = []
    outcomes = iter([False, True, True])

    def send(message: str) -> bool:
        sent.append(message)
        return next(outcomes, True)

    bridge.send_message.side_effect = send
    window.queue_manager.retry_policy = RetryPolicy(
        max_attempts=3,
        initial_delay_seconds=60,
        max_delay_seconds=60,
    )
    window.url_input.setPlainText("https://shopee.vn/bridge-retry")
    window.start_button.click()
    item = window.queue_manager.current_item
    assert item is not None
    first_request = item.request_id
    assert item.state == ItemState.WAITING_RETRY
    assert len(sent) == 1

    window.queue_manager._retry_timer.stop()
    window.queue_manager._on_retry_timeout()
    second_request = item.request_id
    assert second_request != first_request
    assert item.state == ItemState.OPENING_PRODUCT
    assert len(sent) == 2

    window._on_bridge_product_received(
        ui_product(request_id=first_request, shop_id="71001", item_id="81001")
    )
    assert item.state == ItemState.OPENING_PRODUCT
    assert not controller.start_calls

    window._on_bridge_product_received(
        ui_product(request_id=second_request, shop_id="71002", item_id="81002")
    )
    assert window.queue_manager.state == QueueState.IDLE
    assert controller.start_calls == ["71002:81002"]
    assert [json.loads(message)["type"] for message in sent] == [
        "open_product",
        "open_product",
        "batch_finished",
    ]
    window.close()


def test_repeated_verification_events_pause_without_attempt_or_timer_churn(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    pauses: list[int] = []
    manager.verification_required.connect(
        lambda row, _url, _message: pauses.append(row)
    )
    assert manager.start_batch(
        [(0, "https://shopee.vn/verify"), (1, "https://shopee.vn/next")]
    )
    first = manager.current_item
    request_id = first.request_id
    for _ in range(20):
        manager.handle_process_error(
            request_id,
            first.input_url,
            "VERIFICATION_REQUIRED",
            "verification challenge",
        )
        assert manager.state == QueueState.PAUSED_VERIFICATION
        assert first.attempt == 1
        assert first.request_id == request_id
        assert not manager._retry_timer.isActive()

    assert pauses == [0] * 20
    assert manager.resume_verification()
    assert first.attempt == 1
    assert first.request_id != request_id
    _complete_product(manager, tmp_path, 1)
    assert manager.current_item is not None
    assert manager.current_item.row_idx == 1
    _complete_product(manager, tmp_path, 2)
    assert manager.state == QueueState.IDLE


def test_failure_log_keeps_queue_request_attempt_code_and_stage_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    caplog.set_level(logging.WARNING)
    assert manager.start_batch([(7, "https://shopee.vn/log-context")])
    item = manager.current_item
    manager.handle_process_error(
        item.request_id,
        item.input_url,
        "NOT_FOUND",
        "deterministic diagnostic failure",
    )

    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "Item 8" in message
    assert f"req={item.request_id}" in message
    assert "code=NOT_FOUND" in message
    assert "stage=EXTRACTION" in message
    assert "attempt=1/3" in message


class _Response:
    def __init__(
        self,
        body: bytes = b"image-bytes",
        *,
        status: int = 200,
        content_type: str = "image/jpeg",
        read_actions: Sequence[bytes | BaseException] | None = None,
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = BytesIO(body)
        self._read_actions = list(read_actions or [])

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if self._read_actions:
            action = self._read_actions.pop(0)
            if isinstance(action, BaseException):
                raise action
            return action
        return self._body.read(size)


class _ScriptedOpener:
    def __init__(self, actions: Sequence[_Response | BaseException]) -> None:
        self.actions = list(actions)
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> _Response:
        action = self.actions[self.calls]
        self.calls += 1
        if isinstance(action, BaseException):
            raise action
        return action


def _fast_downloader(opener: _ScriptedOpener, *, max_attempts: int = 3) -> ImageDownloader:
    return ImageDownloader(
        DownloadConfig(
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
            overall_timeout_seconds=2,
            max_attempts=max_attempts,
            retry_backoff_seconds=0,
            max_retry_after_seconds=0,
            chunk_size=8,
        ),
        open_url=opener,
        sleeper=lambda _seconds: None,
    )


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_network_transient_statuses_retry_exact_bound_and_leave_no_part(
    status: int,
    tmp_path: Path,
) -> None:
    opener = _ScriptedOpener([_Response(status=status) for _ in range(3)])
    result = _fast_downloader(opener).download_image(
        f"https://cdn.example/http-{status}.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )
    assert result.status == ImageDownloadStatus.FAILED
    assert result.attempts == 3
    assert opener.calls == 3
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize(
    ("failure", "expected_calls"),
    [
        (TimeoutError("timeout"), 3),
        (ConnectionResetError("connection reset"), 3),
        (
            HTTPError(
                "https://cdn.example/404.jpg",
                404,
                "not found",
                {},
                None,
            ),
            1,
        ),
    ],
)
def test_network_timeout_reset_and_404_classification_is_bounded(
    failure: BaseException,
    expected_calls: int,
    tmp_path: Path,
) -> None:
    opener = _ScriptedOpener([failure] * expected_calls)
    result = _fast_downloader(opener).download_image(
        "https://cdn.example/failure.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )
    assert result.status == ImageDownloadStatus.FAILED
    assert result.attempts == expected_calls
    assert opener.calls == expected_calls
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize(
    "response",
    [
        _Response(body=b"<html>not an image</html>", content_type=""),
        _Response(body=b"", content_type="image/jpeg"),
        _Response(body=b"json", content_type="application/json"),
    ],
)
def test_invalid_html_json_and_empty_bodies_are_permanent_and_atomic(
    response: _Response,
    tmp_path: Path,
) -> None:
    opener = _ScriptedOpener([response])
    result = _fast_downloader(opener).download_image(
        "https://cdn.example/invalid.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )
    assert result.status == ImageDownloadStatus.FAILED
    assert result.attempts == 1
    assert opener.calls == 1
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.jpg"))


def test_mid_transfer_connection_reset_cleans_part_and_preserves_final(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "completed.jpg"
    sentinel.write_bytes(b"completed-final")
    response = _Response(
        read_actions=[b"first-chunk", ConnectionResetError("mid-transfer")]
    )
    opener = _ScriptedOpener([response])
    result = _fast_downloader(opener, max_attempts=1).download_image(
        "https://cdn.example/reset.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )
    assert result.status == ImageDownloadStatus.FAILED
    assert sentinel.read_bytes() == b"completed-final"
    assert not list(tmp_path.glob("*.part"))


def test_atomic_metadata_failure_then_success_preserves_valid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = _folder_ready(_product("metadata", 1, image_count=1), tmp_path)
    result_product = _terminal_product(product)
    old_metadata = {"schema_version": 1, "product_name": "Old valid value"}
    target = write_product_metadata(product.product_folder, old_metadata)
    old_bytes = target.read_bytes()
    new_metadata = build_product_metadata(
        product,
        result_product.download_result,
    )
    real_replace = metadata_module.os.replace

    def fail_replace(_source: object, _target: object) -> None:
        raise PermissionError("simulated interrupted metadata replace")

    monkeypatch.setattr(
        "shopee_image_downloader.core.product_metadata.os.replace",
        fail_replace,
    )
    with pytest.raises(Exception) as caught:
        write_product_metadata(product.product_folder, new_metadata)
    assert "simulated interrupted" in str(caught.value)
    assert json.loads(target.read_text(encoding="utf-8")) == old_metadata
    assert target.read_bytes() == old_bytes
    assert not (product.product_folder / PRODUCT_METADATA_TEMP_FILENAME).exists()

    monkeypatch.setattr(
        "shopee_image_downloader.core.product_metadata.os.replace",
        real_replace,
    )
    write_product_metadata(product.product_folder, new_metadata)
    current = json.loads(target.read_text(encoding="utf-8"))
    assert current["product_name"] == product.product_name
    assert current["image_count"] == 1
    assert len(current["images"]) == 1
    assert not (product.product_folder / PRODUCT_METADATA_TEMP_FILENAME).exists()


def test_partial_five_of_nine_reuses_folder_completes_four_and_refreshes_metadata(
    tmp_path: Path,
) -> None:
    folder = ensure_product_folder(tmp_path, "Old title", "101", "202")
    existing_bytes: dict[Path, bytes] = {}
    for index in range(1, 6):
        path = folder / f"{index:02d}.jpg"
        payload = f"existing-{index}".encode()
        path.write_bytes(payload)
        existing_bytes[path] = payload

    images = [f"https://cdn.example/nine/{index}.jpg" for index in range(1, 10)]
    opener = _ScriptedOpener([_Response(body=f"new-{index}".encode()) for index in range(1, 10)])
    result = _fast_downloader(opener, max_attempts=1).download_product_images(
        images,
        ensure_product_folder(tmp_path, "New title", "101", "202"),
    )
    product = BridgeProductData(
        url="https://shopee.vn/nine-i.101.202",
        input_url="https://shopee.vn/nine-input",
        final_url="https://shopee.vn/nine-i.101.202",
        product_name="New title",
        shop_id="101",
        item_id="202",
        images=images,
        image_count=9,
        request_id="nine-request",
        product_folder=folder,
    )
    write_product_metadata(folder, build_product_metadata(product, result))

    assert ensure_product_folder(tmp_path, "Another title", "101", "202") == folder
    assert all(path.read_bytes() == payload for path, payload in existing_bytes.items())
    assert len(list(folder.glob("*.jpg"))) == 9
    assert result.total == 9
    assert result.skipped == 5
    assert result.successful == 4
    metadata = json.loads((folder / PRODUCT_METADATA_FILENAME).read_text(encoding="utf-8"))
    assert metadata["image_count"] == 9
    assert len(metadata["images"]) == 9
    assert metadata["download"] == {
        "total": 9,
        "successful": 4,
        "failed": 0,
        "skipped": 5,
    }
    assert not list(folder.glob("*.part"))


def test_complete_product_reprocess_reuses_folder_preserves_files_and_metadata(
    tmp_path: Path,
) -> None:
    folder = ensure_product_folder(tmp_path, "Complete title", "303", "404")
    images = [f"https://cdn.example/complete/{index}.jpg" for index in range(1, 10)]
    first_result = _fast_downloader(
        _ScriptedOpener([_Response(body=f"first-{index}".encode()) for index in range(1, 10)]),
        max_attempts=1,
    ).download_product_images(images, folder)
    before = {path.name: path.read_bytes() for path in folder.glob("*.jpg")}

    reused = ensure_product_folder(tmp_path, "Changed complete title", "303", "404")
    second_result = _fast_downloader(
        _ScriptedOpener([_Response(body=f"second-{index}".encode()) for index in range(1, 10)]),
        max_attempts=1,
    ).download_product_images(images, reused)
    product = BridgeProductData(
        url="https://shopee.vn/complete-i.303.404",
        input_url="https://shopee.vn/reprocess-input",
        final_url="https://shopee.vn/complete-i.303.404",
        product_name="Changed complete title",
        shop_id="303",
        item_id="404",
        images=images,
        image_count=9,
        request_id="reprocess",
        product_folder=reused,
    )
    write_product_metadata(reused, build_product_metadata(product, second_result))

    assert reused == folder
    assert first_result.successful == 9
    assert second_result.skipped == 9
    assert {path.name: path.read_bytes() for path in folder.glob("*.jpg")} == before
    assert len([path for path in tmp_path.iterdir() if path.is_dir()]) == 1
    metadata = json.loads((folder / PRODUCT_METADATA_FILENAME).read_text(encoding="utf-8"))
    assert metadata["product_name"] == "Changed complete title"
    assert metadata["source_url"] == "https://shopee.vn/reprocess-input"
    assert metadata["download"]["skipped"] == 9


def test_many_same_title_products_get_distinct_correct_identity_markers(
    tmp_path: Path,
) -> None:
    folders: dict[str, Path] = {}
    for number in range(1, 41):
        folder = ensure_product_folder(
            tmp_path,
            "Tên trùng / collision:*?",
            str(1_000 + number),
            str(2_000 + number),
        )
        key = f"{1_000 + number}:{2_000 + number}"
        folders[key] = folder
        assert (folder / PRODUCT_ID_MARKER_FILENAME).read_text(
            encoding="utf-8"
        ).strip() == key

    assert len(set(folders.values())) == 40
    for key, folder in folders.items():
        shop_id, item_id = key.split(":")
        assert ensure_product_folder(
            tmp_path,
            "Completely changed title",
            shop_id,
            item_id,
        ) == folder


@pytest.mark.parametrize(
    "name",
    [
        "Tên sản phẩm Việt Nam rất dài " + "áo quần đẹp " * 30,
        "Sản phẩm emoji 🛍️🔥✨ " * 12,
        "A\u0301o khoa\u0301c pho\u0302́i ma\u0300u " * 12,
        '< > : " / \\ | ? *',
        "CON",
        "LPT9.txt",
        "Tên có dấu chấm và khoảng trắng...   ",
        "../../foo",
        "..\\..\\Windows",
        "C:\\Windows",
        "/etc",
    ],
)
def test_long_unicode_and_path_like_names_are_safe_bounded_and_contained(
    name: str,
    tmp_path: Path,
) -> None:
    sanitized = sanitize_product_folder_name(name, "501", "601")
    assert sanitized
    assert len(sanitized) <= MAX_PRODUCT_FOLDER_NAME_LENGTH
    assert sanitized == sanitized.rstrip(" .")
    assert "/" not in sanitized and "\\" not in sanitized
    folder = ensure_product_folder(tmp_path, name, "501", "601")
    assert folder.resolve().parent == tmp_path.resolve()
    assert len(folder.name) <= MAX_PRODUCT_FOLDER_NAME_LENGTH
    assert (folder / PRODUCT_ID_MARKER_FILENAME).read_text(
        encoding="utf-8"
    ).strip() == "501:601"


def test_multiple_marker_claims_fail_without_modifying_either_directory(
    tmp_path: Path,
) -> None:
    first = tmp_path / "claim-a"
    second = tmp_path / "claim-b"
    first.mkdir()
    second.mkdir()
    for folder in (first, second):
        (folder / PRODUCT_ID_MARKER_FILENAME).write_text(
            "901:902\n",
            encoding="utf-8",
        )
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    with pytest.raises(ProductFolderError) as caught:
        ensure_product_folder(tmp_path, "Conflicting product", "901", "902")

    assert caught.value.error.error_code == "MULTIPLE_PRODUCT_FOLDERS"
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["claim-a", "claim-b"]


class _FloodDownloader:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.flood_complete = threading.Event()

    def download_product_images(
        self,
        images: Sequence[str],
        product_folder: str | Path,
        *,
        progress_callback: Any = None,
        cancel_check: Any = None,
    ) -> ProductDownloadResult:
        self.started.set()
        total = len(images)
        for index in range(1, total + 1):
            if progress_callback is not None:
                progress_callback(index, total)
        self.flood_complete.set()
        while cancel_check is not None and not cancel_check():
            threading.Event().wait(0.002)
        raise DownloadCancelledError("cancelled after progress flood")


def test_high_frequency_worker_progress_keeps_ui_correlated_and_cancellable(
    tmp_path: Path,
    qtbot,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    settings = SettingsManager(config_path=tmp_path / "settings.json")
    settings.set_output_folder(output_root)
    bridge = MagicMock(spec=ExtensionBridgeServer)
    bridge.has_connected_clients = True
    downloader = _FloodDownloader()
    controller = ImageDownloadController(downloader=downloader)
    window = MainWindow(
        settings_manager=settings,
        bridge_server=bridge,
        image_download_controller=controller,
        start_bridge=False,
    )
    qtbot.addWidget(window)
    window.show()
    event_loop_tick = threading.Event()
    QTimer.singleShot(10, event_loop_tick.set)
    window.url_input.setPlainText("https://shopee.vn/progress-flood")
    window.start_button.click()
    current = window.queue_manager.current_item
    images = [f"https://cdn.example/flood/{index}.jpg" for index in range(1, 5001)]
    window._on_bridge_product_received(
        BridgeProductData(
            url="https://shopee.vn/flood-i.111.222",
            product_name="Progress flood",
            shop_id="111",
            item_id="222",
            images=images,
            image_count=len(images),
            request_id=current.request_id,
        )
    )

    qtbot.waitUntil(downloader.flood_complete.is_set, timeout=3000)
    qtbot.waitUntil(event_loop_tick.is_set, timeout=3000)
    qtbot.waitUntil(
        lambda: window.results_table.item(0, window.COL_IMAGES).text()
        == "5000/5000",
        timeout=5000,
    )
    assert window.queue_manager.current_item.row_idx == 0
    assert window.queue_manager.current_item.state == ItemState.DOWNLOADING
    assert window.cancel_button.isEnabled()
    window.cancel_button.click()
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=3000)
    qtbot.waitUntil(lambda: window.queue_manager.state == QueueState.IDLE, timeout=3000)
    assert window.queue_manager.items[0].state == ItemState.CANCELLED
    assert not list(output_root.rglob("*.part"))
    window.close()


def test_request_tombstones_are_intentionally_session_persistent_while_live_state_resets(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    all_requests: set[str] = set()
    for batch in range(5):
        assert manager.start_batch(
            [(row, f"https://shopee.vn/tombstone-{batch}-{row}") for row in range(20)]
        )
        for row in range(20):
            current = manager.current_item
            all_requests.add(current.request_id)
            _complete_product(manager, tmp_path, batch * 100 + row + 1)
        assert manager.state == QueueState.IDLE
        assert len(manager.items) == 20
        assert len(manager._reusable_products_by_key) == 20
        assert not manager._timeout_timer.isActive()
        assert not manager._retry_timer.isActive()

    assert len(all_requests) == 100
    assert manager._known_request_ids == all_requests
    assert all(manager.is_known_request(request_id) for request_id in all_requests)
    assert manager.current_item is None


def test_known_nine_image_model_remains_nine_through_worker_and_metadata(
    tmp_path: Path,
    qtbot,
) -> None:
    images = [f"https://cdn.example/known-nine/{index}.jpg" for index in range(1, 10)]
    opener = _ScriptedOpener([_Response(body=f"image-{index}".encode()) for index in range(1, 10)])
    controller = ImageDownloadController(
        downloader=_fast_downloader(opener, max_attempts=1)
    )
    product = BridgeProductData(
        url="https://shopee.vn/known-nine-i.12345.67890",
        input_url="https://shopee.vn/known-nine-input",
        final_url="https://shopee.vn/known-nine-i.12345.67890",
        product_name="Known 9 images plus one filtered video",
        shop_id="12345",
        item_id="67890",
        images=images,
        image_count=9,
        request_id="known-nine-request",
    )
    completed: list[tuple[BridgeProductData, ProductDownloadResult]] = []
    controller.finished.connect(
        lambda current, result: completed.append((current, result))
    )

    assert controller.start(product, str(tmp_path))
    qtbot.waitUntil(lambda: bool(completed), timeout=5000)
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=5000)
    completed_product, result = completed[0]
    metadata = json.loads(
        (completed_product.product_folder / PRODUCT_METADATA_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert product.images == images
    assert completed_product.images == images
    assert len(completed_product.images) == 9
    assert result.total == 9
    assert result.successful == 9
    assert len(list(completed_product.product_folder.glob("*.jpg"))) == 9
    assert metadata["image_count"] == 9
    assert len(metadata["images"]) == 9
    assert controller._thread is None
    assert controller._worker is None
    assert controller._context is None
