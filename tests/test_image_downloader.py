"""Offline tests for deterministic authoritative image downloading."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import threading
from typing import Any
from urllib.error import HTTPError

import pytest

from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.image_downloader import (
    DownloadCancelledError,
    DownloadConfig,
    ImageDownloader,
    ImageDownloadStatus,
    ProductDownloadResult,
)
from shopee_image_downloader.workers.image_download_worker import (
    ImageDownloadController,
)


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        content_type: str = "image/jpeg",
        status: int = 200,
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ScriptedOpener:
    def __init__(self, outcomes: list[FakeResponse | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.urls: list[str] = []
        self.timeouts: list[float] = []

    def __call__(self, request: Any, *, timeout: float) -> FakeResponse:
        self.urls.append(request.full_url)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class UrlMappedOpener:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, request: Any, *, timeout: float) -> FakeResponse:
        del timeout
        with self._lock:
            self.urls.append(request.full_url)
            return self.responses[request.full_url]


def _config(**changes: object) -> DownloadConfig:
    return replace(
        DownloadConfig(
            connect_timeout_seconds=0.5,
            read_timeout_seconds=0.75,
            overall_timeout_seconds=2.0,
            max_attempts=3,
            retry_backoff_seconds=0,
            chunk_size=4,
        ),
        **changes,
    )


def test_three_images_keep_input_order_content_and_mime_extensions(
    tmp_path: Path,
) -> None:
    urls = [
        "https://cdn.example/first",
        "https://cdn.example/second",
        "https://cdn.example/third",
    ]
    opener = UrlMappedOpener(
        {
            urls[0]: FakeResponse(b"jpeg-one", "image/jpeg"),
            urls[1]: FakeResponse(b"png-two", "image/png"),
            urls[2]: FakeResponse(b"webp-three", "image/webp"),
        }
    )
    progress: list[tuple[int, int]] = []
    downloader = ImageDownloader(_config(), open_url=opener)

    result = downloader.download_product_images(
        urls,
        tmp_path,
        progress_callback=lambda index, total: progress.append((index, total)),
    )

    assert sorted(opener.urls) == sorted(urls)
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert [item.target_path.name for item in result.items] == [
        "01.jpg",
        "02.png",
        "03.webp",
    ]
    assert (tmp_path / "01.jpg").read_bytes() == b"jpeg-one"
    assert (tmp_path / "02.png").read_bytes() == b"png-two"
    assert (tmp_path / "03.webp").read_bytes() == b"webp-three"
    assert result.total == 3
    assert result.successful == 3
    assert result.failed == 0
    assert result.skipped == 0


def test_filename_padding_expands_for_large_gallery(tmp_path: Path) -> None:
    opener = ScriptedOpener(
        [FakeResponse(b"first"), FakeResponse(b"last")]
    )
    downloader = ImageDownloader(_config(), open_url=opener)

    first = downloader.download_image(
        "https://cdn.example/first",
        index=1,
        total=120,
        product_folder=tmp_path,
    )
    last = downloader.download_image(
        "https://cdn.example/last",
        index=120,
        total=120,
        product_folder=tmp_path,
    )

    assert first.target_path.name == "001.jpg"
    assert last.target_path.name == "120.jpg"


def test_http_404_is_not_retried_and_leaves_no_partial_file(
    tmp_path: Path,
) -> None:
    opener = ScriptedOpener(
        [HTTPError("https://cdn.example/missing", 404, "Not Found", None, None)]
    )
    downloader = ImageDownloader(_config(), open_url=opener)

    result = downloader.download_image(
        "https://cdn.example/missing.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )

    assert result.status == ImageDownloadStatus.FAILED
    assert result.attempts == 1
    assert result.error == "HTTP 404"
    assert list(tmp_path.iterdir()) == []


def test_http_500_then_success_retries_once(tmp_path: Path) -> None:
    opener = ScriptedOpener(
        [
            FakeResponse(b"server error", "text/plain", status=500),
            FakeResponse(b"recovered", "image/png"),
        ]
    )
    downloader = ImageDownloader(_config(), open_url=opener)

    result = downloader.download_image(
        "https://cdn.example/image",
        index=1,
        total=1,
        product_folder=tmp_path,
    )

    assert result.status == ImageDownloadStatus.SUCCESS
    assert result.attempts == 2
    assert result.target_path.name == "01.png"
    assert result.target_path.read_bytes() == b"recovered"


def test_timeout_then_success_retries_once(tmp_path: Path) -> None:
    opener = ScriptedOpener(
        [TimeoutError("slow CDN"), FakeResponse(b"recovered", "image/webp")]
    )
    downloader = ImageDownloader(_config(), open_url=opener)

    result = downloader.download_image(
        "https://cdn.example/image",
        index=1,
        total=1,
        product_folder=tmp_path,
    )

    assert result.status == ImageDownloadStatus.SUCCESS
    assert result.attempts == 2
    assert result.target_path.name == "01.webp"


@pytest.mark.parametrize(
    ("response", "expected_error"),
    [
        (FakeResponse(b"<html>captcha</html>", "text/html"), "không phải ảnh"),
        (FakeResponse(b"", "image/jpeg"), "rỗng"),
        (FakeResponse(b'{"error": true}', "image/jpeg"), "HTML hoặc JSON"),
    ],
)
def test_invalid_or_empty_response_is_not_saved_or_retried(
    tmp_path: Path,
    response: FakeResponse,
    expected_error: str,
) -> None:
    opener = ScriptedOpener([response])
    downloader = ImageDownloader(_config(), open_url=opener)

    result = downloader.download_image(
        "https://cdn.example/image.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )

    assert result.status == ImageDownloadStatus.FAILED
    assert result.attempts == 1
    assert expected_error in (result.error or "")
    assert not (tmp_path / "01.jpg").exists()
    assert not list(tmp_path.glob("*.part"))


def test_existing_nonempty_target_is_preserved_and_reported_skipped(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "01.jpg"
    existing.write_bytes(b"user-existing-bytes")
    opener = ScriptedOpener([FakeResponse(b"new-server-bytes", "image/jpeg")])
    downloader = ImageDownloader(_config(), open_url=opener)

    result = downloader.download_image(
        "https://cdn.example/image.jpg",
        index=1,
        total=1,
        product_folder=tmp_path,
    )

    assert result.status == ImageDownloadStatus.SKIPPED_EXISTING
    assert result.attempts == 1
    assert existing.read_bytes() == b"user-existing-bytes"
    assert not list(tmp_path.glob("*.part"))


def test_cancellation_removes_current_part_and_keeps_completed_files(
    tmp_path: Path,
) -> None:
    completed = tmp_path / "00.jpg"
    completed.write_bytes(b"completed")
    opener = ScriptedOpener([FakeResponse(b"abcdefghijk", "image/jpeg")])
    downloader = ImageDownloader(_config(chunk_size=4), open_url=opener)
    checks = 0

    def cancel_during_stream() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 4

    with pytest.raises(DownloadCancelledError):
        downloader.download_image(
            "https://cdn.example/image.jpg",
            index=1,
            total=1,
            product_folder=tmp_path,
            cancel_check=cancel_during_stream,
        )

    assert completed.read_bytes() == b"completed"
    assert not (tmp_path / "01.jpg").exists()
    assert not list(tmp_path.glob("*.part"))


def test_nine_image_product_stores_result_without_mutating_authoritative_urls(
    tmp_path: Path,
) -> None:
    urls = [f"https://cdn.example/{index}" for index in range(1, 10)]
    original_urls = list(urls)
    opener = ScriptedOpener(
        [FakeResponse(f"image-{index}".encode()) for index in range(1, 10)]
    )
    downloader = ImageDownloader(_config(), open_url=opener)
    product = BridgeProductData(
        url="https://shopee.vn/product-i.78513158.28469164720",
        product_name="Known product",
        shop_id="78513158",
        item_id="28469164720",
        images=urls,
        image_count=9,
        product_folder=tmp_path,
    )

    result = downloader.download_product_images(
        product.images,
        product.product_folder,
    )
    stored = replace(product, download_result=result)

    assert len(list(tmp_path.glob("*.jpg"))) == 9
    assert result.total == 9
    assert result.successful == 9
    assert result.failed == 0
    assert product.images == original_urls
    assert stored.images == original_urls
    assert stored.download_result == result


class RecordingDownloader(ImageDownloader):
    def __init__(self) -> None:
        super().__init__(_config())
        self.thread_id: int | None = None

    def download_product_images(
        self,
        images: list[str],
        product_folder: str | Path,
        *,
        progress_callback: Any = None,
        cancel_check: Any = None,
    ) -> ProductDownloadResult:
        self.thread_id = threading.get_ident()
        return ProductDownloadResult.from_items(len(images), ())


def test_controller_runs_downloader_outside_gui_thread(tmp_path: Path, qtbot) -> None:
    downloader = RecordingDownloader()
    controller = ImageDownloadController(downloader=downloader)
    product = BridgeProductData(
        url="https://shopee.vn/product-i.1.2",
        product_name="Thread test",
        shop_id="1",
        item_id="2",
        images=[],
        image_count=0,
        product_folder=tmp_path,
    )
    gui_thread_id = threading.get_ident()

    with qtbot.waitSignal(controller.finished, timeout=2000):
        assert controller.start(product, str(tmp_path))
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=2000)

    assert downloader.thread_id is not None
    assert downloader.thread_id != gui_thread_id
