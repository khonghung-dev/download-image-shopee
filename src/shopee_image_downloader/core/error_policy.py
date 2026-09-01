"""Canonical desktop error taxonomy and bounded retry policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
import errno
import math


DEFAULT_PRODUCT_MAX_ATTEMPTS: int = 3
DEFAULT_PRODUCT_ATTEMPT_TIMEOUT_MS: int = 9000
DEFAULT_PRODUCT_BACKOFF_SECONDS: float = 1.0
DEFAULT_PRODUCT_MAX_BACKOFF_SECONDS: float = 2.0
DEFAULT_DOWNLOADER_MAX_ATTEMPTS: int = 3
DEFAULT_DOWNLOADER_BACKOFF_SECONDS: float = 0.25
DEFAULT_RETRY_AFTER_MAX_SECONDS: float = 30.0


class ErrorCategory(str, Enum):
    """Action-oriented classification shared by desktop components."""

    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    CANCELLED = "CANCELLED"
    INTERNAL = "INTERNAL"


class ErrorStage(str, Enum):
    """The desktop pipeline stage that produced an error."""

    VALIDATION = "VALIDATION"
    EXTRACTION = "EXTRACTION"
    FOLDER = "FOLDER"
    DOWNLOAD = "DOWNLOAD"
    METADATA = "METADATA"
    PROTOCOL = "PROTOCOL"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class AppError:
    """Small canonical error value suitable for policy, UI, and logs."""

    error_code: str
    category: ErrorCategory
    stage: ErrorStage
    user_message: str
    technical_message: str
    retryable: bool
    exception_type: str | None = None
    retry_after_seconds: float | None = None


class AppErrorException(RuntimeError):
    """Carry one canonical error across a worker boundary."""

    def __init__(self, error: AppError) -> None:
        self.error = error
        super().__init__(error.technical_message or error.user_message)


_TRANSIENT_CODES: frozenset[str] = frozenset(
    {
        "TIMEOUT",
        "PRODUCT_TIMEOUT",
        "NETWORK_TIMEOUT",
        "CONNECTION_RESET",
        "BRIDGE_DISCONNECTED",
        "BRIDGE_INTERRUPTED",
        "NATIVE_HOST_DISCONNECTED",
        "TEMPORARY_BRIDGE_INTERRUPTION",
    }
)
_PERMANENT_CODES: frozenset[str] = frozenset(
    {
        "NOT_FOUND",
        "PRODUCT_NOT_FOUND",
        "INVALID_URL",
        "INVALID_SHOPEE_URL",
        "INVALID_OUTPUT_PATH",
        "PATH_CONTAINMENT_VIOLATION",
        "PRODUCT_FOLDER_ERROR",
        "INVALID_PRODUCT_ID",
        "MULTIPLE_PRODUCT_FOLDERS",
        "PERMISSION_DENIED",
        "DISK_FULL",
        "IMAGE_DOWNLOAD_ERROR",
        "METADATA_WRITE_ERROR",
        "UNSUPPORTED_RESPONSE",
        "EMPTY_IMAGE_RESPONSE",
        "NON_IMAGE_RESPONSE",
    }
)
_USER_ACTION_CODES: frozenset[str] = frozenset({"VERIFICATION_REQUIRED"})
_CANCELLED_CODES: frozenset[str] = frozenset({"CANCELLED", "USER_CANCELLED"})
_PROTOCOL_CODES: frozenset[str] = frozenset(
    {"PROTOCOL_INTEGRITY_ERROR", "INVALID_PROTOCOL_VERSION", "MALFORMED_PRODUCT_RESULT"}
)
_METADATA_CODES: frozenset[str] = frozenset({"METADATA_WRITE_ERROR"})

_USER_MESSAGES: dict[str, str] = {
    "TIMEOUT": "Hết thời gian chờ Shopee.",
    "PRODUCT_TIMEOUT": "Hết thời gian chờ Shopee.",
    "NETWORK_TIMEOUT": "Hết thời gian kết nối.",
    "CONNECTION_RESET": "Kết nối tạm thời bị gián đoạn.",
    "BRIDGE_DISCONNECTED": "Kết nối với Chrome tạm thời bị gián đoạn.",
    "BRIDGE_INTERRUPTED": "Kết nối với Chrome tạm thời bị gián đoạn.",
    "NATIVE_HOST_DISCONNECTED": "Kết nối với Chrome tạm thời bị gián đoạn.",
    "TEMPORARY_BRIDGE_INTERRUPTION": "Kết nối với Chrome tạm thời bị gián đoạn.",
    "NOT_FOUND": "Không tìm thấy sản phẩm.",
    "PRODUCT_NOT_FOUND": "Không tìm thấy sản phẩm.",
    "INVALID_URL": "Link sản phẩm Shopee không hợp lệ.",
    "INVALID_SHOPEE_URL": "Link sản phẩm Shopee không hợp lệ.",
    "INVALID_OUTPUT_PATH": "Không thể tạo thư mục sản phẩm.",
    "PATH_CONTAINMENT_VIOLATION": "Không thể tạo thư mục sản phẩm.",
    "PRODUCT_FOLDER_ERROR": "Không thể tạo thư mục sản phẩm.",
    "INVALID_PRODUCT_ID": "Dữ liệu định danh sản phẩm không hợp lệ.",
    "MULTIPLE_PRODUCT_FOLDERS": "Phát hiện nhiều thư mục cho cùng một sản phẩm.",
    "PERMISSION_DENIED": "Không có quyền ghi vào thư mục đầu ra.",
    "DISK_FULL": "Không đủ dung lượng ổ đĩa.",
    "IMAGE_DOWNLOAD_ERROR": "Không thể hoàn tất tải ảnh sản phẩm.",
    "METADATA_WRITE_ERROR": "Không thể ghi thông tin sản phẩm.",
    "UNSUPPORTED_RESPONSE": "Phản hồi không phải ảnh.",
    "EMPTY_IMAGE_RESPONSE": "Phản hồi ảnh rỗng.",
    "NON_IMAGE_RESPONSE": "Phản hồi chứa HTML hoặc JSON, không phải ảnh.",
    "VERIFICATION_REQUIRED": "Shopee yêu cầu xác minh trên Chrome.",
    "CANCELLED": "Đã hủy.",
    "USER_CANCELLED": "Đã hủy.",
    "PROTOCOL_INTEGRITY_ERROR": "Lỗi đồng bộ dữ liệu ảnh",
    "INVALID_PROTOCOL_VERSION": "Phiên bản giao thức không hợp lệ.",
    "MALFORMED_PRODUCT_RESULT": "Dữ liệu sản phẩm không hợp lệ.",
    "INTERNAL_ERROR": "Lỗi nội bộ khi xử lý sản phẩm.",
    "ERROR": "Lỗi nội bộ khi xử lý sản phẩm.",
}


def classify_error_code(
    error_code: str,
    *,
    stage: ErrorStage,
    technical_message: str = "",
    retry_after_seconds: float | None = None,
) -> AppError:
    """Map an existing desktop/extension error code through one policy."""
    normalized = str(error_code or "INTERNAL_ERROR").strip().upper()
    if normalized in _PROTOCOL_CODES:
        resolved_stage = ErrorStage.PROTOCOL
    elif normalized in _METADATA_CODES:
        resolved_stage = ErrorStage.METADATA
    else:
        resolved_stage = stage

    if normalized.startswith("HTTP_"):
        try:
            return error_from_http_status(
                int(normalized.removeprefix("HTTP_")),
                stage=resolved_stage,
                technical_message=technical_message,
                retry_after_seconds=retry_after_seconds,
            )
        except ValueError:
            pass

    if normalized in _TRANSIENT_CODES:
        category = ErrorCategory.TRANSIENT
    elif normalized in _PERMANENT_CODES:
        category = ErrorCategory.PERMANENT
    elif normalized in _USER_ACTION_CODES:
        category = ErrorCategory.USER_ACTION_REQUIRED
    elif normalized in _CANCELLED_CODES:
        category = ErrorCategory.CANCELLED
        resolved_stage = ErrorStage.CANCEL
    else:
        category = ErrorCategory.INTERNAL

    user_message = _USER_MESSAGES.get(
        normalized,
        _USER_MESSAGES["INTERNAL_ERROR"],
    )
    technical = technical_message.strip() or normalized
    return AppError(
        error_code=normalized,
        category=category,
        stage=resolved_stage,
        user_message=user_message,
        technical_message=technical,
        retryable=category == ErrorCategory.TRANSIENT,
        retry_after_seconds=retry_after_seconds,
    )


def error_from_http_status(
    status_code: int,
    *,
    stage: ErrorStage = ErrorStage.DOWNLOAD,
    technical_message: str = "",
    retry_after_seconds: float | None = None,
) -> AppError:
    """Classify one HTTP status without embedding retry decisions in callers."""
    code = f"HTTP_{status_code}"
    category = (
        ErrorCategory.TRANSIENT
        if status_code == 429 or 500 <= status_code <= 599
        else ErrorCategory.PERMANENT
    )
    display = f"HTTP {status_code}"
    return AppError(
        error_code=code,
        category=category,
        stage=stage,
        user_message=display,
        technical_message=technical_message.strip() or display,
        retryable=category == ErrorCategory.TRANSIENT,
        retry_after_seconds=retry_after_seconds,
    )


def is_disk_full_error(exc: BaseException) -> bool:
    """Recognize POSIX ENOSPC and Windows ERROR_DISK_FULL."""
    return (
        getattr(exc, "errno", None) == errno.ENOSPC
        or getattr(exc, "winerror", None) == 112
    )


def error_from_exception(
    exc: BaseException,
    *,
    stage: ErrorStage,
    default_code: str = "INTERNAL_ERROR",
) -> AppError:
    """Convert an exception at a meaningful boundary into an AppError."""
    if is_disk_full_error(exc):
        code = "DISK_FULL"
    elif isinstance(exc, PermissionError):
        code = "PERMISSION_DENIED"
    elif isinstance(exc, (TimeoutError, ConnectionError)):
        code = "NETWORK_TIMEOUT" if isinstance(exc, TimeoutError) else "CONNECTION_RESET"
    else:
        code = default_code
    classified = classify_error_code(
        code,
        stage=stage,
        technical_message=f"{type(exc).__name__}: {exc}",
    )
    return replace(classified, exception_type=type(exc).__name__)


def parse_retry_after(
    value: object,
    *,
    maximum_seconds: float = DEFAULT_RETRY_AFTER_MAX_SECONDS,
    now: datetime | None = None,
) -> float | None:
    """Parse an HTTP Retry-After delta/date and clamp it to a safe bound."""
    if maximum_seconds < 0:
        raise ValueError("maximum_seconds cannot be negative")
    text = str(value or "").strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        seconds = (retry_at - current).total_seconds()
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, maximum_seconds)


@dataclass(frozen=True)
class RetryPolicy:
    """Central bounded-attempt and backoff decision policy."""

    max_attempts: int
    initial_delay_seconds: float
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = DEFAULT_RETRY_AFTER_MAX_SECONDS

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds cannot be negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least one")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds cannot be negative")

    @classmethod
    def product_default(cls) -> RetryPolicy:
        """Return the desktop product extraction retry policy."""
        return cls(
            max_attempts=DEFAULT_PRODUCT_MAX_ATTEMPTS,
            initial_delay_seconds=DEFAULT_PRODUCT_BACKOFF_SECONDS,
            backoff_multiplier=2.0,
            max_delay_seconds=DEFAULT_PRODUCT_MAX_BACKOFF_SECONDS,
        )

    @classmethod
    def downloader_default(cls) -> RetryPolicy:
        """Return the Task 007B per-image retry policy."""
        return cls(
            max_attempts=DEFAULT_DOWNLOADER_MAX_ATTEMPTS,
            initial_delay_seconds=DEFAULT_DOWNLOADER_BACKOFF_SECONDS,
            backoff_multiplier=2.0,
            max_delay_seconds=DEFAULT_RETRY_AFTER_MAX_SECONDS,
        )

    def should_retry(self, error: AppError, attempt: int) -> bool:
        """Return whether a failed 1-based attempt may be followed by another."""
        return error.retryable and attempt < self.max_attempts

    def get_delay(self, attempt: int, error: AppError) -> float:
        """Return bounded backoff after the given failed 1-based attempt."""
        if error.retry_after_seconds is not None:
            return min(max(0.0, error.retry_after_seconds), self.max_delay_seconds)
        calculated = self.initial_delay_seconds * (
            self.backoff_multiplier ** max(0, attempt - 1)
        )
        return min(calculated, self.max_delay_seconds)
