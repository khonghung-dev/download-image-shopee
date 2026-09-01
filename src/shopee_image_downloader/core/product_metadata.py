"""Build and atomically persist portable per-product metadata."""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging
import os
from pathlib import Path
from typing import Any

from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.core.error_policy import (
    AppError,
    AppErrorException,
    ErrorStage,
    classify_error_code,
)
from shopee_image_downloader.core.image_downloader import (
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
)

logger = logging.getLogger(__name__)

PRODUCT_METADATA_FILENAME: str = "product.json"
PRODUCT_METADATA_TEMP_FILENAME: str = "product.json.tmp"
PRODUCT_METADATA_SCHEMA_VERSION: int = 1

_STATUS_NAMES: dict[ImageDownloadStatus, str] = {
    ImageDownloadStatus.SUCCESS: "success",
    ImageDownloadStatus.FAILED: "failed",
    ImageDownloadStatus.SKIPPED_EXISTING: "skipped_existing",
}


class ProductMetadataError(AppErrorException):
    """Controlled failure while building or writing ``product.json``."""

    def __init__(self, error: AppError | str) -> None:
        if isinstance(error, AppError):
            app_error = error
        else:
            app_error = classify_error_code(
                "METADATA_WRITE_ERROR",
                stage=ErrorStage.METADATA,
                technical_message=error,
            )
        super().__init__(app_error)


def build_product_metadata(
    product: BridgeProductData,
    download_result: ProductDownloadResult,
) -> dict[str, Any]:
    """Return schema-versioned metadata from authoritative in-memory results.

    This function does not discover files, perform network requests, or mutate
    the product/image models. The authoritative image order is validated
    against the downloader's ordered per-image result.
    """
    _validate_download_result(product, download_result)
    product_folder = _require_product_folder(product)

    image_entries = [
        _build_image_entry(product_folder, image_result)
        for image_result in download_result.items
    ]
    source_url = product.input_url.strip() or None

    return {
        "schema_version": PRODUCT_METADATA_SCHEMA_VERSION,
        "product_name": product.product_name,
        "shop_id": str(product.shop_id),
        "item_id": str(product.item_id),
        "product_key": product.product_key,
        "source_url": source_url,
        "image_count": len(product.images),
        "images": image_entries,
        "download": {
            "total": download_result.total,
            "successful": download_result.successful,
            "failed": download_result.failed,
            "skipped": download_result.skipped,
        },
        "status": "partial" if download_result.failed else "success",
    }


def write_product_metadata(
    product_folder: str | Path,
    metadata: Mapping[str, Any],
) -> Path:
    """Atomically replace the canonical ``product.json`` in one folder."""
    folder = _validated_product_folder(product_folder)
    target = folder / PRODUCT_METADATA_FILENAME
    temporary = folder / PRODUCT_METADATA_TEMP_FILENAME

    try:
        resolved_target = target.resolve(strict=False)
        resolved_temporary = temporary.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise _metadata_error(exc) from exc
    if resolved_target.parent != folder or resolved_temporary.parent != folder:
        raise ProductMetadataError(
            "Metadata path escapes the validated product folder"
        )

    try:
        temporary.unlink(missing_ok=True)
        with temporary.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(
                metadata,
                output,
                ensure_ascii=False,
                indent=2,
            )
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    except (OSError, TypeError, ValueError) as exc:
        raise _metadata_error(exc) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            logger.warning("Không thể xóa metadata tạm: %s", temporary)

    return target


def _validate_download_result(
    product: BridgeProductData,
    result: ProductDownloadResult,
) -> None:
    total = len(product.images)
    counters_total = result.successful + result.failed + result.skipped
    if (
        result.total != total
        or len(result.items) != total
        or counters_total != result.total
    ):
        raise ProductMetadataError(
            "Download result does not match the authoritative image count"
        )
    for index, image_result in enumerate(result.items, start=1):
        if (
            image_result.index != index
            or image_result.source_url != product.images[index - 1]
        ):
            raise ProductMetadataError(
                "Download result order does not match authoritative images"
            )
        if image_result.status not in _STATUS_NAMES:
            raise ProductMetadataError(
                f"Unsupported image download status: {image_result.status!r}"
            )


def _require_product_folder(product: BridgeProductData) -> Path:
    if product.product_folder is None:
        raise ProductMetadataError("Product folder is unavailable")
    try:
        return Path(product.product_folder).resolve(strict=False)
    except (OSError, RuntimeError, TypeError) as exc:
        raise _metadata_error(exc) from exc


def _build_image_entry(
    product_folder: Path,
    result: ImageDownloadResult,
) -> dict[str, Any]:
    try:
        target = Path(result.target_path).resolve(strict=False)
        relative = target.relative_to(product_folder)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ProductMetadataError(
            "Image target is outside the validated product folder"
        ) from exc
    if relative == Path(".") or any(part in {"", ".", ".."} for part in relative.parts):
        raise ProductMetadataError("Image target is not a safe relative path")

    return {
        "index": result.index,
        "source_url": result.source_url,
        "local_file": relative.as_posix(),
        "status": _STATUS_NAMES[result.status],
    }


def _validated_product_folder(product_folder: str | Path) -> Path:
    try:
        folder = Path(product_folder).resolve(strict=True)
        is_directory = folder.is_dir()
    except (OSError, RuntimeError, TypeError) as exc:
        raise _metadata_error(exc) from exc
    if not is_directory:
        raise ProductMetadataError(
            f"Product metadata parent is not a directory: {folder}"
        )
    return folder


def _metadata_error(exc: BaseException) -> ProductMetadataError:
    return ProductMetadataError(
        classify_error_code(
            "METADATA_WRITE_ERROR",
            stage=ErrorStage.METADATA,
            technical_message=f"{type(exc).__name__}: {exc}",
        )
    )
