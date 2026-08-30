"""Entry point for Shopee Image Downloader."""

import sys
from shopee_image_downloader.app import create_application
from shopee_image_downloader.ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    """Launch the Shopee Image Downloader desktop application."""
    app = create_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
