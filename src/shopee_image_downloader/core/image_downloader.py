"""Deterministic image downloading for authoritative desktop product images."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
)
PART_FILE_SUFFIX: str = ".part"

_MIME_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
    "image/tiff": ".tif",
    "image/avif": ".avif",
}
_URL_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
)
_AMBIGUOUS_MIME_TYPES: frozenset[str] = frozenset(
    {"", "application/octet-stream", "binary/octet-stream"}
)


class ImageDownloadStatus(str, Enum):
    """Terminal status for one authoritative image URL."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED_EXISTING = "SKIPPED_EXISTING"


@dataclass(frozen=True)
class DownloadConfig:
    """Centralized bounded network and retry configuration."""

    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 15.0
    overall_timeout_seconds: float = 30.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.25
    chunk_size: int = 64 * 1024
    user_agent: str = DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ValueError("Network timeouts must be greater than zero.")
        if self.overall_timeout_seconds <= 0:
            raise ValueError("Overall timeout must be greater than zero.")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative.")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be at least one byte.")

    @property
    def socket_timeout_seconds(self) -> float:
        """Return the stricter urllib connect/read socket timeout."""
        return min(self.connect_timeout_seconds, self.read_timeout_seconds)


@dataclass(frozen=True)
class ImageDownloadResult:
    """Structured outcome for one image URL, using a one-based source index."""

    index: int
    source_url: str
    target_path: Path
    status: ImageDownloadStatus
    attempts: int
    error: str | None = None


@dataclass(frozen=True)
class ProductDownloadResult:
    """Aggregate download outcome stored on the existing desktop product model."""

    total: int
    successful: int
    failed: int
    skipped: int
    items: tuple[ImageDownloadResult, ...]

    @classmethod
    def from_items(
        cls,
        total: int,
        items: Sequence[ImageDownloadResult],
    ) -> ProductDownloadResult:
        """Build aggregate counters from per-image results."""
        frozen_items = tuple(items)
        if total < 0 or len(frozen_items) != total:
            raise ValueError("Per-image results must match the declared total.")
        return cls(
            total=total,
            successful=sum(
                item.status == ImageDownloadStatus.SUCCESS for item in frozen_items
            ),
            failed=sum(
                item.status == ImageDownloadStatus.FAILED for item in frozen_items
            ),
            skipped=sum(
                item.status == ImageDownloadStatus.SKIPPED_EXISTING
                for item in frozen_items
            ),
            items=frozen_items,
        )

    @property
    def completed_with_errors(self) -> bool:
        """Return whether all URLs were processed but one or more failed."""
        return self.failed > 0


class DownloadCancelledError(RuntimeError):
    """Raised when cooperative cancellation stops an in-progress product."""


class _AttemptError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ImageDownloader:
    """Download authoritative image URLs sequentially into one product folder."""

    def __init__(
        self,
        config: DownloadConfig | None = None,
        *,
        open_url: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or DownloadConfig()
        self._open_url = open_url
        self._sleep = sleeper
        self._monotonic = monotonic

    def download_product_images(
        self,
        images: Sequence[str],
        product_folder: str | Path,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ProductDownloadResult:
        """Download ``images`` in source order and return aggregate results.

        The sequence is never sorted or mutated. Each callback index is one-based.
        """
        folder = self._validated_product_folder(product_folder)
        authoritative_images = tuple(images)
        total = len(authoritative_images)
        results: list[ImageDownloadResult] = []

        for index, source_url in enumerate(authoritative_images, start=1):
            self._raise_if_cancelled(cancel_check)
            result = self.download_image(
                source_url,
                index=index,
                total=total,
                product_folder=folder,
                cancel_check=cancel_check,
            )
            results.append(result)
            if progress_callback is not None:
                progress_callback(index, total)

        return ProductDownloadResult.from_items(total, results)

    def download_image(
        self,
        source_url: str,
        *,
        index: int,
        total: int,
        product_folder: str | Path,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ImageDownloadResult:
        """Download one URL to its controlled sequential filename."""
        folder = self._validated_product_folder(product_folder)
        if index < 1 or total < index:
            raise ValueError("index must be between one and total, inclusive.")

        padding = max(2, len(str(total)))
        stem = f"{index:0{padding}d}"
        fallback_target = self._target_path(
            folder,
            stem,
            self._extension_from_url(source_url) or ".jpg",
        )
        self._remove_leftover_parts(folder, stem)

        error_message = "Không thể tải ảnh."
        attempts = 0
        for attempt in range(1, self.config.max_attempts + 1):
            attempts = attempt
            self._raise_if_cancelled(cancel_check)
            try:
                return self._download_once(
                    source_url=source_url,
                    index=index,
                    stem=stem,
                    folder=folder,
                    attempt=attempt,
                    cancel_check=cancel_check,
                )
            except DownloadCancelledError:
                self._remove_leftover_parts(folder, stem)
                raise
            except _AttemptError as exc:
                error_message = str(exc)
                self._remove_leftover_parts(folder, stem)
                if not exc.retryable or attempt >= self.config.max_attempts:
                    break
                backoff = self.config.retry_backoff_seconds * attempt
                logger.warning(
                    "Thử lại ảnh %d/%d sau lỗi tạm thời: %s",
                    index,
                    total,
                    error_message,
                )
                self._raise_if_cancelled(cancel_check)
                self._sleep(backoff)

        return ImageDownloadResult(
            index=index,
            source_url=source_url,
            target_path=fallback_target,
            status=ImageDownloadStatus.FAILED,
            attempts=attempts,
            error=error_message,
        )

    def _download_once(
        self,
        *,
        source_url: str,
        index: int,
        stem: str,
        folder: Path,
        attempt: int,
        cancel_check: Callable[[], bool] | None,
    ) -> ImageDownloadResult:
        started_at = self._monotonic()
        try:
            if urlsplit(source_url).scheme.lower() not in {"http", "https"}:
                raise ValueError("unsupported image URL scheme")
            request = Request(
                source_url,
                headers={
                    "User-Agent": self.config.user_agent,
                    "Accept": "image/*",
                },
                method="GET",
            )
            response = self._open_url(
                request,
                timeout=self.config.socket_timeout_seconds,
            )
        except HTTPError as exc:
            raise _AttemptError(
                f"HTTP {exc.code}",
                retryable=exc.code == 429 or 500 <= exc.code <= 599,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise _AttemptError("Hết thời gian tải ảnh.", retryable=True) from exc
        except URLError as exc:
            message = (
                "Hết thời gian tải ảnh."
                if isinstance(exc.reason, (TimeoutError, socket.timeout))
                else "Không thể kết nối máy chủ ảnh."
            )
            raise _AttemptError(message, retryable=True) from exc
        except (ConnectionError, OSError) as exc:
            raise _AttemptError(
                "Không thể kết nối máy chủ ảnh.", retryable=True
            ) from exc
        except (TypeError, ValueError) as exc:
            raise _AttemptError("URL ảnh không hợp lệ.", retryable=False) from exc

        try:
            with response:
                return self._consume_response(
                    response=response,
                    source_url=source_url,
                    index=index,
                    stem=stem,
                    folder=folder,
                    attempt=attempt,
                    started_at=started_at,
                    cancel_check=cancel_check,
                )
        except _AttemptError:
            raise
        except DownloadCancelledError:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise _AttemptError("Hết thời gian tải ảnh.", retryable=True) from exc
        except (ConnectionError, OSError) as exc:
            raise _AttemptError("Kết nối tải ảnh bị gián đoạn.", retryable=True) from exc

    def _consume_response(
        self,
        *,
        response: Any,
        source_url: str,
        index: int,
        stem: str,
        folder: Path,
        attempt: int,
        started_at: float,
        cancel_check: Callable[[], bool] | None,
    ) -> ImageDownloadResult:
        status_code = getattr(response, "status", None)
        if status_code is None and hasattr(response, "getcode"):
            status_code = response.getcode()
        if not isinstance(status_code, int) or not 200 <= status_code <= 299:
            code = status_code if isinstance(status_code, int) else "không xác định"
            retryable = status_code == 429 or (
                isinstance(status_code, int) and 500 <= status_code <= 599
            )
            raise _AttemptError(f"HTTP {code}", retryable=retryable)

        raw_content_type = ""
        headers = getattr(response, "headers", None)
        if headers is not None:
            raw_content_type = str(headers.get("Content-Type", ""))
        mime_type = raw_content_type.split(";", 1)[0].strip().lower()
        mime_extension = _MIME_EXTENSIONS.get(mime_type)
        if mime_extension is None and mime_type not in _AMBIGUOUS_MIME_TYPES:
            raise _AttemptError(
                f"Phản hồi không phải ảnh ({mime_type or 'không rõ'}).",
                retryable=False,
            )

        self._raise_if_cancelled(cancel_check)
        first_chunk = self._read_chunk(response, started_at)
        if not first_chunk:
            raise _AttemptError("Phản hồi ảnh rỗng.", retryable=False)
        if self._looks_like_non_image(first_chunk):
            raise _AttemptError("Phản hồi chứa HTML hoặc JSON, không phải ảnh.", retryable=False)

        extension = (
            mime_extension
            or self._extension_from_signature(first_chunk)
            or self._extension_from_url(source_url)
            or ".jpg"
        )
        target = self._target_path(folder, stem, extension)
        if target.exists() and target.is_file() and target.stat().st_size > 0:
            return ImageDownloadResult(
                index=index,
                source_url=source_url,
                target_path=target,
                status=ImageDownloadStatus.SKIPPED_EXISTING,
                attempts=attempt,
            )

        part_path = target.with_name(target.name + PART_FILE_SUFFIX)
        try:
            if part_path.exists():
                part_path.unlink()
            with part_path.open("wb") as output_file:
                output_file.write(first_chunk)
                while True:
                    self._raise_if_cancelled(cancel_check)
                    chunk = self._read_chunk(response, started_at)
                    if not chunk:
                        break
                    output_file.write(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())

            self._raise_if_cancelled(cancel_check)
            if target.exists() and target.is_file() and target.stat().st_size > 0:
                part_path.unlink(missing_ok=True)
                return ImageDownloadResult(
                    index=index,
                    source_url=source_url,
                    target_path=target,
                    status=ImageDownloadStatus.SKIPPED_EXISTING,
                    attempts=attempt,
                )
            part_path.replace(target)
        except DownloadCancelledError:
            part_path.unlink(missing_ok=True)
            raise
        except OSError as exc:
            part_path.unlink(missing_ok=True)
            raise _AttemptError("Không thể ghi tệp ảnh.", retryable=False) from exc

        return ImageDownloadResult(
            index=index,
            source_url=source_url,
            target_path=target,
            status=ImageDownloadStatus.SUCCESS,
            attempts=attempt,
        )

    def _read_chunk(self, response: Any, started_at: float) -> bytes:
        if self._monotonic() - started_at >= self.config.overall_timeout_seconds:
            raise _AttemptError("Hết thời gian tổng để tải ảnh.", retryable=True)
        try:
            chunk = response.read(self.config.chunk_size)
        except (TimeoutError, socket.timeout) as exc:
            raise _AttemptError("Hết thời gian đọc ảnh.", retryable=True) from exc
        except (ConnectionError, OSError) as exc:
            raise _AttemptError("Kết nối tải ảnh bị gián đoạn.", retryable=True) from exc
        if self._monotonic() - started_at >= self.config.overall_timeout_seconds:
            raise _AttemptError("Hết thời gian tổng để tải ảnh.", retryable=True)
        if not isinstance(chunk, bytes):
            raise _AttemptError("Phản hồi ảnh không hợp lệ.", retryable=False)
        return chunk

    @staticmethod
    def _validated_product_folder(product_folder: str | Path) -> Path:
        try:
            folder = Path(product_folder).resolve(strict=True)
        except (OSError, RuntimeError, TypeError) as exc:
            raise ValueError("Thư mục sản phẩm không tồn tại hoặc không khả dụng.") from exc
        if not folder.is_dir():
            raise ValueError("Đường dẫn thư mục sản phẩm không phải thư mục.")
        return folder

    @staticmethod
    def _target_path(folder: Path, stem: str, extension: str) -> Path:
        target = folder / f"{stem}{extension}"
        resolved_target = target.resolve(strict=False)
        if resolved_target.parent != folder:
            raise ValueError("Đường dẫn ảnh nằm ngoài thư mục sản phẩm.")
        return target

    @staticmethod
    def _extension_from_url(source_url: str) -> str | None:
        try:
            suffix = Path(urlsplit(source_url).path).suffix.lower()
        except ValueError:
            return None
        if suffix not in _URL_EXTENSIONS:
            return None
        if suffix == ".jpeg":
            return ".jpg"
        if suffix == ".tiff":
            return ".tif"
        return suffix

    @staticmethod
    def _extension_from_signature(first_chunk: bytes) -> str | None:
        if first_chunk.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if first_chunk.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if first_chunk.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if first_chunk.startswith(b"RIFF") and first_chunk[8:12] == b"WEBP":
            return ".webp"
        if first_chunk.startswith(b"BM"):
            return ".bmp"
        return None

    @staticmethod
    def _looks_like_non_image(first_chunk: bytes) -> bool:
        stripped = first_chunk.lstrip().lower()
        return stripped.startswith(
            (b"<!doctype html", b"<html", b"<head", b"<body", b"<?xml", b"{", b"[")
        )

    @staticmethod
    def _raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
        if cancel_check is not None and cancel_check():
            raise DownloadCancelledError("Đã hủy tải ảnh.")

    @staticmethod
    def _remove_leftover_parts(folder: Path, stem: str) -> None:
        for extension in _URL_EXTENSIONS | {".jpg", ".tif"}:
            part_path = folder / f"{stem}{extension}{PART_FILE_SUFFIX}"
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Không thể xóa tệp tải dở: %s", part_path)
