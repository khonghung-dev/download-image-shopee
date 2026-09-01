"""Presentation-only text, tones, and styles for the desktop UI."""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import QTableWidgetItem

from shopee_image_downloader.core.batch_queue import (
    ItemState,
    QueueItem,
)
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

_STATUS_FOREGROUNDS: dict[StatusTone, QColor] = {
    StatusTone.NEUTRAL: QColor("#5f6368"),
    StatusTone.ACTIVE: QColor("#1769aa"),
    StatusTone.SUCCESS: QColor("#247a3c"),
    StatusTone.WARNING: QColor("#8a5a00"),
    StatusTone.ERROR: QColor("#b3261e"),
    StatusTone.SKIPPED: QColor("#6b7280"),
    StatusTone.CANCELLED: QColor("#6b7280"),
}


APP_STYLE_SHEET: str = """
QWidget {
    font-size: 10pt;
}
QLabel[role="sectionTitle"] {
    font-weight: 600;
}
QLabel#urlCountLabel,
QLabel#bridgeTitleLabel,
QLabel#batchProgressLabel {
    color: #5f6368;
}
QFrame#bridgeFrame {
    background-color: #f7f7f8;
    border: 1px solid #dfe1e5;
    border-radius: 5px;
}
QPushButton {
    padding: 6px 12px;
}
QPushButton#startButton {
    background-color: #ee4d2d;
    border: 1px solid #d84325;
    border-radius: 4px;
    color: white;
    font-weight: 600;
    padding: 7px 18px;
}
QPushButton#startButton:hover {
    background-color: #df4326;
}
QPushButton#startButton:disabled {
    background-color: #d8dadd;
    border-color: #c7c9cc;
    color: #76797d;
}
QPushButton#continueButton {
    font-weight: 600;
}
QProgressBar {
    min-height: 18px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #ee4d2d;
}
QLabel#currentProductLabel {
    color: #303134;
}
QLabel#summaryLabel {
    background-color: #f7f7f8;
    border: 1px solid #dfe1e5;
    border-radius: 5px;
    padding: 8px 10px;
}
QLabel#summaryLabel[statusTone="success"] {
    color: #247a3c;
}
QLabel#summaryLabel[statusTone="warning"] {
    color: #8a5a00;
}
QLabel#summaryLabel[statusTone="error"] {
    color: #b3261e;
}
QLabel#summaryLabel[statusTone="cancelled"] {
    color: #5f6368;
}
"""


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
) -> None:
    """Apply centralized, restrained formatting to one status cell."""
    item.setForeground(QBrush(_STATUS_FOREGROUNDS[tone]))
    font = QFont(item.font())
    font.setBold(tone in {StatusTone.ACTIVE, StatusTone.SUCCESS, StatusTone.ERROR})
    item.setFont(font)
