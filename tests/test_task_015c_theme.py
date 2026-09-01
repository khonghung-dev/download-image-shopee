"""Task 015C desktop theme and live-state preservation regressions."""

from __future__ import annotations

from pathlib import Path
import re
from unittest.mock import MagicMock

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from shopee_image_downloader.core.batch_queue import QueueState
from shopee_image_downloader.core.bridge_protocol import BridgeProductData
from shopee_image_downloader.storage.settings import SettingsManager
from shopee_image_downloader.ui.main_window import MainWindow
from shopee_image_downloader.ui.theme import (
    PALETTES,
    Theme,
    ThemeManager,
    build_theme_stylesheet,
)
from shopee_image_downloader.workers.bridge_worker import ExtensionBridgeServer


def _qsettings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def _window(
    tmp_path: Path,
    theme_settings: QSettings,
) -> tuple[MainWindow, MagicMock]:
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    app_settings = SettingsManager(tmp_path / "settings.json")
    assert app_settings.set_output_folder(output)
    bridge = MagicMock(spec=ExtensionBridgeServer)
    bridge.has_connected_clients = True
    window = MainWindow(
        settings_manager=app_settings,
        bridge_server=bridge,
        start_bridge=False,
        theme_settings=theme_settings,
    )
    return window, bridge


def _product(request_id: str) -> BridgeProductData:
    return BridgeProductData(
        url="https://shopee.vn/theme-product-i.1001.2001",
        final_url="https://shopee.vn/theme-product-i.1001.2001",
        product_name="Sản phẩm kiểm thử giao diện",
        shop_id="1001",
        item_id="2001",
        images=["https://cdn.example/theme/01.jpg"],
        image_count=1,
        request_id=request_id,
    )


def test_theme_manager_defaults_persists_and_switches_both_themes(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    settings = _qsettings(tmp_path / "theme.ini")
    settings.clear()
    manager = ThemeManager(qapp, settings)

    assert manager.remembered_theme() == Theme.DARK
    assert manager.apply_remembered() == Theme.DARK
    assert manager.current_theme == Theme.DARK

    settings.setValue(ThemeManager.SETTINGS_KEY, "unsupported")
    assert manager.remembered_theme() == Theme.DARK

    assert manager.apply(Theme.LIGHT) == Theme.LIGHT
    assert manager.current_theme == Theme.LIGHT
    assert settings.value(ThemeManager.SETTINGS_KEY) == "light"

    assert manager.apply(Theme.DARK) == Theme.DARK
    assert manager.current_theme == Theme.DARK
    assert settings.value(ThemeManager.SETTINGS_KEY) == "dark"


def test_theme_qss_keeps_normal_labels_transparent_and_badge_semantic() -> None:
    for theme in Theme:
        stylesheet = build_theme_stylesheet(theme)
        label_blocks = re.findall(
            r"(?:^|\n)(QLabel[^\{]*)\{([^\}]*)\}",
            stylesheet,
        )
        assert label_blocks
        for selector, declarations in label_blocks:
            if "background" in declarations:
                assert "background-color: transparent" in declarations, selector

        assert re.search(
            r"QLabel\s*\{\s*background-color:\s*transparent;\s*border:\s*none;",
            stylesheet,
        )
        bridge_badge = re.search(
            r"QFrame#bridgeFrame\s*\{([^\}]*)\}",
            stylesheet,
        )
        assert bridge_badge is not None
        assert "background-color:" in bridge_badge.group(1)
        assert "QTableView#urlTable" in stylesheet
        assert "QTableWidget" in stylesheet
        assert "QProgressBar" in stylesheet
        assert "QCheckBox" in stylesheet

    assert PALETTES[Theme.DARK].table_background != "#ffffff"
    assert PALETTES[Theme.LIGHT].table_background == "#ffffff"


def test_main_window_restores_remembered_theme(tmp_path: Path) -> None:
    theme_path = tmp_path / "remembered-theme.ini"
    first_settings = _qsettings(theme_path)
    first_settings.clear()
    first, _ = _window(tmp_path, first_settings)

    assert first.theme_manager.current_theme == Theme.DARK
    assert first.theme_toggle_button.text() == "☀ Sáng"
    first.theme_toggle_button.click()
    assert first.theme_manager.current_theme == Theme.LIGHT
    assert first_settings.value(ThemeManager.SETTINGS_KEY) == "light"
    first.close()

    second, _ = _window(tmp_path, _qsettings(theme_path))
    assert second.theme_manager.current_theme == Theme.LIGHT
    assert second.theme_toggle_button.text() == "☾ Tối"
    second.theme_toggle_button.click()
    assert second.theme_manager.current_theme == Theme.DARK
    second.close()

    remembered = _qsettings(theme_path)
    assert remembered.value(ThemeManager.SETTINGS_KEY) == "dark"


def test_live_toggle_preserves_running_and_paused_ui_state(tmp_path: Path) -> None:
    theme_settings = _qsettings(tmp_path / "live-theme.ini")
    theme_settings.clear()
    window, _ = _window(tmp_path, theme_settings)
    window.export_metadata_checkbox.setChecked(True)
    window.export_marker_checkbox.setChecked(False)
    source_text = "https://shopee.vn/theme-product-i.1001.2001"
    window.url_input.setPlainText(source_text)
    window.start_button.click()

    assert window.queue_manager.state == QueueState.RUNNING
    current = window.queue_manager.current_item
    assert current is not None
    window.progress_bar.setValue(37)
    running_snapshot = (
        current,
        window.url_input.toPlainText(),
        window.export_metadata_checkbox.isChecked(),
        window.export_marker_checkbox.isChecked(),
        window.results_table.rowCount(),
        window.results_table.item(0, window.COL_PRODUCT).text(),
        window.progress_bar.value(),
        window.progress_percent_label.text(),
        window.bridge_frame.property("connectionState"),
    )

    window.theme_toggle_button.click()

    assert window.theme_manager.current_theme == Theme.LIGHT
    assert window.queue_manager.state == QueueState.RUNNING
    assert window.queue_manager.current_item is running_snapshot[0]
    assert window.url_input.toPlainText() == running_snapshot[1]
    assert window.export_metadata_checkbox.isChecked() is running_snapshot[2]
    assert window.export_marker_checkbox.isChecked() is running_snapshot[3]
    assert window.results_table.rowCount() == running_snapshot[4]
    assert window.results_table.item(0, window.COL_PRODUCT).text() == running_snapshot[5]
    assert window.progress_bar.value() == running_snapshot[6]
    assert window.progress_percent_label.text() == running_snapshot[7]
    assert window.bridge_frame.property("connectionState") == running_snapshot[8]

    window.pause_button.click()
    assert window.queue_manager.state == QueueState.PAUSE_REQUESTED
    window._on_bridge_product_received(_product(current.request_id))
    assert window.queue_manager.state == QueueState.PAUSED_USER
    assert window.pause_button.text() == "Tiếp tục"
    paused_snapshot = (
        window.queue_manager.current_item,
        window.url_input.toPlainText(),
        window.results_table.rowCount(),
        window.results_table.item(0, window.COL_PRODUCT).text(),
        window.progress_bar.value(),
        window.export_metadata_checkbox.isChecked(),
        window.export_marker_checkbox.isChecked(),
    )

    window.theme_toggle_button.click()

    assert window.theme_manager.current_theme == Theme.DARK
    assert window.queue_manager.state == QueueState.PAUSED_USER
    assert window.pause_button.text() == "Tiếp tục"
    assert window.queue_manager.current_item is paused_snapshot[0]
    assert window.url_input.toPlainText() == paused_snapshot[1]
    assert window.results_table.rowCount() == paused_snapshot[2]
    assert window.results_table.item(0, window.COL_PRODUCT).text() == paused_snapshot[3]
    assert window.progress_bar.value() == paused_snapshot[4]
    assert window.export_metadata_checkbox.isChecked() is paused_snapshot[5]
    assert window.export_marker_checkbox.isChecked() is paused_snapshot[6]

    window.cancel_button.click()
    assert window.queue_manager.state == QueueState.IDLE
    window.close()
