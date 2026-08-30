"""Background worker for interactive Shopee user authentication."""

import logging
from PySide6.QtCore import QObject, QThread, Signal
from shopee_image_downloader.core.browser_session import (
    STATUS_NOT_LOGGED_IN,
    STATUS_OPENING_CHROME,
    ShopeeSessionManager,
)

logger = logging.getLogger(__name__)


class AuthLoginWorker(QThread):
    """QThread worker that launches Google Chrome and monitors interactive login via CDP."""

    login_started = Signal()
    status_updated = Signal(str)
    username_detected = Signal(str)
    login_finished = Signal(bool, str)

    def __init__(
        self,
        session_manager: ShopeeSessionManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.session_manager = session_manager or ShopeeSessionManager()
        self._is_cancelled: bool = False
        self._last_status: str = STATUS_NOT_LOGGED_IN
        self._detected_username: str | None = None

    def cancel(self) -> None:
        """Cancel the login monitoring loop."""
        self._is_cancelled = True
        self.requestInterruption()

    def is_cancelled(self) -> bool:
        """Return True if cancel or thread interruption was requested."""
        return self._is_cancelled or self.isInterruptionRequested()

    def run(self) -> None:
        """Execute Chrome process launch and background session monitor."""
        self.login_started.emit()
        self.status_updated.emit(STATUS_OPENING_CHROME)
        logger.info("AuthLoginWorker: Opening dedicated Google Chrome process...")

        opened = self.session_manager.open_auth_browser()
        if not opened:
            logger.error("AuthLoginWorker: Could not launch Google Chrome.")
            self.status_updated.emit("Không thể khởi động Google Chrome. Vui lòng kiểm tra cài đặt Chrome.")
            self.login_finished.emit(False, "Không thể khởi động Google Chrome")
            return

        def on_status_change(status_text: str) -> None:
            self._last_status = status_text
            self.status_updated.emit(status_text)

        def on_username_detected(uname: str) -> None:
            self._detected_username = uname
            self.username_detected.emit(uname)

        try:
            self.session_manager.monitor_login_loop(
                on_status_change=on_status_change,
                on_username_detected=on_username_detected,
                is_cancelled=self.is_cancelled,
            )
        except Exception as e:
            logger.error("Exception during login monitoring: %s", e)
