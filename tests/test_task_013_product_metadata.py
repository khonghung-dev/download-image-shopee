"""Task 013 portable per-product metadata regressions."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Sequence

import pytest

from shopee_image_downloader.core.batch_queue import (
    BatchQueueManager,
    ItemState,
    QueueState,
)
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.error_policy import ErrorStage
from shopee_image_downloader.core.image_downloader import (
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
)
from shopee_image_downloader.core.product_metadata import (
    PRODUCT_METADATA_FILENAME,
    PRODUCT_METADATA_SCHEMA_VERSION,
    PRODUCT_METADATA_TEMP_FILENAME,
    ProductMetadataError,
    build_product_metadata,
    write_product_metadata,
)
from shopee_image_downloader.storage.product_folder import (
    PRODUCT_ID_MARKER_FILENAME,
    ensure_product_folder,
)
from shopee_image_downloader.workers import image_download_worker as worker_module
from shopee_image_downloader.workers.image_download_worker import (
    ImageDownloadController,
)


def _product(
    folder: Path,
    *,
    name: str = "Túi đựng đồ du lịch",
    shop_id: str = "123",
    item_id: str = "456",
    image_count: int = 3,
    request_id: str | None = None,
    input_url: str = "https://shopee.vn/input-product-i.123.456",
) -> BridgeProductData:
    images = [
        f"https://images.example/{index}.jpg"
        for index in range(1, image_count + 1)
    ]
    return BridgeProductData(
        url=f"https://shopee.vn/final-product-i.{shop_id}.{item_id}",
        input_url=input_url,
        final_url=f"https://shopee.vn/final-product-i.{shop_id}.{item_id}",
        product_name=name,
        shop_id=shop_id,
        item_id=item_id,
        images=images,
        image_count=image_count,
        request_id=request_id,
        product_folder=folder,
    )


def _download_result(
    product: BridgeProductData,
    *,
    statuses: Sequence[ImageDownloadStatus] | None = None,
    filenames: Sequence[str] | None = None,
) -> ProductDownloadResult:
    chosen_statuses = list(
        statuses or [ImageDownloadStatus.SUCCESS] * len(product.images)
    )
    chosen_filenames = list(
        filenames or [f"{index:02d}.jpg" for index in range(1, len(product.images) + 1)]
    )
    items = [
        ImageDownloadResult(
            index=index,
            source_url=source_url,
            target_path=product.product_folder / chosen_filenames[index - 1],
            status=chosen_statuses[index - 1],
            attempts=1,
            error=(
                "HTTP 404"
                if chosen_statuses[index - 1] == ImageDownloadStatus.FAILED
                else None
            ),
        )
        for index, source_url in enumerate(product.images, start=1)
    ]
    return ProductDownloadResult.from_items(len(product.images), items)


def test_basic_metadata_uses_canonical_identity_and_authoritative_order(
    tmp_path: Path,
) -> None:
    product = _product(tmp_path)
    original_images = list(product.images)

    metadata = build_product_metadata(product, _download_result(product))

    assert metadata["schema_version"] == PRODUCT_METADATA_SCHEMA_VERSION == 1
    assert metadata["product_name"] == "Túi đựng đồ du lịch"
    assert metadata["shop_id"] == "123"
    assert metadata["item_id"] == "456"
    assert metadata["product_key"] == "123:456"
    assert metadata["source_url"] == product.input_url
    assert metadata["image_count"] == 3
    assert len(metadata["images"]) == 3
    assert [entry["index"] for entry in metadata["images"]] == [1, 2, 3]
    assert [entry["source_url"] for entry in metadata["images"]] == original_images
    assert metadata["download"] == {
        "total": 3,
        "successful": 3,
        "failed": 0,
        "skipped": 0,
    }
    assert metadata["status"] == "success"
    assert product.images == original_images


def test_vietnamese_is_written_as_readable_utf8(tmp_path: Path) -> None:
    product = _product(tmp_path, name="Áo khoác nữ chống nắng cao cấp")
    metadata = build_product_metadata(product, _download_result(product))

    path = write_product_metadata(tmp_path, metadata)
    raw = path.read_bytes()
    text = raw.decode("utf-8")

    assert "Áo khoác nữ chống nắng cao cấp" in text
    assert "\\u00c1" not in text
    assert json.loads(text)["product_name"] == product.product_name


def test_exact_local_filenames_partial_and_skipped_statuses(tmp_path: Path) -> None:
    product = _product(tmp_path)
    result = _download_result(
        product,
        statuses=[
            ImageDownloadStatus.SUCCESS,
            ImageDownloadStatus.SKIPPED_EXISTING,
            ImageDownloadStatus.FAILED,
        ],
        filenames=["01.jpg", "02.webp", "03.png"],
    )

    metadata = build_product_metadata(product, result)

    assert [entry["local_file"] for entry in metadata["images"]] == [
        "01.jpg",
        "02.webp",
        "03.png",
    ]
    assert all(
        not Path(entry["local_file"]).is_absolute()
        for entry in metadata["images"]
    )
    assert [entry["status"] for entry in metadata["images"]] == [
        "success",
        "skipped_existing",
        "failed",
    ]
    assert metadata["images"][2]["source_url"] == product.images[2]
    assert metadata["download"] == {
        "total": 3,
        "successful": 1,
        "failed": 1,
        "skipped": 1,
    }
    assert metadata["status"] == "partial"


def test_source_url_is_null_when_input_url_is_unavailable(tmp_path: Path) -> None:
    product = _product(tmp_path, input_url="")

    metadata = build_product_metadata(product, _download_result(product))

    assert metadata["source_url"] is None


def test_atomic_replace_updates_one_canonical_file(tmp_path: Path) -> None:
    target = tmp_path / PRODUCT_METADATA_FILENAME
    target.write_text('{"product_name":"Old Name"}', encoding="utf-8")
    product = _product(tmp_path, name="New Name")

    written = write_product_metadata(
        tmp_path,
        build_product_metadata(product, _download_result(product)),
    )

    assert written == target
    assert json.loads(target.read_text(encoding="utf-8"))["product_name"] == "New Name"
    assert not (tmp_path / PRODUCT_METADATA_TEMP_FILENAME).exists()
    assert not list(tmp_path.glob("product (*).json"))


def test_write_failure_preserves_images_and_existing_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = tmp_path / "01.jpg"
    image.write_bytes(b"completed-image")
    target = tmp_path / PRODUCT_METADATA_FILENAME
    target.write_text('{"product_name":"Old Name"}\n', encoding="utf-8")
    old_bytes = target.read_bytes()
    product = _product(tmp_path, image_count=1)
    metadata = build_product_metadata(product, _download_result(product))

    def deny_replace(_source: Path, _target: Path) -> None:
        raise PermissionError("metadata denied")

    monkeypatch.setattr(
        "shopee_image_downloader.core.product_metadata.os.replace",
        deny_replace,
    )

    with pytest.raises(ProductMetadataError) as caught:
        write_product_metadata(tmp_path, metadata)

    assert caught.value.error.error_code == "METADATA_WRITE_ERROR"
    assert caught.value.error.stage == ErrorStage.METADATA
    assert caught.value.error.user_message == "Không thể ghi thông tin sản phẩm."
    assert image.read_bytes() == b"completed-image"
    assert target.read_bytes() == old_bytes
    assert not (tmp_path / PRODUCT_METADATA_TEMP_FILENAME).exists()


def test_cross_run_title_change_updates_metadata_without_renaming_folder(
    tmp_path: Path,
) -> None:
    folder = ensure_product_folder(tmp_path, "Old Name", "123", "456")
    old_product = _product(folder, name="Old Name")
    write_product_metadata(
        folder,
        build_product_metadata(old_product, _download_result(old_product)),
    )
    marker = folder / PRODUCT_ID_MARKER_FILENAME
    marker_bytes = marker.read_bytes()

    reused = ensure_product_folder(tmp_path, "New Name", "123", "456")
    new_product = _product(reused, name="New Name", image_count=2)
    write_product_metadata(
        reused,
        build_product_metadata(new_product, _download_result(new_product)),
    )

    assert reused == folder
    assert folder.name == "Old Name"
    assert marker.read_bytes() == marker_bytes
    current_metadata = json.loads(
        (folder / PRODUCT_METADATA_FILENAME).read_text(encoding="utf-8")
    )
    assert current_metadata["product_name"] == "New Name"
    assert current_metadata["image_count"] == 2
    assert len(current_metadata["images"]) == 2


def test_marker_identity_is_independent_from_product_json(tmp_path: Path) -> None:
    owned = ensure_product_folder(tmp_path, "Owned", "123", "456")
    assert not (owned / PRODUCT_METADATA_FILENAME).exists()
    assert ensure_product_folder(tmp_path, "Renamed", "123", "456") == owned

    unmarked = tmp_path / "Unmarked"
    unmarked.mkdir()
    (unmarked / PRODUCT_METADATA_FILENAME).write_text(
        '{"product_key":"789:999"}',
        encoding="utf-8",
    )
    resolved = ensure_product_folder(tmp_path, "Unmarked", "789", "999")

    assert resolved != unmarked
    assert not (unmarked / PRODUCT_ID_MARKER_FILENAME).exists()
    assert (
        resolved / PRODUCT_ID_MARKER_FILENAME
    ).read_text(encoding="utf-8").strip() == "789:999"


class _SuccessfulDownloader:
    """Write deterministic files while the real worker owns metadata."""

    def download_product_images(
        self,
        images: Sequence[str],
        product_folder: str | Path,
        *,
        progress_callback: Any = None,
        cancel_check: Any = None,
    ) -> ProductDownloadResult:
        folder = Path(product_folder)
        items: list[ImageDownloadResult] = []
        for index, source_url in enumerate(images, start=1):
            target = folder / f"{index:02d}.jpg"
            target.write_bytes(f"image-{index}".encode())
            items.append(
                ImageDownloadResult(
                    index=index,
                    source_url=source_url,
                    target_path=target,
                    status=ImageDownloadStatus.SUCCESS,
                    attempts=1,
                )
            )
            if progress_callback is not None:
                progress_callback(index, len(images))
        return ProductDownloadResult.from_items(len(images), items)


def test_manual_worker_lifecycle_writes_metadata(tmp_path: Path, qtbot) -> None:
    controller = ImageDownloadController(downloader=_SuccessfulDownloader())
    product = _product(tmp_path, name="Manual Product", image_count=3, request_id=None)
    completed: list[tuple[BridgeProductData, ProductDownloadResult]] = []
    controller.finished.connect(
        lambda current, result: completed.append((current, result))
    )

    assert controller.start(product, str(tmp_path))
    qtbot.waitUntil(lambda: bool(completed), timeout=3000)
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=3000)

    completed_product, _result = completed[0]
    metadata_path = completed_product.product_folder / PRODUCT_METADATA_FILENAME
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["product_name"] == "Manual Product"
    assert metadata["image_count"] == 3
    assert metadata["source_url"] == product.input_url


def test_automatic_metadata_failure_is_controlled_and_keeps_images(
    tmp_path: Path,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = ImageDownloadController(downloader=_SuccessfulDownloader())
    manager = BatchQueueManager(item_timeout_ms=0)
    manager.item_download_requested.connect(
        lambda _row, product: controller.start(product, str(tmp_path))
    )
    controller.folder_ready.connect(manager.handle_product_folder_ready)
    controller.finished.connect(
        lambda product, result: manager.handle_download_result(
            replace(product, download_result=result)
        )
    )
    controller.failed.connect(manager.handle_pipeline_failure)

    def deny_metadata(_folder: Path, _metadata: dict[str, Any]) -> Path:
        raise ProductMetadataError("simulated metadata write failure")

    monkeypatch.setattr(worker_module, "write_product_metadata", deny_metadata)

    manager.start_batch([(0, "https://shopee.vn/original-input")])
    request_id = manager.current_item.request_id
    manager.handle_product_result(
        _product(
            tmp_path,
            request_id=request_id,
            image_count=3,
            input_url="extension-value",
        )
    )
    qtbot.waitUntil(lambda: manager.state == QueueState.IDLE, timeout=3000)

    item = manager.items[0]
    assert item.state == ItemState.FAILED
    assert item.error_code == "METADATA_WRITE_ERROR"
    assert item.error_stage == ErrorStage.METADATA
    assert item.product_data is not None
    assert item.product_data.product_folder is not None
    assert len(list(item.product_data.product_folder.glob("*.jpg"))) == 3
    assert not (item.product_data.product_folder / PRODUCT_METADATA_FILENAME).exists()


def test_same_batch_duplicate_does_not_rewrite_metadata_and_preserves_nine_images(
    tmp_path: Path,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = ImageDownloadController(downloader=_SuccessfulDownloader())
    manager = BatchQueueManager(item_timeout_ms=0)
    metadata_writes: list[Path] = []
    real_writer = worker_module.write_product_metadata

    def record_write(folder: Path, metadata: dict[str, Any]) -> Path:
        metadata_writes.append(Path(folder))
        return real_writer(folder, metadata)

    monkeypatch.setattr(worker_module, "write_product_metadata", record_write)
    manager.item_download_requested.connect(
        lambda _row, product: controller.start(product, str(tmp_path))
    )
    controller.folder_ready.connect(manager.handle_product_folder_ready)
    controller.finished.connect(
        lambda product, result: manager.handle_download_result(
            replace(product, download_result=result)
        )
    )
    controller.failed.connect(manager.handle_pipeline_failure)

    first_url = "https://shopee.vn/original-queue-input"
    manager.start_batch([(0, first_url), (1, "https://s.shopee.vn/duplicate")])
    first_request = manager.current_item.request_id
    first_product = _product(
        tmp_path,
        request_id=first_request,
        image_count=9,
        input_url="extension-provided-value",
    )
    original_images = list(first_product.images)
    manager.handle_product_result(first_product)
    qtbot.waitUntil(
        lambda: manager.current_item is not None
        and manager.current_item.row_idx == 1,
        timeout=3000,
    )
    second_request = manager.current_item.request_id
    manager.handle_product_result(
        _product(
            tmp_path,
            request_id=second_request,
            name="Changed Duplicate Title",
            image_count=9,
        )
    )
    qtbot.waitUntil(lambda: manager.state == QueueState.IDLE, timeout=3000)

    first, second = manager.items
    assert [first.state, second.state] == [
        ItemState.SUCCESS,
        ItemState.SKIPPED_DUPLICATE,
    ]
    assert len(metadata_writes) == 1
    assert first.product_data is not None
    assert first.product_data.images == original_images
    metadata_path = first.product_data.product_folder / PRODUCT_METADATA_FILENAME
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_url"] == first_url
    assert metadata["image_count"] == 9
    assert len(metadata["images"]) == 9
    assert len(list(tmp_path.glob("*/product.json"))) == 1
