"""Windows-safe product folder creation within a selected output root."""

from __future__ import annotations

import logging
from pathlib import Path
import re

from shopee_image_downloader.core.error_policy import (
    AppError,
    AppErrorException,
    ErrorStage,
    classify_error_code,
    error_from_exception,
)

logger = logging.getLogger(__name__)

MAX_PRODUCT_FOLDER_NAME_LENGTH: int = 120

_INVALID_WINDOWS_RUN = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE_RUN = re.compile(r"\s+")
_RESERVED_DEVICE_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$",
    re.IGNORECASE,
)


class ProductFolderError(AppErrorException):
    """Controlled failure while validating or creating a product folder."""

    def __init__(
        self,
        error: AppError | str,
        *,
        error_code: str = "PRODUCT_FOLDER_ERROR",
    ) -> None:
        if isinstance(error, AppError):
            app_error = error
        else:
            app_error = classify_error_code(
                error_code,
                stage=ErrorStage.FOLDER,
                technical_message=error,
            )
        super().__init__(app_error)


def _safe_identity_part(value: object | None) -> str:
    """Return a deterministic filename-safe identity token."""
    text = "" if value is None else str(value)
    text = _INVALID_WINDOWS_RUN.sub("_", text)
    text = _WHITESPACE_RUN.sub("_", text.strip())
    text = text.strip(" ._")
    return text or "unknown"


def _fallback_name(shop_id: object | None, item_id: object | None) -> str:
    """Build the stable fallback used when a title is unusable."""
    return (
        f"product_{_safe_identity_part(shop_id)}_"
        f"{_safe_identity_part(item_id)}"
    )[:MAX_PRODUCT_FOLDER_NAME_LENGTH].rstrip(" .")


def sanitize_product_folder_name(
    product_name: object | None,
    shop_id: object | None = None,
    item_id: object | None = None,
) -> str:
    """Return a deterministic Windows-safe single path component.

    Vietnamese and other Unicode text is preserved. Invalid Windows filename
    runs and ASCII control-character runs are replaced with ``_``.
    """
    raw_name = "" if product_name is None else str(product_name)
    sanitized = _INVALID_WINDOWS_RUN.sub("_", raw_name)
    sanitized = _WHITESPACE_RUN.sub(" ", sanitized).strip()
    sanitized = sanitized.rstrip(" .")

    if not sanitized or not sanitized.strip("_") or sanitized in {".", ".."}:
        return _fallback_name(shop_id, item_id)

    basename = sanitized.split(".", 1)[0]
    if _RESERVED_DEVICE_NAME.fullmatch(basename):
        sanitized = f"_{sanitized}"

    sanitized = sanitized[:MAX_PRODUCT_FOLDER_NAME_LENGTH].rstrip(" .")
    if not sanitized or not sanitized.strip("_") or sanitized in {".", ".."}:
        return _fallback_name(shop_id, item_id)
    return sanitized


def _collision_name(base_name: str, shop_id: object | None, item_id: object | None) -> str:
    """Build the provisional identity-suffixed collision component."""
    identity = f"{_safe_identity_part(shop_id)}-{_safe_identity_part(item_id)}"
    max_identity_length = MAX_PRODUCT_FOLDER_NAME_LENGTH - len("product []")
    identity = identity[:max_identity_length].rstrip(" .") or "unknown"
    suffix = f" [{identity}]"
    available = MAX_PRODUCT_FOLDER_NAME_LENGTH - len(suffix)
    prefix = base_name[:available].rstrip(" .") or "product"
    return f"{prefix}{suffix}"[:MAX_PRODUCT_FOLDER_NAME_LENGTH].rstrip(" .")


def _validated_child(root: Path, component: str) -> Path:
    """Return the target only when it resolves to a direct child of root."""
    target = root / component
    try:
        resolved_target = target.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ProductFolderError(
            error_from_exception(
                exc,
                stage=ErrorStage.FOLDER,
                default_code="PRODUCT_FOLDER_ERROR",
            )
        ) from exc

    if resolved_target.parent != root:
        raise ProductFolderError(
            "Đường dẫn thư mục sản phẩm không nằm trong thư mục đầu ra.",
            error_code="PATH_CONTAINMENT_VIOLATION",
        )
    return target


def ensure_product_folder(
    output_root: str | Path | None,
    product_name: object | None,
    shop_id: object | None = None,
    item_id: object | None = None,
) -> Path:
    """Create and return one safe product directory below an existing root.

    Existing primary names use the provisional ``[shop_id-item_id]`` suffix.
    If that identity-specific directory already exists, it is reused.
    """
    if output_root is None or not str(output_root).strip():
        raise ProductFolderError(
            "Chưa chọn thư mục đầu ra.",
            error_code="INVALID_OUTPUT_PATH",
        )

    raw_root = Path(output_root)
    try:
        root = raw_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProductFolderError(
            f"Thư mục đầu ra không tồn tại hoặc không khả dụng: {raw_root}",
            error_code="INVALID_OUTPUT_PATH",
        ) from exc

    try:
        root_is_directory = root.is_dir()
    except OSError as exc:
        raise ProductFolderError(
            error_from_exception(
                exc,
                stage=ErrorStage.FOLDER,
                default_code="INVALID_OUTPUT_PATH",
            )
        ) from exc
    if not root_is_directory:
        raise ProductFolderError(
            f"Đường dẫn đầu ra không phải thư mục: {root}",
            error_code="INVALID_OUTPUT_PATH",
        )

    folder_name = sanitize_product_folder_name(product_name, shop_id, item_id)
    fallback_name = _fallback_name(shop_id, item_id)
    primary = _validated_child(root, folder_name)

    if primary.exists():
        if not primary.is_dir():
            raise ProductFolderError(
                f"Tên thư mục sản phẩm đang bị một tệp chiếm dụng: {primary.name}",
                error_code="INVALID_OUTPUT_PATH",
            )
        if folder_name == fallback_name:
            return primary
        target = _validated_child(
            root,
            _collision_name(folder_name, shop_id, item_id),
        )
    else:
        target = primary

    try:
        target.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        if target.is_dir():
            return target
        raise ProductFolderError(
            f"Không thể tạo thư mục vì đường dẫn đã tồn tại: {target}",
            error_code="INVALID_OUTPUT_PATH",
        ) from exc
    except PermissionError as exc:
        raise ProductFolderError(
            error_from_exception(
                exc,
                stage=ErrorStage.FOLDER,
                default_code="PERMISSION_DENIED",
            )
        ) from exc
    except OSError as exc:
        raise ProductFolderError(
            error_from_exception(
                exc,
                stage=ErrorStage.FOLDER,
                default_code="PRODUCT_FOLDER_ERROR",
            )
        ) from exc

    logger.info("Đã tạo thư mục sản phẩm: %s", target)
    return target
