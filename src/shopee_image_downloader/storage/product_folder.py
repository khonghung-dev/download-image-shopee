"""Marker-owned product folder resolution below one selected output root."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import uuid

from shopee_image_downloader.core.error_policy import (
    AppError,
    AppErrorException,
    ErrorStage,
    classify_error_code,
    error_from_exception,
)
from shopee_image_downloader.core.product_identity import (
    canonical_product_key,
    is_canonical_product_key,
)

logger = logging.getLogger(__name__)

MAX_PRODUCT_FOLDER_NAME_LENGTH: int = 120
PRODUCT_ID_MARKER_FILENAME: str = ".shopee-product-id"
_MAX_MARKER_BYTES: int = 128
_WINDOWS_REPARSE_POINT_ATTRIBUTE: int = 0x400

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
    """Build the identity-suffixed collision component."""
    identity = f"{_safe_identity_part(shop_id)}-{_safe_identity_part(item_id)}"
    max_identity_length = MAX_PRODUCT_FOLDER_NAME_LENGTH - len("product []")
    identity = identity[:max_identity_length].rstrip(" .") or "unknown"
    suffix = f" [{identity}]"
    available = MAX_PRODUCT_FOLDER_NAME_LENGTH - len(suffix)
    prefix = base_name[:available].rstrip(" .") or "product"
    return f"{prefix}{suffix}"[:MAX_PRODUCT_FOLDER_NAME_LENGTH].rstrip(" .")


def _numbered_collision_name(base_name: str, number: int) -> str:
    """Return a stable fallback when even the identity suffix is occupied."""
    suffix = f" ({number})"
    available = MAX_PRODUCT_FOLDER_NAME_LENGTH - len(suffix)
    prefix = base_name[:available].rstrip(" .") or "product"
    return f"{prefix}{suffix}"


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


def _entry_exists(path: Path) -> bool:
    """Check lexical existence without treating a broken link as available."""
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ProductFolderError(
            error_from_exception(
                exc,
                stage=ErrorStage.FOLDER,
                default_code="PRODUCT_FOLDER_ERROR",
            )
        ) from exc
    return True


def _is_reparse_point(path: Path) -> bool:
    """Conservatively recognize symlinks and Windows reparse points."""
    try:
        stat_result = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        getattr(stat_result, "st_file_attributes", 0)
        & _WINDOWS_REPARSE_POINT_ATTRIBUTE
    )


def _read_product_marker(root: Path, child: Path) -> str | None:
    """Read one fixed-name marker only when containment is provable."""
    marker = child / PRODUCT_ID_MARKER_FILENAME
    try:
        marker.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Không thể kiểm tra marker sản phẩm %s: %s", marker, exc)
        return None
    if _is_reparse_point(marker):
        logger.warning("Bỏ qua marker reparse/symlink không an toàn: %s", marker)
        return None

    try:
        resolved_marker = marker.resolve(strict=True)
        marker_stat = resolved_marker.stat()
        if resolved_marker.parent != child or child.parent != root:
            logger.warning("Bỏ qua marker ngoài biên thư mục đầu ra: %s", marker)
            return None
        if not resolved_marker.is_file() or marker_stat.st_size > _MAX_MARKER_BYTES:
            logger.warning("Marker sản phẩm không hợp lệ: %s", marker)
            return None
        marker_text = resolved_marker.read_text(encoding="utf-8")
        marker_value = (
            marker_text[:-1] if marker_text.endswith("\n") else marker_text
        )
    except (OSError, RuntimeError, UnicodeError) as exc:
        logger.warning("Không thể đọc marker sản phẩm %s: %s", marker, exc)
        return None

    if not is_canonical_product_key(marker_value):
        logger.warning(
            "Marker sản phẩm rỗng hoặc sai định dạng tại %s: %r",
            marker,
            marker_value,
        )
        return None
    return marker_value


def _discover_owned_folder(root: Path, product_key: str) -> Path | None:
    """Find a unique immediate child whose marker claims ``product_key``."""
    matches: list[Path] = []
    try:
        children = sorted(root.iterdir(), key=lambda path: path.name.casefold())
    except OSError as exc:
        raise ProductFolderError(
            error_from_exception(
                exc,
                stage=ErrorStage.FOLDER,
                default_code="PRODUCT_FOLDER_ERROR",
            )
        ) from exc

    for child in children:
        if _is_reparse_point(child):
            logger.warning("Bỏ qua thư mục reparse/symlink: %s", child)
            continue
        try:
            resolved_child = child.resolve(strict=True)
            if resolved_child.parent != root or not resolved_child.is_dir():
                continue
        except (OSError, RuntimeError):
            logger.warning("Không thể xác minh thư mục con: %s", child)
            continue
        if _read_product_marker(root, resolved_child) == product_key:
            matches.append(resolved_child)

    if len(matches) > 1:
        joined = ", ".join(path.name for path in matches)
        raise ProductFolderError(
            (
                "Phát hiện nhiều thư mục cho cùng một sản phẩm. "
                f"product_key={product_key}; folders={joined}"
            ),
            error_code="MULTIPLE_PRODUCT_FOLDERS",
        )
    return matches[0] if matches else None


def _choose_available_target(
    root: Path,
    folder_name: str,
    shop_id: object,
    item_id: object,
) -> Path:
    """Choose a direct child without adopting any unmarked existing entry."""
    primary = _validated_child(root, folder_name)
    if not _entry_exists(primary):
        return primary

    collision_component = _collision_name(folder_name, shop_id, item_id)
    collision = _validated_child(root, collision_component)
    if not _entry_exists(collision):
        return collision

    number = 2
    while number <= 10_000:
        candidate = _validated_child(
            root,
            _numbered_collision_name(collision_component, number),
        )
        if not _entry_exists(candidate):
            return candidate
        number += 1
    raise ProductFolderError(
        "Không thể chọn tên thư mục sản phẩm an toàn.",
        error_code="PRODUCT_FOLDER_ERROR",
    )


def _write_identity_marker_atomic(folder: Path, product_key: str) -> None:
    """Atomically create the fixed internal identity marker."""
    marker = folder / PRODUCT_ID_MARKER_FILENAME
    temporary = folder / (
        f"{PRODUCT_ID_MARKER_FILENAME}.{uuid.uuid4().hex}.tmp"
    )
    resolved_folder = folder.resolve(strict=True)
    if marker.resolve(strict=False).parent != resolved_folder:
        raise ProductFolderError(
            "Đường dẫn marker không nằm trong thư mục sản phẩm.",
            error_code="PATH_CONTAINMENT_VIOLATION",
        )

    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as marker_file:
            marker_file.write(f"{product_key}\n")
            marker_file.flush()
            os.fsync(marker_file.fileno())
        os.replace(temporary, marker)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            logger.warning("Không thể xóa marker tạm: %s", temporary)


def ensure_product_folder(
    output_root: str | Path | None,
    product_name: object | None,
    shop_id: object | None = None,
    item_id: object | None = None,
) -> Path:
    """Resolve or create the unique marker-owned folder for one product."""
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

    try:
        product_key = canonical_product_key(shop_id, item_id)
    except ValueError as exc:
        raise ProductFolderError(
            f"Định danh sản phẩm không hợp lệ: {exc}",
            error_code="INVALID_PRODUCT_ID",
        ) from exc

    existing_owned = _discover_owned_folder(root, product_key)
    if existing_owned is not None:
        logger.info(
            "Tái sử dụng thư mục sản phẩm: product_key=%s folder=%s",
            product_key,
            existing_owned,
        )
        return existing_owned

    folder_name = sanitize_product_folder_name(product_name, shop_id, item_id)
    target = _choose_available_target(root, folder_name, shop_id, item_id)

    try:
        target.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise ProductFolderError(
            f"Tên thư mục vừa bị chiếm dụng: {target}",
            error_code="PRODUCT_FOLDER_ERROR",
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

    try:
        _write_identity_marker_atomic(target, product_key)
    except ProductFolderError:
        try:
            target.rmdir()
        except OSError:
            logger.warning(
                "Không thể dọn thư mục mới sau lỗi marker: %s", target
            )
        raise
    except OSError as exc:
        try:
            target.rmdir()
        except OSError:
            logger.warning(
                "Không thể dọn thư mục mới sau lỗi marker: %s", target
            )
        raise ProductFolderError(
            error_from_exception(
                exc,
                stage=ErrorStage.FOLDER,
                default_code="PRODUCT_FOLDER_ERROR",
            )
        ) from exc

    logger.info(
        "Đã tạo thư mục sản phẩm: product_key=%s folder=%s",
        product_key,
        target,
    )
    return target
