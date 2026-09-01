"""Canonical light/dark presentation themes for the desktop application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


class Theme(str, Enum):
    """Supported desktop appearance themes."""

    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """Semantic colors used to build one complete Qt Widgets theme."""

    window_background: str
    card_background: str
    elevated_background: str
    card_border: str
    primary_text: str
    secondary_text: str
    muted_text: str
    input_background: str
    input_border: str
    input_disabled_background: str
    disabled_text: str
    table_background: str
    table_alternate_background: str
    table_header_background: str
    table_selected_background: str
    table_selected_text: str
    primary_accent: str
    secondary_accent: str
    accent_hover: str
    success: str
    warning: str
    error: str
    progress_track: str
    progress_fill_start: str
    progress_fill_middle: str
    progress_fill_end: str
    header_start: str
    header_middle: str
    header_end: str
    button_background: str
    button_hover: str
    button_pressed: str
    success_surface: str
    error_surface: str
    pause_surface: str
    scrollbar_handle: str


PALETTES: dict[Theme, ThemePalette] = {
    Theme.DARK: ThemePalette(
        window_background="#070b17",
        card_background="#10182b",
        elevated_background="#131d32",
        card_border="#2a3c62",
        primary_text="#eaf2ff",
        secondary_text="#b7c5da",
        muted_text="#8da2c3",
        input_background="#0b1222",
        input_border="#33466d",
        input_disabled_background="#0d1423",
        disabled_text="#64748b",
        table_background="#0b1425",
        table_alternate_background="#122039",
        table_header_background="#172743",
        table_selected_background="#31558d",
        table_selected_text="#ffffff",
        primary_accent="#22d3ee",
        secondary_accent="#a855f7",
        accent_hover="#67e8f9",
        success="#4ade80",
        warning="#fbbf24",
        error="#fb7185",
        progress_track="#080d19",
        progress_fill_start="#22d3ee",
        progress_fill_middle="#8b5cf6",
        progress_fill_end="#ec4899",
        header_start="#111c33",
        header_middle="#151936",
        header_end="#25133d",
        button_background="#18233b",
        button_hover="#223255",
        button_pressed="#111a2e",
        success_surface="#0d2b27",
        error_surface="#351823",
        pause_surface="#12324a",
        scrollbar_handle="#3a4f78",
    ),
    Theme.LIGHT: ThemePalette(
        window_background="#eef3f9",
        card_background="#ffffff",
        elevated_background="#f7f9fd",
        card_border="#cbd8e8",
        primary_text="#12213a",
        secondary_text="#425674",
        muted_text="#64748b",
        input_background="#ffffff",
        input_border="#aebfd4",
        input_disabled_background="#edf1f6",
        disabled_text="#8b99aa",
        table_background="#ffffff",
        table_alternate_background="#eef7ff",
        table_header_background="#dfeaf6",
        table_selected_background="#bde8f6",
        table_selected_text="#10223c",
        primary_accent="#087ea4",
        secondary_accent="#7048c7",
        accent_hover="#0b6f91",
        success="#16803c",
        warning="#a46108",
        error="#c73e57",
        progress_track="#dbe5f0",
        progress_fill_start="#06a6c9",
        progress_fill_middle="#5b67d8",
        progress_fill_end="#a146c2",
        header_start="#ffffff",
        header_middle="#f5f8fd",
        header_end="#f4effd",
        button_background="#e8eef7",
        button_hover="#dce9f6",
        button_pressed="#cbdbea",
        success_surface="#e9f8ef",
        error_surface="#fff0f2",
        pause_surface="#e5f6fb",
        scrollbar_handle="#91a7c1",
    ),
}


def parse_theme(value: object) -> Theme:
    """Return a supported theme, defaulting invalid or missing values to dark."""
    if isinstance(value, Theme):
        return value
    normalized = str(value or "").strip().lower()
    try:
        return Theme(normalized)
    except ValueError:
        return Theme.DARK


def build_theme_stylesheet(theme: Theme) -> str:
    """Build a complete application stylesheet from semantic palette roles."""
    palette = PALETTES[theme]
    return f"""
QWidget {{
    background-color: {palette.window_background};
    color: {palette.primary_text};
    font-family: "Segoe UI Variable", "Segoe UI";
    font-size: 10pt;
}}
QLabel {{
    background-color: transparent;
    border: none;
}}
QFrame#heroHeader {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {palette.header_start}, stop:0.55 {palette.header_middle},
        stop:1 {palette.header_end});
    border: 1px solid {palette.card_border};
    border-radius: 12px;
}}
QLabel[role="heroTitle"] {{
    color: {palette.primary_text};
    font-size: 17pt;
    font-weight: 700;
}}
QLabel[role="heroSubtitle"] {{
    color: {palette.muted_text};
    font-size: 9pt;
}}
QFrame[role="card"] {{
    background-color: {palette.card_background};
    border: 1px solid {palette.card_border};
    border-radius: 11px;
}}
QLabel[role="sectionTitle"] {{
    color: {palette.primary_text};
    font-weight: 700;
}}
QLabel#urlCountLabel,
QLabel#bridgeTitleLabel,
QLabel#batchProgressLabel,
QLabel#currentProductLabel {{
    color: {palette.muted_text};
}}
QFrame#bridgeFrame {{
    background-color: {palette.elevated_background};
    border: 1px solid {palette.input_border};
    border-radius: 12px;
}}
QFrame#bridgeFrame[connectionState="connected"] {{
    background-color: {palette.success_surface};
    border-color: {palette.success};
}}
QFrame#bridgeFrame[connectionState="connected"] QLabel {{
    color: {palette.success};
}}
QFrame#bridgeFrame[connectionState="lost"],
QFrame#bridgeFrame[connectionState="disconnected"] {{
    background-color: {palette.error_surface};
    border-color: {palette.error};
}}
QFrame#bridgeFrame[connectionState="lost"] QLabel,
QFrame#bridgeFrame[connectionState="disconnected"] QLabel {{
    color: {palette.error};
}}
QLineEdit {{
    min-height: 30px;
    background-color: {palette.input_background};
    color: {palette.primary_text};
    border: 1px solid {palette.input_border};
    border-radius: 7px;
    padding: 3px 9px;
    selection-background-color: {palette.table_selected_background};
    selection-color: {palette.table_selected_text};
}}
QLineEdit:focus {{
    border-color: {palette.primary_accent};
}}
QLineEdit:disabled {{
    background-color: {palette.input_disabled_background};
    color: {palette.disabled_text};
    border-color: {palette.card_border};
}}
QCheckBox {{
    background-color: transparent;
    color: {palette.secondary_text};
    spacing: 7px;
}}
QCheckBox:disabled {{
    color: {palette.disabled_text};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {palette.input_border};
    border-radius: 4px;
    background-color: {palette.input_background};
}}
QCheckBox::indicator:checked {{
    background-color: {palette.secondary_accent};
    border-color: {palette.primary_accent};
}}
QCheckBox::indicator:disabled {{
    background-color: {palette.input_disabled_background};
    border-color: {palette.card_border};
}}
QPushButton {{
    min-height: 30px;
    background-color: {palette.button_background};
    border: 1px solid {palette.input_border};
    border-radius: 7px;
    color: {palette.primary_text};
    padding: 4px 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {palette.button_hover};
    border-color: {palette.primary_accent};
}}
QPushButton:pressed {{
    background-color: {palette.button_pressed};
}}
QPushButton:disabled {{
    background-color: {palette.input_disabled_background};
    border-color: {palette.card_border};
    color: {palette.disabled_text};
}}
QPushButton#themeToggleButton {{
    min-height: 26px;
    padding: 2px 10px;
    background-color: {palette.elevated_background};
}}
QPushButton#startButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {palette.progress_fill_start},
        stop:0.5 {palette.progress_fill_middle},
        stop:1 {palette.progress_fill_end});
    border: 1px solid {palette.accent_hover};
    color: #ffffff;
    font-weight: 700;
    padding: 5px 20px;
}}
QPushButton#startButton:hover {{
    border-color: {palette.secondary_accent};
}}
QPushButton#startButton:disabled {{
    background-color: {palette.input_disabled_background};
    border-color: {palette.card_border};
    color: {palette.disabled_text};
}}
QPushButton#pauseButton {{
    background-color: {palette.pause_surface};
    border-color: {palette.primary_accent};
    color: {palette.primary_accent};
}}
QPushButton#cancelButton {{
    background-color: {palette.error_surface};
    border-color: {palette.error};
    color: {palette.error};
}}
QProgressBar {{
    min-height: 16px;
    max-height: 16px;
    background-color: {palette.progress_track};
    border: 1px solid {palette.card_border};
    border-radius: 8px;
}}
QProgressBar::chunk {{
    border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {palette.progress_fill_start},
        stop:0.55 {palette.progress_fill_middle},
        stop:1 {palette.progress_fill_end});
}}
QLabel#progressPercentLabel {{
    color: {palette.primary_accent};
    font-weight: 700;
}}
QTableView#urlTable {{
    background-color: {palette.table_background};
    alternate-background-color: {palette.table_alternate_background};
    color: {palette.primary_text};
    gridline-color: {palette.card_border};
    selection-background-color: {palette.table_selected_background};
    selection-color: {palette.table_selected_text};
    border: 1px solid {palette.input_border};
    border-radius: 7px;
}}
QTableView#urlTable:disabled {{
    color: {palette.disabled_text};
    background-color: {palette.input_disabled_background};
}}
QTableView#urlTable QHeaderView::section {{
    background-color: {palette.table_header_background};
    color: {palette.secondary_text};
    border: 0;
    border-right: 1px solid {palette.card_border};
    border-bottom: 1px solid {palette.card_border};
    padding: 4px;
}}
QTableWidget {{
    background-color: {palette.table_background};
    alternate-background-color: {palette.table_alternate_background};
    color: {palette.primary_text};
    gridline-color: {palette.card_border};
    border: 1px solid {palette.input_border};
    border-radius: 7px;
    selection-background-color: {palette.table_selected_background};
    selection-color: {palette.table_selected_text};
}}
QHeaderView::section,
QTableCornerButton::section {{
    background-color: {palette.table_header_background};
    color: {palette.secondary_text};
    border: 0;
    border-right: 1px solid {palette.card_border};
    border-bottom: 1px solid {palette.card_border};
    padding: 7px 8px;
    font-weight: 700;
}}
QLabel#summaryLabel {{
    background-color: transparent;
    border: none;
    color: {palette.secondary_text};
    padding: 6px 2px;
}}
QLabel#summaryLabel[statusTone="active"] {{ color: {palette.primary_accent}; }}
QLabel#summaryLabel[statusTone="success"] {{ color: {palette.success}; }}
QLabel#summaryLabel[statusTone="warning"] {{ color: {palette.warning}; }}
QLabel#summaryLabel[statusTone="error"] {{ color: {palette.error}; }}
QLabel#summaryLabel[statusTone="skipped"] {{ color: {palette.secondary_accent}; }}
QLabel#summaryLabel[statusTone="cancelled"] {{ color: {palette.muted_text}; }}
QSplitter::handle:vertical {{
    height: 5px;
    background-color: {palette.table_header_background};
    border-radius: 2px;
}}
QScrollBar:vertical,
QScrollBar:horizontal {{
    background-color: {palette.input_background};
    border: 0;
    margin: 0;
}}
QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {{
    background-color: {palette.scrollbar_handle};
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{
    background-color: {palette.primary_accent};
}}
QScrollBar::add-line,
QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page,
QScrollBar::sub-page {{
    background: transparent;
}}
QToolTip {{
    background-color: {palette.elevated_background};
    color: {palette.primary_text};
    border: 1px solid {palette.input_border};
    padding: 4px;
}}
"""


def build_application_palette(theme: Theme) -> QPalette:
    """Build Qt palette roles used by custom painting and native fallbacks."""
    colors = PALETTES[theme]
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors.window_background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors.primary_text))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors.input_background))
    palette.setColor(
        QPalette.ColorRole.AlternateBase,
        QColor(colors.table_alternate_background),
    )
    palette.setColor(QPalette.ColorRole.Text, QColor(colors.primary_text))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors.button_background))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors.primary_text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors.table_selected_background))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors.table_selected_text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors.muted_text))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors.elevated_background))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors.primary_text))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(colors.disabled_text),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(colors.disabled_text),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(colors.disabled_text),
    )
    return palette


class ThemeManager(QObject):
    """Apply, toggle, and persist the application appearance theme."""

    theme_changed = Signal(str)

    SETTINGS_KEY = "appearance/theme"
    ORGANIZATION = "ShopeeImageDownloader"
    APPLICATION = "ShopeeImageDownloader"

    def __init__(
        self,
        application: QApplication | None = None,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        resolved_application = application or QApplication.instance()
        if not isinstance(resolved_application, QApplication):
            raise RuntimeError("ThemeManager requires an active QApplication")
        self._application = resolved_application
        self._settings = settings or QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            self.ORGANIZATION,
            self.APPLICATION,
        )
        self._theme = Theme.DARK

    @property
    def current_theme(self) -> Theme:
        """Return the currently applied theme."""
        return self._theme

    @property
    def palette(self) -> ThemePalette:
        """Return semantic colors for the currently applied theme."""
        return PALETTES[self._theme]

    def remembered_theme(self) -> Theme:
        """Read the persisted theme without mutating application state."""
        return parse_theme(self._settings.value(self.SETTINGS_KEY, Theme.DARK.value))

    def apply_remembered(self) -> Theme:
        """Apply the remembered theme before a window is shown."""
        return self.apply(self.remembered_theme(), persist=False)

    def apply(self, theme: Theme | str, *, persist: bool = True) -> Theme:
        """Apply one supported theme immediately and optionally persist it."""
        selected = parse_theme(theme)
        self._theme = selected
        self._application.setProperty("appearanceTheme", selected.value)
        self._application.setPalette(build_application_palette(selected))
        self._application.setStyleSheet(build_theme_stylesheet(selected))
        if persist:
            self._settings.setValue(self.SETTINGS_KEY, selected.value)
            self._settings.sync()
        self.theme_changed.emit(selected.value)
        return selected

    def toggle(self) -> Theme:
        """Switch between the only two supported themes."""
        target = Theme.LIGHT if self._theme == Theme.DARK else Theme.DARK
        return self.apply(target)

    def status_color(self, tone: str) -> QColor:
        """Resolve a presentation status tone through the active palette."""
        palette = self.palette
        colors = {
            "neutral": palette.muted_text,
            "active": palette.primary_accent,
            "success": palette.success,
            "warning": palette.warning,
            "error": palette.error,
            "skipped": palette.secondary_accent,
            "cancelled": palette.muted_text,
        }
        return QColor(colors.get(tone, palette.primary_text))
