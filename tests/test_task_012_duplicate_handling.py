"""Task 012 product identity, reuse, and duplicate regressions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
from typing import Any

import pytest

from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    ItemState,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.error_policy import ErrorCategory, RetryPolicy
from shopee_image_downloader.core.image_downloader import (
    DownloadConfig,
    ImageDownloadResult,
    ImageDownloadStatus,
    ImageDownloader,
    ProductDownloadResult,
)
from shopee_image_downloader.core.product_identity import canonical_product_key
from shopee_image_downloader.storage import product_folder as product_folder_module
from shopee_image_downloader.storage.product_folder import (
    PRODUCT_ID_MARKER_FILENAME,
    ProductFolderError,
    ensure_product_folder,
)


def _marker(folder: Path) -> Path:
    return folder / PRODUCT_ID_MARKER_FILENAME


def _write_marker(folder: Path, product_key: str) -> None:
    folder.mkdir()
    _marker(folder).write_text(f"{product_key}\n", encoding="utf-8")


def _product(
    request_id: str,
    *,
    shop_id: str = "1",
    item_id: str = "1",
    name: str = "Product",
    image_count: int = 2,
) -> BridgeProductData:
    return BridgeProductData(
        url=f"https://shopee.vn/{name}-i.{shop_id}.{item_id}",
        product_name=name,
        shop_id=shop_id,
        item_id=item_id,
        images=[
            f"https://images.example/{shop_id}-{item_id}-{index}.jpg"
            for index in range(1, image_count + 1)
        ],
        image_count=image_count,
        request_id=request_id,
    )


def _successful_download(product: BridgeProductData) -> BridgeProductData:
    assert product.product_folder is not None
    total = len(product.images)
    items = tuple(
        ImageDownloadResult(
            index=index,
            source_url=source_url,
            target_path=product.product_folder / f"{index:02d}.jpg",
            status=ImageDownloadStatus.SUCCESS,
            attempts=1,
        )
        for index, source_url in enumerate(product.images, start=1)
    )
    return replace(
        product,
        download_result=ProductDownloadResult.from_items(total, items),
    )


def test_canonical_product_key_and_atomic_marker_creation(tmp_path: Path) -> None:
    folder = ensure_product_folder(tmp_path, "Product Folder", "123", "456")

    assert canonical_product_key("123", "456") == "123:456"
    assert _marker(folder).read_text(encoding="utf-8").strip() == "123:456"
    assert not list(folder.glob(f"{PRODUCT_ID_MARKER_FILENAME}.*.tmp"))


def test_changed_title_reuses_cross_run_marker_owned_folder(tmp_path: Path) -> None:
    old_folder = tmp_path / "Old Product Name"
    _write_marker(old_folder, "123:456")

    resolved = ensure_product_folder(
        tmp_path,
        "New Product Name",
        "123",
        "456",
    )

    assert resolved == old_folder
    assert not (tmp_path / "New Product Name").exists()


def test_folder_discovery_does_not_scan_recursively(tmp_path: Path) -> None:
    container = tmp_path / "Unrelated Container"
    container.mkdir()
    nested = container / "Copied Product"
    _write_marker(nested, "123:456")

    resolved = ensure_product_folder(tmp_path, "Product", "123", "456")

    assert resolved == tmp_path / "Product"
    assert nested.is_dir()


def test_same_title_different_product_uses_identity_collision(tmp_path: Path) -> None:
    first = ensure_product_folder(tmp_path, "Product", "1", "1")
    second = ensure_product_folder(tmp_path, "Product", "2", "2")

    assert first == tmp_path / "Product"
    assert second == tmp_path / "Product [2-2]"
    assert _marker(first).read_text(encoding="utf-8").strip() == "1:1"
    assert _marker(second).read_text(encoding="utf-8").strip() == "2:2"


def test_unmarked_legacy_folder_is_preserved_and_not_adopted(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "Product"
    legacy.mkdir()
    user_file = legacy / "user.txt"
    user_file.write_text("keep", encoding="utf-8")

    resolved = ensure_product_folder(tmp_path, "Product", "1", "1")

    assert resolved == tmp_path / "Product [1-1]"
    assert user_file.read_text(encoding="utf-8") == "keep"
    assert not _marker(legacy).exists()
    assert _marker(resolved).read_text(encoding="utf-8").strip() == "1:1"


def test_corrupt_or_mismatched_marker_is_never_overwritten(
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "Product"
    _write_marker(corrupt, "garbage")

    resolved = ensure_product_folder(tmp_path, "Product", "1", "1")

    assert resolved == tmp_path / "Product [1-1]"
    assert _marker(corrupt).read_text(encoding="utf-8") == "garbage\n"
    assert _marker(resolved).read_text(encoding="utf-8").strip() == "1:1"


def test_multiple_folders_claiming_one_key_fail_permanently_without_changes(
    tmp_path: Path,
) -> None:
    first = tmp_path / "A"
    second = tmp_path / "B"
    _write_marker(first, "1:1")
    _write_marker(second, "1:1")
    before = {
        path: path.read_bytes()
        for path in (_marker(first), _marker(second))
    }

    with pytest.raises(ProductFolderError) as caught:
        ensure_product_folder(tmp_path, "Product", "1", "1")

    assert caught.value.error.error_code == "MULTIPLE_PRODUCT_FOLDERS"
    assert caught.value.error.category == ErrorCategory.PERMANENT
    assert {
        _marker(first): _marker(first).read_bytes(),
        _marker(second): _marker(second).read_bytes(),
    } == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["A", "B"]


def test_marker_failure_removes_only_the_empty_new_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_marker(_folder: Path, _product_key: str) -> None:
        raise PermissionError("marker denied")

    monkeypatch.setattr(
        product_folder_module,
        "_write_identity_marker_atomic",
        fail_marker,
    )

    with pytest.raises(ProductFolderError) as caught:
        ensure_product_folder(tmp_path, "Product", "1", "1")

    assert caught.value.error.error_code == "PERMISSION_DENIED"
    assert not (tmp_path / "Product").exists()


def test_same_batch_different_urls_skip_only_after_success(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    download_calls: list[str] = []

    def complete(_row: int, product: BridgeProductData) -> None:
        download_calls.append(product.request_id or "")
        folder = ensure_product_folder(
            tmp_path,
            product.product_name,
            product.shop_id,
            product.item_id,
        )
        enriched = replace(product, product_folder=folder)
        manager.handle_product_folder_ready(enriched)
        manager.handle_download_result(_successful_download(enriched))

    manager.item_download_requested.connect(complete)
    manager.start_batch(
        [
            (0, "https://shopee.vn/normal-product"),
            (1, "https://s.shopee.vn/alternative-product"),
        ]
    )
    first_request = manager.current_item.request_id
    manager.handle_product_result(_product(first_request, image_count=9))
    second_request = manager.current_item.request_id
    manager.handle_product_result(
        _product(second_request, name="Same Product New URL", image_count=9)
    )

    first, second = manager.items
    assert [first.state, second.state] == [
        ItemState.SUCCESS,
        ItemState.SKIPPED_DUPLICATE,
    ]
    assert len(download_calls) == 1
    assert manager.get_finished_count() == 2
    assert manager.get_success_count() == 1
    assert manager.get_duplicate_count() == 1
    assert second.product_data is not None
    assert first.product_data is not None
    assert second.product_data.product_folder == first.product_data.product_folder
    assert second.product_data.download_result is first.product_data.download_result
    assert len(first.product_data.images) == len(second.product_data.images) == 9
    assert len([path for path in tmp_path.iterdir() if path.is_dir()]) == 1


def test_failed_first_product_does_not_make_later_item_a_duplicate(
    tmp_path: Path,
) -> None:
    manager = BatchQueueManager(item_timeout_ms=0)
    pipeline_calls = 0

    def process(_row: int, product: BridgeProductData) -> None:
        nonlocal pipeline_calls
        pipeline_calls += 1
        if pipeline_calls == 1:
            manager.handle_pipeline_failure(
                product,
                "PRODUCT_FOLDER_ERROR",
                "first failed",
            )
            return
        folder = ensure_product_folder(
            tmp_path,
            product.product_name,
            product.shop_id,
            product.item_id,
        )
        enriched = replace(product, product_folder=folder)
        manager.handle_product_folder_ready(enriched)
        manager.handle_download_result(_successful_download(enriched))

    manager.item_download_requested.connect(process)
    manager.start_batch([(0, "https://shopee.vn/a"), (1, "https://shopee.vn/b")])
    manager.handle_product_result(_product(manager.current_item.request_id))
    manager.handle_product_result(_product(manager.current_item.request_id))

    assert [item.state for item in manager.items] == [
        ItemState.FAILED,
        ItemState.SUCCESS,
    ]
    assert pipeline_calls == 2
    assert manager.get_duplicate_count() == 0


def test_retry_transport_generation_is_not_a_duplicate(tmp_path: Path) -> None:
    manager = BatchQueueManager(
        item_timeout_ms=0,
        retry_policy=RetryPolicy(max_attempts=2, initial_delay_seconds=60),
    )
    download_calls: list[str] = []

    def complete(_row: int, product: BridgeProductData) -> None:
        download_calls.append(product.request_id or "")
        folder = ensure_product_folder(tmp_path, "Product", "1", "1")
        enriched = replace(product, product_folder=folder)
        manager.handle_product_folder_ready(enriched)
        manager.handle_download_result(_successful_download(enriched))

    manager.item_download_requested.connect(complete)
    manager.start_batch([(0, "https://shopee.vn/product")])
    first_request = manager.current_item.request_id
    manager.handle_process_error(
        first_request,
        "https://shopee.vn/product",
        "PRODUCT_TIMEOUT",
        "temporary",
    )
    manager._retry_timer.stop()
    manager._on_retry_timeout()
    second_request = manager.current_item.request_id
    manager.handle_product_result(_product(second_request))

    assert first_request != second_request
    assert manager.items[0].attempt == 2
    assert manager.items[0].state == ItemState.SUCCESS
    assert manager.get_duplicate_count() == 0
    assert download_calls == [second_request]


class _Response:
    def __init__(self, body: bytes, content_type: str = "image/jpeg") -> None:
        self.status = 200
        self.headers = {"Content-Type": content_type}
        self._body = body
        self._offset = 0

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._body):
            return b""
        end = len(self._body) if size < 0 else self._offset + size
        chunk = self._body[self._offset:end]
        self._offset += len(chunk)
        return chunk


class _Opener:
    def __init__(self, bodies: list[bytes]) -> None:
        self._bodies = list(bodies)
        self.calls = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> _Response:
        body = self._bodies[self.calls]
        self.calls += 1
        return _Response(body)


class _UrlMappedOpener:
    """Return deterministic bodies by request URL under concurrent scheduling."""

    def __init__(self, bodies: dict[str, bytes]) -> None:
        self._bodies = dict(bodies)
        self._lock = threading.Lock()
        self.calls = 0

    def __call__(self, request: Any, **_kwargs: Any) -> _Response:
        with self._lock:
            self.calls += 1
        return _Response(self._bodies[request.full_url])


def _downloader(opener: Any) -> ImageDownloader:
    return ImageDownloader(
        DownloadConfig(
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
            overall_timeout_seconds=2,
            max_attempts=1,
            retry_backoff_seconds=0,
        ),
        open_url=opener,
        sleeper=lambda _seconds: None,
    )


def test_cross_run_partial_download_reuses_folder_and_completes_missing(
    tmp_path: Path,
) -> None:
    original_folder = ensure_product_folder(tmp_path, "Old Title", "1", "1")
    existing = original_folder / "01.jpg"
    existing.write_bytes(b"existing-one")
    reused = ensure_product_folder(tmp_path, "Changed Title", "1", "1")
    images = ["https://images.example/1.jpg", "https://images.example/2.jpg"]
    opener = _UrlMappedOpener(
        {
            "https://images.example/1.jpg": b"new-one",
            "https://images.example/2.jpg": b"new-two",
        }
    )

    result = _downloader(opener).download_product_images(images, reused)

    assert reused == original_folder
    assert existing.read_bytes() == b"existing-one"
    assert (reused / "02.jpg").read_bytes() == b"new-two"
    assert result.skipped == 1
    assert result.successful == 1
    assert opener.calls == 2
    assert images == ["https://images.example/1.jpg", "https://images.example/2.jpg"]


def test_cross_run_complete_download_preserves_all_existing_bytes(
    tmp_path: Path,
) -> None:
    folder = ensure_product_folder(tmp_path, "Product", "1", "1")
    first = folder / "01.jpg"
    second = folder / "02.jpg"
    first.write_bytes(b"existing-one")
    second.write_bytes(b"existing-two")
    opener = _Opener([b"replacement-one", b"replacement-two"])

    result = _downloader(opener).download_product_images(
        ["https://images.example/1.jpg", "https://images.example/2.jpg"],
        ensure_product_folder(tmp_path, "New Title", "1", "1"),
    )

    assert first.read_bytes() == b"existing-one"
    assert second.read_bytes() == b"existing-two"
    assert result.skipped == 2
    assert result.successful == 0
    assert len([path for path in tmp_path.iterdir() if path.is_dir()]) == 1


def test_zero_byte_existing_file_is_replaced_not_skipped(tmp_path: Path) -> None:
    folder = ensure_product_folder(tmp_path, "Product", "1", "1")
    target = folder / "01.jpg"
    target.write_bytes(b"")

    result = _downloader(_Opener([b"valid-image"])).download_product_images(
        ["https://images.example/1.jpg"],
        folder,
    )

    assert target.read_bytes() == b"valid-image"
    assert result.items[0].status == ImageDownloadStatus.SUCCESS
    assert not list(folder.glob("*.part"))
