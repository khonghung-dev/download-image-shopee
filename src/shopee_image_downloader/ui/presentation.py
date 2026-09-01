"""Presentation-only text and tones for the desktop UI."""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import QTableWidgetItem

from shopee_image_downloader.core.batch_queue import ItemState, QueueItem
from shopee_image_downloader.core.image_downloader import ProductDownloadResult


class StatusTone(str, Enum):
    """Restrained visual categories used by status text."""

    NEUTRAL = "neutral"
    ACTIVE = "active"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


ITEM_STATE_TEXT: dict[ItemState, str] = {
    ItemState.PENDING: "Chờ xử lý",
    ItemState.OPENING_PRODUCT: "Đang mở sản phẩm",
    ItemState.WAITING_EXTRACTION: "Đang lấy dữ liệu",
    ItemState.WAITING_RETRY: "Đang thử lại",
    ItemState.CREATING_FOLDER: "Đang tạo thư mục",
    ItemState.DOWNLOADING: "Đang tải ảnh",
    ItemState.SUCCESS: "Hoàn tất",
    ItemState.COMPLETED_WITH_ERRORS: "Hoàn tất một phần",
    ItemState.FAILED: "Lỗi",
    ItemState.SKIPPED_DUPLICATE: "Trùng sản phẩm — đã bỏ qua",
    ItemState.CANCELLED: "Đã hủy",
}

ITEM_STATE_TONES: dict[ItemState, StatusTone] = {
    ItemState.PENDING: StatusTone.NEUTRAL,
    ItemState.OPENING_PRODUCT: StatusTone.ACTIVE,
    ItemState.WAITING_EXTRACTION: StatusTone.ACTIVE,
    ItemState.WAITING_RETRY: StatusTone.WARNING,
    ItemState.CREATING_FOLDER: StatusTone.ACTIVE,
    ItemState.DOWNLOADING: StatusTone.ACTIVE,
    ItemState.SUCCESS: StatusTone.SUCCESS,
    ItemState.COMPLETED_WITH_ERRORS: StatusTone.WARNING,
    ItemState.FAILED: StatusTone.ERROR,
    ItemState.SKIPPED_DUPLICATE: StatusTone.SKIPPED,
    ItemState.CANCELLED: StatusTone.CANCELLED,
}

_DEFAULT_STATUS_FOREGROUNDS: dict[StatusTone, QColor] = {
    StatusTone.NEUTRAL: QColor("#94a3b8"),
    StatusTone.ACTIVE: QColor("#22d3ee"),
    StatusTone.SUCCESS: QColor("#4ade80"),
    StatusTone.WARNING: QColor("#fbbf24"),
    StatusTone.ERROR: QColor("#fb7185"),
    StatusTone.SKIPPED: QColor("#c084fc"),
    StatusTone.CANCELLED: QColor("#94a3b8"),
}

STATUS_TONE_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1


def item_state_text(state: ItemState) -> str:
    """Return the canonical Vietnamese label for one item state."""
    return ITEM_STATE_TEXT[state]


def item_state_tone(state: ItemState) -> StatusTone:
    """Return the presentation tone for one authoritative item state."""
    return ITEM_STATE_TONES[state]


def item_progress_text(item: QueueItem) -> str:
    """Build dynamic progress text from the current queue item model."""
    if item.state == ItemState.WAITING_RETRY:
        next_attempt = min(item.attempt + 1, item.max_attempts)
        return f"Đang thử lại {next_attempt}/{item.max_attempts}..."
    if item.stage == "metadata":
        return "Đang lưu thông tin sản phẩm..."
    return item_state_text(item.state)


def download_status_text(result: ProductDownloadResult | None) -> str:
    """Return a terminal product status without treating existing files as errors."""
    if result is None:
        return item_state_text(ItemState.SUCCESS)
    available = result.successful + result.skipped
    if result.failed:
        return f"Hoàn tất một phần — {available}/{result.total} ảnh"
    return f"Hoàn tất — {available}/{result.total} ảnh"


def image_count_text(result: ProductDownloadResult | None, total: int) -> str:
    """Return authoritative image availability for the result-table image column."""
    if result is None:
        return str(total)
    return f"{result.successful + result.skipped}/{result.total}"


def batch_summary_text(items: Sequence[QueueItem]) -> str:
    """Build one summary solely from terminal queue-item states."""
    total = len(items)
    success = sum(
        item.state in {ItemState.SUCCESS, ItemState.COMPLETED_WITH_ERRORS}
        for item in items
    )
    duplicate = sum(item.state == ItemState.SKIPPED_DUPLICATE for item in items)
    failed = sum(item.state == ItemState.FAILED for item in items)
    cancelled = sum(item.state == ItemState.CANCELLED for item in items)

    if total > 0 and success == total:
        return f"Hoàn tất {total}/{total} sản phẩm."

    counts = [f"{success} thành công"]
    if duplicate:
        counts.append(f"{duplicate} trùng")
    if failed:
        counts.append(f"{failed} lỗi")
    if cancelled:
        counts.append(f"{cancelled} đã hủy")
    heading = "Đã hủy" if cancelled else "Hoàn tất"
    return f"{heading} — " + " · ".join(counts)


def batch_summary_tone(items: Sequence[QueueItem]) -> StatusTone:
    """Return the final-summary tone from authoritative terminal states."""
    if any(item.state == ItemState.CANCELLED for item in items):
        return StatusTone.CANCELLED
    if any(item.state == ItemState.FAILED for item in items):
        return StatusTone.ERROR
    if any(item.state == ItemState.COMPLETED_WITH_ERRORS for item in items):
        return StatusTone.WARNING
    return StatusTone.SUCCESS


def apply_table_status_tone(
    item: QTableWidgetItem,
    tone: StatusTone,
    foreground: QColor | None = None,
) -> None:
    """Apply centralized formatting and retain its semantic tone for retheming."""
    item.setData(STATUS_TONE_DATA_ROLE, tone.value)
    item.setForeground(QBrush(foreground or _DEFAULT_STATUS_FOREGROUNDS[tone]))
    font = QFont(item.font())
    font.setBold(tone in {StatusTone.ACTIVE, StatusTone.SUCCESS, StatusTone.ERROR})
    item.setFont(font)
