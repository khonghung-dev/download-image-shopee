"""Main window implementation for Shopee Image Downloader."""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout


class MainWindow(QMainWindow):
    """The main application window for Shopee Image Downloader."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Shopee Image Downloader")
        self.resize(800, 600)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize blank central widget."""
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
