"""Application lifecycle and setup."""

import sys
from PySide6.QtWidgets import QApplication
from shopee_image_downloader import __app_name__


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create and configure the Qt application instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(__app_name__)
    return app
