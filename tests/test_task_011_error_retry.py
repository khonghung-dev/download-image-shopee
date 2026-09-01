"""Task 011 regressions for canonical errors and bounded retries."""

from __future__ import annotations

from dataclasses import replace
import errno
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest

from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    ItemState,
    QueueState,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.error_policy import (
    AppErrorException,
    ErrorCategory,
    ErrorStage,
    RetryPolicy,
    classify_error_code,
)
from shopee_image_downloader.core.image_downloader import (
    DownloadConfig,
    ImageDownloader,
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
)
from shopee_image_downloader.storage.product_folder import (
    ProductFolderError,
    ensure_product_folder,
)
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.ui.main_window import MainWindow
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer
from shopee_image_downloader.workers.image_download_worker import (
    ImageDownloadController,
)


def _policy(*, max_attempts: int = 3, delay: float = 60.0) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max_attempts,
        initial_delay_seconds=delay,
        max_delay_seconds=delay,
    )


def _product(
    request_id: str,
    number: int,
    *,
    image_count: int = 1,
) -> BridgeProductData:
    return BridgeProductData(
        url=f"https://shopee.vn/product-{number}",
        product_name=f"Product {number}",
        shop_id=str(1000 + number),
        item_id=str(2000 + number),
        images=[
            f"https://cdn.example/{number}/{index}.jpg"
            for index in range(1, image_count + 1)
        ],
        image_count=image_count,
        request_id=request_id,
    )


def _successful(product: BridgeProductData) -> BridgeProductData:
    assert product.product_folder is not None
    total = len(product.images)
    items = tuple(
        ImageDownloadResult(
            index=index,
            source_url=url,
            target_path=product.product_folder / f"{index:02d}.jpg",
            status=ImageDownloadStatus.SUCCESS,
            attempts=1,
        )
        for index, url in enumerate(product.images, start=1)
    )
    return replace(
        product,
        download_result=ProductDownloadResult.from_items(total, items),
    )


def _complete_current(
    manager: BatchQueueManager,
    number: int,
    *,
    image_count: int = 1,
    folder: Path | None = None,
) -> BridgeProductData:
    item = manager.current_item
    assert item is not None
    product = _product(item.request_id, number, image_count=image_count)
    manager.handle_product_result(product)
    enriched = replace(
        product,
        product_folder=folder or Path(f"product-{number}"),
    )
    manager.handle_product_folder_ready(enriched)
    manager.handle_download_result(_successful(enriched))
    return enriched


def _fire_retry(manager: BatchQueueManager) -> None:
    manager._retry_timer.stop()
    manager._on_retry_timeout()


def test_canonical_error_code_classification() -> None:
    timeout = classify_error_code(
        "PRODUCT_TIMEOUT",
        stage=ErrorStage.EXTRACTION,
    )
    assert timeout.category == ErrorCategory.TRANSIENT
    assert classify_error_code(
        "NOT_FOUND",
        stage=ErrorStage.EXTRACTION,
    ).category == ErrorCategory.PERMANENT
    assert classify_error_code(
        "VERIFICATION_REQUIRED",
        stage=ErrorStage.EXTRACTION,
    ).category == ErrorCategory.USER_ACTION_REQUIRED
    protocol = classify_error_code(
        "PROTOCOL_INTEGRITY_ERROR",
        stage=ErrorStage.EXTRACTION,
    )
    assert protocol.category == ErrorCategory.INTERNAL
    assert protocol.stage == ErrorStage.PROTOCOL
    policy = RetryPolicy.product_default()
    assert policy.should_retry(timeout, 1)
    assert policy.should_retry(timeout, 2)
    assert not policy.should_retry(timeout, 3)
    assert policy.get_delay(1, timeout) == 1
    assert policy.get_delay(2, timeout) == 2


def test_transient_product_failure_then_success_keeps_one_item_row_and_folder(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    logical_items = []
    started: list[tuple[int, str]] = []
    download_calls: list[str | None] = []

    def download_once(_row: int, product: BridgeProductData) -> None:
        download_calls.append(product.request_id)
        product_folder = ensure_product_folder(
            tmp_path,
            product.product_name,
            product.shop_id,
            product.item_id,
        )
        enriched = replace(product, product_folder=product_folder)
        manager.handle_product_folder_ready(enriched)
        manager.handle_download_result(_successful(enriched))

    manager.item_started.connect(
        lambda row, _url, request: started.append((row, request))
    )
    manager.item_download_requested.connect(download_once)
    assert manager.start_batch([(0, "https://shopee.vn/a")])
    logical_items.append(manager.current_item)
    first_request = manager.current_item.request_id

    manager.handle_process_error(
        first_request,
        "https://shopee.vn/a",
        "PRODUCT_TIMEOUT",
        "extension timed out",
    )
    assert manager.current_item is logical_items[0]
    assert manager.current_item.state == ItemState.WAITING_RETRY

    _fire_retry(manager)
    second_request = manager.current_item.request_id
    assert second_request != first_request
    assert manager.current_item.attempt == 2
    manager.handle_product_result(_product(second_request, 1))

    assert manager.items[0] is logical_items[0]
    assert manager.items[0].state == ItemState.SUCCESS
    assert [row for row, _request in started] == [0, 0]
    assert len(download_calls) == 1
    assert len(list(tmp_path.iterdir())) == 1
    assert manager.total_count == 1


def test_transient_exhaustion_uses_exact_max_attempts_then_advances() -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    opened_rows: list[int] = []
    manager.item_started.connect(
        lambda row, _url, _request: opened_rows.append(row)
    )
    manager.start_batch(
        [(0, "https://shopee.vn/a"), (1, "https://shopee.vn/b")]
    )
    first_item = manager.current_item
    assert first_item is not None

    for attempt in range(1, 4):
        manager.handle_process_error(
            manager.current_item.request_id,
            manager.current_item.input_url,
            "PRODUCT_TIMEOUT",
            f"timeout {attempt}",
        )
        if attempt < 3:
            assert manager.current_item is first_item
            assert manager.current_item.state == ItemState.WAITING_RETRY
            _fire_retry(manager)

    assert first_item.state == ItemState.FAILED
    assert first_item.attempt == 3
    assert manager.current_item is not None
    assert manager.current_item.row_idx == 1
    assert opened_rows == [0, 0, 0, 1]


def test_permanent_product_error_fails_without_backoff_and_advances() -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    manager.start_batch(
        [(0, "https://shopee.vn/a"), (1, "https://shopee.vn/b")]
    )
    failed = manager.current_item
    manager.handle_process_error(
        failed.request_id,
        failed.input_url,
        "NOT_FOUND",
        "raw extension detail",
    )

    assert failed.state == ItemState.FAILED
    assert failed.attempt == 1
    assert failed.last_error is not None
    assert failed.last_error.technical_message == "raw extension detail"
    assert failed.error_message == "Không tìm thấy sản phẩm."
    assert not manager._retry_timer.isActive()
    assert manager.current_item.row_idx == 1


def test_verification_pause_resume_does_not_consume_retry_attempt() -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    opened: list[str] = []
    manager.send_open_product_requested.connect(
        lambda request, _url: opened.append(request)
    )
    manager.start_batch([(0, "https://shopee.vn/verify")])
    item = manager.current_item
    request_id = item.request_id
    manager.handle_process_error(
        request_id,
        item.input_url,
        "VERIFICATION_REQUIRED",
        "captcha",
    )

    assert manager.state == QueueState.PAUSED_VERIFICATION
    assert item.attempt == 1
    assert not manager._retry_timer.isActive()
    assert manager.resume_verification()
    assert item.attempt == 1
    resumed_request_id = item.request_id
    assert resumed_request_id != request_id
    assert opened == [request_id, resumed_request_id]

    manager.handle_product_result(_product(request_id, 99))
    assert item.state == ItemState.OPENING_PRODUCT


def test_stale_result_and_error_from_previous_attempt_are_ignored() -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    manager.start_batch([(0, "https://shopee.vn/a")])
    item = manager.current_item
    first_request = item.request_id
    manager.handle_process_error(
        first_request,
        item.input_url,
        "PRODUCT_TIMEOUT",
        "timeout",
    )
    _fire_retry(manager)
    second_request = item.request_id

    manager.handle_product_result(_product(first_request, 99))
    manager.handle_process_error(
        first_request,
        item.input_url,
        "PRODUCT_TIMEOUT",
        "late error",
    )

    assert item.request_id == second_request
    assert item.state == ItemState.OPENING_PRODUCT
    assert item.product_data is None
    assert item.attempt == 2


def test_cancel_during_backoff_prevents_scheduled_retry(qtbot) -> None:
    manager = BatchQueueManager(
        item_timeout_ms=0,
        retry_policy=_policy(delay=0.03),
    )
    opened: list[str] = []
    manager.send_open_product_requested.connect(
        lambda request, _url: opened.append(request)
    )
    manager.start_batch([(0, "https://shopee.vn/a")])
    item = manager.current_item
    manager.handle_process_error(
        item.request_id,
        item.input_url,
        "PRODUCT_TIMEOUT",
        "timeout",
    )
    assert item.state == ItemState.WAITING_RETRY
    assert manager.cancel_batch()
    qtbot.wait(60)

    assert len(opened) == 1
    assert item.state == ItemState.CANCELLED
    assert manager.state == QueueState.IDLE
    assert not manager._retry_timer.isActive()


def test_three_product_mix_preserves_total_and_order() -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    manager.start_batch(
        [
            (0, "https://shopee.vn/a"),
            (1, "https://shopee.vn/b"),
            (2, "https://shopee.vn/c"),
        ]
    )
    item_a = manager.current_item
    manager.handle_process_error(
        item_a.request_id,
        item_a.input_url,
        "PRODUCT_TIMEOUT",
        "timeout",
    )
    _fire_retry(manager)
    _complete_current(manager, 1)
    item_b = manager.current_item
    manager.handle_process_error(
        item_b.request_id,
        item_b.input_url,
        "NOT_FOUND",
        "missing",
    )
    _complete_current(manager, 3)

    assert manager.total_count == 3
    assert [item.state for item in manager.items] == [
        ItemState.SUCCESS,
        ItemState.FAILED,
        ItemState.SUCCESS,
    ]
    assert manager.items[0].attempt == 2
    assert manager.get_success_count() == 2
    assert manager.get_fail_count() == 1


def test_nine_image_result_survives_product_retry_unchanged() -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    manager.start_batch([(0, "https://shopee.vn/nine")])
    item = manager.current_item
    manager.handle_process_error(
        item.request_id,
        item.input_url,
        "PRODUCT_TIMEOUT",
        "timeout",
    )
    _fire_retry(manager)
    original_images = [f"https://cdn.example/{index}.jpg" for index in range(9)]
    product = replace(
        _product(item.request_id, 9, image_count=9),
        images=original_images,
        image_count=9,
    )
    manager.handle_product_result(product)

    assert item.state == ItemState.CREATING_FOLDER
    assert item.product_data is not None
    assert item.product_data.images == original_images
    assert len(item.product_data.images) == 9


class _FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "image/jpeg",
        retry_after: str | None = None,
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after
        self._body = BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _Opener:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, _request: Any, *, timeout: float) -> _FakeResponse:
        assert timeout > 0
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _download_config(**changes: object) -> DownloadConfig:
    return replace(
        DownloadConfig(
            connect_timeout_seconds=0.5,
            read_timeout_seconds=0.5,
            overall_timeout_seconds=2,
            max_attempts=3,
            retry_backoff_seconds=0.25,
            max_retry_after_seconds=4,
            chunk_size=64,
        ),
        **changes,
    )


def test_downloader_429_respects_bounded_retry_after_without_real_sleep(
    tmp_path: Path,
) -> None:
    error = HTTPError(
        "https://cdn.example/image",
        429,
        "Too Many Requests",
        {"Retry-After": "999"},
        None,
    )
    opener = _Opener([error, _FakeResponse(b"recovered")])
    delays: list[float] = []
    downloader = ImageDownloader(
        _download_config(),
        open_url=opener,
        sleeper=delays.append,
    )

    result = downloader.download_image(
        "https://cdn.example/image.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )

    assert result.status == ImageDownloadStatus.SUCCESS
    assert result.attempts == 2
    assert opener.calls == 2
    assert delays == [4]


@pytest.mark.parametrize(
    ("status", "expected_calls"),
    [(404, 1), (500, 3)],
)
def test_downloader_404_is_permanent_and_500_is_bounded(
    tmp_path: Path,
    status: int,
    expected_calls: int,
) -> None:
    opener = _Opener(
        [
            _FakeResponse(b"error", status=status, content_type="text/plain")
            for _ in range(expected_calls)
        ]
    )
    downloader = ImageDownloader(
        _download_config(retry_backoff_seconds=0),
        open_url=opener,
        sleeper=lambda _delay: None,
    )

    result = downloader.download_image(
        "https://cdn.example/image.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )

    assert result.status == ImageDownloadStatus.FAILED
    assert result.attempts == expected_calls
    assert opener.calls == expected_calls


def test_permission_error_is_permanent_for_folder_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_mkdir(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied by test")

    monkeypatch.setattr(Path, "mkdir", deny_mkdir)
    with pytest.raises(ProductFolderError) as caught:
        ensure_product_folder(tmp_path, "Product", "1", "2")

    assert caught.value.error.error_code == "PERMISSION_DENIED"
    assert caught.value.error.category == ErrorCategory.PERMANENT
    assert caught.value.error.retryable is False
    assert caught.value.error.user_message == (
        "Không có quyền ghi vào thư mục đầu ra."
    )


def test_permission_failure_does_not_retry_product_and_next_item_continues() -> None:
    manager = BatchQueueManager(item_timeout_ms=0, retry_policy=_policy())
    manager.start_batch(
        [(0, "https://shopee.vn/a"), (1, "https://shopee.vn/b")]
    )
    first = manager.current_item
    product = _product(first.request_id, 1)
    manager.handle_product_result(product)
    manager.handle_pipeline_failure(
        product,
        "PERMISSION_DENIED",
        "PermissionError: denied by test",
    )

    assert first.state == ItemState.FAILED
    assert first.attempt == 1
    assert first.error_message == "Không có quyền ghi vào thư mục đầu ra."
    assert manager.current_item.row_idx == 1
    assert not manager._retry_timer.isActive()


def test_disk_full_aborts_without_retry_and_preserves_completed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = tmp_path / "00.jpg"
    completed.write_bytes(b"completed")
    opener = _Opener([_FakeResponse(b"new image")])
    downloader = ImageDownloader(
        _download_config(retry_backoff_seconds=0),
        open_url=opener,
        sleeper=lambda _delay: None,
    )

    def no_space(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "no space left")

    monkeypatch.setattr(Path, "open", no_space)
    with pytest.raises(AppErrorException) as caught:
        downloader.download_image(
            "https://cdn.example/image.jpg",
            index=1,
            total=1,
            product_folder=tmp_path,
        )

    assert caught.value.error.error_code == "DISK_FULL"
    assert caught.value.error.category == ErrorCategory.PERMANENT
    assert caught.value.error.user_message == "Không đủ dung lượng ổ đĩa."
    assert opener.calls == 1
    monkeypatch.undo()
    assert completed.read_bytes() == b"completed"
    assert not list(tmp_path.glob("*.part"))


def test_download_write_permission_error_is_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = _Opener([_FakeResponse(b"new image")])
    downloader = ImageDownloader(
        _download_config(retry_backoff_seconds=0),
        open_url=opener,
        sleeper=lambda _delay: None,
    )

    def deny_write(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied by test")

    monkeypatch.setattr(Path, "open", deny_write)
    with pytest.raises(AppErrorException) as caught:
        downloader.download_image(
            "https://cdn.example/image.jpg",
            index=1,
            total=1,
            product_folder=tmp_path,
        )

    assert caught.value.error.error_code == "PERMISSION_DENIED"
    assert caught.value.error.retryable is False
    assert opener.calls == 1


class _ExplodingDownloader:
    def download_product_images(
        self,
        images: list[str],
        product_folder: str | Path,
        *,
        progress_callback: Any = None,
        cancel_check: Any = None,
    ) -> ProductDownloadResult:
        raise RuntimeError("synthetic worker failure")


def test_unexpected_downloader_exception_becomes_controlled_internal_failure(
    tmp_path: Path,
    qtbot,
) -> None:
    controller = ImageDownloadController(downloader=_ExplodingDownloader())
    product = _product("unexpected-worker", 1)

    with qtbot.waitSignal(controller.failed, timeout=2000) as failure:
        assert controller.start(product, str(tmp_path))
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=2000)

    failed_product, code, message = failure.args
    assert failed_product.request_id == product.request_id
    assert code == "INTERNAL_ERROR"
    assert message == "Lỗi nội bộ khi xử lý sản phẩm."
    assert controller._thread is None
    assert controller._worker is None


def test_window_close_during_backoff_cancels_retry_timer(
    tmp_path: Path,
    qtbot,
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    settings = SettingsManager(config_path=tmp_path / "settings.json")
    settings.set_output_folder(output)
    bridge = MagicMock(spec=ExtensionBridgeServer)
    bridge.has_connected_clients = True
    sent_messages: list[str] = []
    bridge.send_message.side_effect = lambda message: sent_messages.append(message)
    window = MainWindow(
        settings_manager=settings,
        bridge_server=bridge,
        start_bridge=False,
    )
    qtbot.addWidget(window)
    window.queue_manager.retry_policy = _policy(delay=0.03)
    window.url_input.setPlainText("https://shopee.vn/product-1")
    window.start_button.click()
    current = window.queue_manager.current_item
    window._on_bridge_process_error_received(
        current.request_id,
        current.input_url,
        "PRODUCT_TIMEOUT",
        "timeout",
    )
    assert current.state == ItemState.WAITING_RETRY

    window.close()
    qtbot.wait(60)

    open_messages = [
        message
        for message in sent_messages
        if json.loads(message).get("type") == "open_product"
    ]
    assert len(open_messages) == 1
    assert current.state == ItemState.CANCELLED
    assert not window.queue_manager._retry_timer.isActive()
