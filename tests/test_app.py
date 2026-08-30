"""Tests for package metadata and main window initialization."""

import os
import pytest
from shopee_image_downloader import __version__, __app_name__
from shopee_image_downloader.app import create_application
from shopee_image_downloader.ui.main_window import MainWindow


def test_package_metadata() -> None:
    """Verify package version and app name."""
    assert __version__ == "0.1.0"
    assert __app_name__ == "Shopee Image Downloader"


def test_main_window_initialization() -> None:
    """Verify MainWindow initializes with correct title and size."""
    # Ensure headless/offscreen platform in test environment if not already set
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = create_application([])
    assert app is not None

    window = MainWindow()
    assert window.windowTitle() == "Shopee Image Downloader"
    assert window.width() == 800
    assert window.height() == 600
    window.close()
