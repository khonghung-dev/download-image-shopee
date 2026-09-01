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
    StatusTone.NEUTRAL: QColor("#94a3b8"),
    StatusTone.ACTIVE: QColor("#22d3ee"),
    StatusTone.SUCCESS: QColor("#4ade80"),
    StatusTone.WARNING: QColor("#fbbf24"),
    StatusTone.ERROR: QColor("#fb7185"),
    StatusTone.SKIPPED: QColor("#c084fc"),
    StatusTone.CANCELLED: QColor("#94a3b8"),
}


APP_STYLE_SHEET: str = """
QWidget {
    background-color: #070b17;
    color: #e6edf7;
    font-family: "Segoe UI Variable", "Segoe UI";
    font-size: 10pt;
}
QFrame#heroHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #111c33, stop:0.55 #151936, stop:1 #25133d);
    border: 1px solid #2a3c62;
    border-radius: 12px;
}
QLabel[role="heroTitle"] {
    color: #f8fbff;
    font-size: 17pt;
    font-weight: 700;
}
QLabel[role="heroSubtitle"] {
    color: #8aa4c8;
    font-size: 9pt;
}
QFrame[role="card"] {
    background-color: #10182b;
    border: 1px solid #263757;
    border-radius: 11px;
}
QLabel[role="sectionTitle"] {
    color: #dbeafe;
    font-weight: 700;
}
QLabel#urlCountLabel,
QLabel#bridgeTitleLabel,
QLabel#batchProgressLabel {
    color: #8da2c3;
}
QFrame#bridgeFrame {
    background-color: #131d32;
    border: 1px solid #33466d;
    border-radius: 12px;
}
QFrame#bridgeFrame[connectionState="connected"] {
    background-color: #0d2b27;
    border-color: #22c55e;
}
QFrame#bridgeFrame[connectionState="connected"] QLabel {
    color: #86efac;
}
QFrame#bridgeFrame[connectionState="lost"],
QFrame#bridgeFrame[connectionState="disconnected"] {
    border-color: #7f3147;
}
QFrame#bridgeFrame[connectionState="lost"] QLabel,
QFrame#bridgeFrame[connectionState="disconnected"] QLabel {
    color: #fda4af;
}
QLineEdit {
    min-height: 30px;
    background-color: #0b1222;
    color: #e6edf7;
    border: 1px solid #33466d;
    border-radius: 7px;
    padding: 3px 9px;
    selection-background-color: #7c3aed;
}
QLineEdit:focus {
    border: 1px solid #22d3ee;
}
QCheckBox {
    color: #cbd5e1;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #52678e;
    border-radius: 4px;
    background-color: #0b1222;
}
QCheckBox::indicator:checked {
    background-color: #7c3aed;
    border-color: #22d3ee;
}
QPushButton {
    min-height: 30px;
    background-color: #18233b;
    border: 1px solid #3a4f78;
    border-radius: 7px;
    color: #dbeafe;
    padding: 4px 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #223255;
    border-color: #38bdf8;
}
QPushButton:pressed {
    background-color: #111a2e;
}
QPushButton:disabled {
    background-color: #111827;
    border-color: #263247;
    color: #64748b;
}
QPushButton#startButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #06b6d4, stop:0.5 #6366f1, stop:1 #a855f7);
    border: 1px solid #67e8f9;
    color: white;
    font-weight: 700;
    padding: 5px 20px;
}
QPushButton#startButton:hover {
    border-color: #f0abfc;
}
QPushButton#startButton:disabled {
    background-color: #202a3d;
    border-color: #344158;
    color: #718096;
}
QPushButton#pauseButton {
    background-color: #12324a;
    border-color: #0891b2;
    color: #a5f3fc;
}
QPushButton#cancelButton {
    background-color: #351823;
    border-color: #9f304d;
    color: #fda4af;
}
QProgressBar {
    min-height: 16px;
    max-height: 16px;
    background-color: #080d19;
    border: 1px solid #31466c;
    border-radius: 8px;
}
QProgressBar::chunk {
    border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #22d3ee, stop:0.55 #8b5cf6, stop:1 #ec4899);
}
QLabel#progressPercentLabel {
    color: #67e8f9;
    font-weight: 700;
}
QTableView#urlTable {
    background-color: #ffffff;
    alternate-background-color: #effaff;
    color: #0b1324;
    gridline-color: #c9d7e7;
    selection-background-color: #67e8f9;
    selection-color: #10112c;
    border: 1px solid #4c6c94;
    border-radius: 7px;
}
QTableView#urlTable QHeaderView::section {
    background-color: #dfeaf5;
    color: #32445f;
    border: 0;
    border-right: 1px solid #b7cadf;
    padding: 4px;
}
QTableWidget {
    background-color: #0b1222;
    alternate-background-color: #111b30;
    color: #d8e4f5;
    gridline-color: #243553;
    border: 1px solid #2f4368;
    border-radius: 7px;
    selection-background-color: #243b68;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #17233b;
    color: #93c5fd;
    border: 0;
    border-right: 1px solid #2f4368;
    border-bottom: 1px solid #2f4368;
    padding: 7px 8px;
    font-weight: 700;
}
QLabel#currentProductLabel {
    color: #a9bad3;
}
QLabel#summaryLabel {
    background-color: #0b1222;
    border: 1px solid #2b3e61;
    border-radius: 7px;
    padding: 8px 10px;
}
QLabel#summaryLabel[statusTone="success"] {
    color: #4ade80;
}
QLabel#summaryLabel[statusTone="warning"] {
    color: #fbbf24;
}
QLabel#summaryLabel[statusTone="error"] {
    color: #fb7185;
}
QLabel#summaryLabel[statusTone="cancelled"] {
    color: #94a3b8;
}
QSplitter::handle:vertical {
    height: 5px;
    background-color: #17233b;
    border-radius: 2px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background-color: #0b1222;
    border: 0;
    margin: 0;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background-color: #3a4f78;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
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
