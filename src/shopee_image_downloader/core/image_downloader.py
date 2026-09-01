"""Deterministic image downloading for authoritative desktop product images."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
import socket
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from shopee_image_downloader.core.error_policy import (
    AppError,
    AppErrorException,
    DEFAULT_DOWNLOADER_BACKOFF_SECONDS,
    DEFAULT_DOWNLOADER_MAX_ATTEMPTS,
    DEFAULT_RETRY_AFTER_MAX_SECONDS,
    ErrorStage,
    RetryPolicy,
    classify_error_code,
    error_from_exception,
    error_from_http_status,
    parse_retry_after,
)

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
)
PART_FILE_SUFFIX: str = ".part"
MAX_IMAGE_DOWNLOAD_WORKERS: int = 4

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
    max_attempts: int = DEFAULT_DOWNLOADER_MAX_ATTEMPTS
    retry_backoff_seconds: float = DEFAULT_DOWNLOADER_BACKOFF_SECONDS
    max_retry_after_seconds: float = DEFAULT_RETRY_AFTER_MAX_SECONDS
    chunk_size: int = 64 * 1024
    user_agent: str = DEFAULT_USER_AGENT
    max_workers: int = MAX_IMAGE_DOWNLOAD_WORKERS

    def __post_init__(self) -> None:
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ValueError("Network timeouts must be greater than zero.")
        if self.overall_timeout_seconds <= 0:
            raise ValueError("Overall timeout must be greater than zero.")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative.")
        if self.max_retry_after_seconds < 0:
            raise ValueError("max_retry_after_seconds cannot be negative.")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be at least one byte.")
        if not 1 <= self.max_workers <= MAX_IMAGE_DOWNLOAD_WORKERS:
            raise ValueError(
                f"max_workers must be between 1 and {MAX_IMAGE_DOWNLOAD_WORKERS}."
            )

    @property
    def socket_timeout_seconds(self) -> float:
        """Return the stricter urllib connect/read socket timeout."""
        return min(self.connect_timeout_seconds, self.read_timeout_seconds)

    @property
    def retry_policy(self) -> RetryPolicy:
        """Build the shared policy using this downloader's injected limits."""
        return RetryPolicy(
            max_attempts=self.max_attempts,
            initial_delay_seconds=self.retry_backoff_seconds,
            backoff_multiplier=2.0,
            max_delay_seconds=self.max_retry_after_seconds,
        )


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
    def __init__(self, error: AppError) -> None:
        self.error = error
        super().__init__(error.user_message)


class ImageDownloader:
    """Download authoritative images concurrently with ordered results."""

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
        self._pause_waiter: Callable[[], None] | None = None
        self._pause_check: Callable[[], bool] | None = None

    def set_pause_waiter(self, waiter: Callable[[], None] | None) -> None:
        """Install the worker-owned cooperative pause boundary callback."""
        self._pause_waiter = waiter

    def set_pause_control(
        self,
        pause_check: Callable[[], bool] | None,
        pause_waiter: Callable[[], None] | None,
    ) -> None:
        """Install worker-owned pause observation and boundary waiting."""
        self._pause_check = pause_check
        self._pause_waiter = pause_waiter

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
        if total == 0:
            return ProductDownloadResult.from_items(0, ())

        ordered_results: list[ImageDownloadResult | None] = [None] * total
        completed = 0
        next_index = 1
        active: dict[Future[ImageDownloadResult], int] = {}
        stop_event = threading.Event()
        terminal_error: BaseException | None = None

        def combined_cancel_check() -> bool:
            return stop_event.is_set() or bool(cancel_check and cancel_check())

        executor = ThreadPoolExecutor(
            max_workers=min(self.config.max_workers, total),
            thread_name_prefix="shopee-image",
        )
        try:
            while next_index <= total or active:
                if cancel_check is not None and cancel_check():
                    terminal_error = DownloadCancelledError("Đã hủy tải ảnh.")
                    stop_event.set()

                while (
                    terminal_error is None
                    and next_index <= total
                    and len(active) < self.config.max_workers
                    and not self._is_pause_requested()
                ):
                    source_url = authoritative_images[next_index - 1]
                    future = executor.submit(
                        self.download_image,
                        source_url,
                        index=next_index,
                        total=total,
                        product_folder=folder,
                        cancel_check=combined_cancel_check,
                    )
                    active[future] = next_index
                    next_index += 1

                if terminal_error is not None:
                    for future in active:
                        future.cancel()

                if active:
                    done, _pending = wait(
                        tuple(active),
                        return_when=FIRST_COMPLETED,
                    )
                    for future in sorted(done, key=lambda item: active[item]):
                        index = active.pop(future)
                        try:
                            result = future.result()
                        except DownloadCancelledError as exc:
                            if terminal_error is None:
                                terminal_error = exc
                                stop_event.set()
                        except BaseException as exc:
                            if terminal_error is None:
                                terminal_error = exc
                                stop_event.set()
                        else:
                            ordered_results[index - 1] = result
                            completed += 1
                            if progress_callback is not None:
                                progress_callback(completed, total)
                    continue

                if terminal_error is not None:
                    break

                self._raise_if_cancelled(cancel_check)
                if self._pause_waiter is not None:
                    self._pause_waiter()
                self._raise_if_cancelled(cancel_check)

            if terminal_error is not None:
                raise terminal_error
        finally:
            if terminal_error is not None or bool(cancel_check and cancel_check()):
                stop_event.set()
                for future in active:
                    future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)

        if any(result is None for result in ordered_results):
            raise AppErrorException(
                classify_error_code(
                    "INTERNAL_ERROR",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message="Concurrent downloader ended with missing results",
                )
            )
        return ProductDownloadResult.from_items(
            total,
            tuple(result for result in ordered_results if result is not None),
        )

    def _is_pause_requested(self) -> bool:
        return bool(self._pause_check and self._pause_check())

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
        retry_policy = self.config.retry_policy
        for attempt in range(1, retry_policy.max_attempts + 1):
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
                error_message = exc.error.user_message
                self._remove_leftover_parts(folder, stem)
                if exc.error.error_code in {"DISK_FULL", "PERMISSION_DENIED"}:
                    raise AppErrorException(exc.error) from exc
                if not retry_policy.should_retry(exc.error, attempt):
                    break
                backoff = retry_policy.get_delay(attempt, exc.error)
                logger.warning(
                    "Thử lại ảnh %d/%d: code=%s stage=%s attempt=%d/%d "
                    "delay=%.3fs technical=%s",
                    index,
                    total,
                    exc.error.error_code,
                    exc.error.stage.value,
                    attempt,
                    retry_policy.max_attempts,
                    backoff,
                    exc.error.technical_message,
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
            retry_after = self._retry_after_from_headers(exc.headers)
            raise _AttemptError(
                error_from_http_status(
                    exc.code,
                    technical_message=f"HTTPError: {exc}",
                    retry_after_seconds=retry_after,
                )
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise _AttemptError(
                classify_error_code(
                    "NETWORK_TIMEOUT",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=f"{type(exc).__name__}: {exc}",
                )
            ) from exc
        except URLError as exc:
            code = (
                "NETWORK_TIMEOUT"
                if isinstance(exc.reason, (TimeoutError, socket.timeout))
                else "CONNECTION_RESET"
            )
            raise _AttemptError(
                classify_error_code(
                    code,
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=f"URLError: {exc}",
                )
            ) from exc
        except (ConnectionError, OSError) as exc:
            raise _AttemptError(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="CONNECTION_RESET",
                )
            ) from exc
        except (TypeError, ValueError) as exc:
            raise _AttemptError(
                classify_error_code(
                    "INVALID_URL",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=f"{type(exc).__name__}: {exc}",
                )
            ) from exc

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
            raise _AttemptError(
                classify_error_code(
                    "NETWORK_TIMEOUT",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=f"{type(exc).__name__}: {exc}",
                )
            ) from exc
        except (ConnectionError, OSError) as exc:
            raise _AttemptError(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="CONNECTION_RESET",
                )
            ) from exc

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
            retry_after = self._retry_after_from_headers(
                getattr(response, "headers", None)
            )
            if isinstance(status_code, int):
                raise _AttemptError(
                    error_from_http_status(
                        status_code,
                        retry_after_seconds=retry_after,
                    )
                )
            raise _AttemptError(
                classify_error_code(
                    "UNSUPPORTED_RESPONSE",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=f"HTTP status is not an integer: {code}",
                )
            )

        raw_content_type = ""
        headers = getattr(response, "headers", None)
        if headers is not None:
            raw_content_type = str(headers.get("Content-Type", ""))
        mime_type = raw_content_type.split(";", 1)[0].strip().lower()
        mime_extension = _MIME_EXTENSIONS.get(mime_type)
        if mime_extension is None and mime_type not in _AMBIGUOUS_MIME_TYPES:
            raise _AttemptError(
                classify_error_code(
                    "UNSUPPORTED_RESPONSE",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=(
                        f"Unsupported image Content-Type: {mime_type or 'unknown'}"
                    ),
                )
            )

        self._raise_if_cancelled(cancel_check)
        first_chunk = self._read_chunk(response, started_at)
        if not first_chunk:
            raise _AttemptError(
                classify_error_code(
                    "EMPTY_IMAGE_RESPONSE",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message="Image response body was empty",
                )
            )
        if self._looks_like_non_image(first_chunk):
            raise _AttemptError(
                classify_error_code(
                    "NON_IMAGE_RESPONSE",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message="Image response signature is HTML or JSON",
                )
            )

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
            self._safe_unlink(part_path)
            raise
        except OSError as exc:
            self._safe_unlink(part_path)
            raise _AttemptError(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="IMAGE_DOWNLOAD_ERROR",
                )
            ) from exc

        return ImageDownloadResult(
            index=index,
            source_url=source_url,
            target_path=target,
            status=ImageDownloadStatus.SUCCESS,
            attempts=attempt,
        )

    def _read_chunk(self, response: Any, started_at: float) -> bytes:
        if self._monotonic() - started_at >= self.config.overall_timeout_seconds:
            raise _AttemptError(
                classify_error_code(
                    "NETWORK_TIMEOUT",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message="Overall image download deadline exceeded",
                )
            )
        try:
            chunk = response.read(self.config.chunk_size)
        except (TimeoutError, socket.timeout) as exc:
            raise _AttemptError(
                classify_error_code(
                    "NETWORK_TIMEOUT",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=f"{type(exc).__name__}: {exc}",
                )
            ) from exc
        except (ConnectionError, OSError) as exc:
            raise _AttemptError(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="CONNECTION_RESET",
                )
            ) from exc
        if self._monotonic() - started_at >= self.config.overall_timeout_seconds:
            raise _AttemptError(
                classify_error_code(
                    "NETWORK_TIMEOUT",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message="Overall image download deadline exceeded",
                )
            )
        if not isinstance(chunk, bytes):
            raise _AttemptError(
                classify_error_code(
                    "UNSUPPORTED_RESPONSE",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=(
                        f"Response.read returned {type(chunk).__name__}, expected bytes"
                    ),
                )
            )
        return chunk

    def _retry_after_from_headers(self, headers: Any) -> float | None:
        if headers is None:
            return None
        try:
            raw_value = headers.get("Retry-After", "")
        except (AttributeError, TypeError):
            return None
        return parse_retry_after(
            raw_value,
            maximum_seconds=self.config.max_retry_after_seconds,
        )

    @staticmethod
    def _validated_product_folder(product_folder: str | Path) -> Path:
        try:
            folder = Path(product_folder).resolve(strict=True)
        except (OSError, RuntimeError, TypeError) as exc:
            raise AppErrorException(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="INVALID_OUTPUT_PATH",
                )
            ) from exc
        try:
            is_directory = folder.is_dir()
        except OSError as exc:
            raise AppErrorException(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="INVALID_OUTPUT_PATH",
                )
            ) from exc
        if not is_directory:
            raise AppErrorException(
                classify_error_code(
                    "INVALID_OUTPUT_PATH",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=(
                        f"Product folder is not a directory: {folder}"
                    ),
                )
            )
        return folder

    @staticmethod
    def _target_path(folder: Path, stem: str, extension: str) -> Path:
        target = folder / f"{stem}{extension}"
        try:
            resolved_target = target.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise AppErrorException(
                error_from_exception(
                    exc,
                    stage=ErrorStage.DOWNLOAD,
                    default_code="INVALID_OUTPUT_PATH",
                )
            ) from exc
        if resolved_target.parent != folder:
            raise AppErrorException(
                classify_error_code(
                    "PATH_CONTAINMENT_VIOLATION",
                    stage=ErrorStage.DOWNLOAD,
                    technical_message=(
                        f"Image target escapes product folder: {target}"
                    ),
                )
            )
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

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Không thể xóa tệp tải dở: %s", path)
