"""Shopee authentication and persistent browser session manager.

Manages a dedicated persistent Google Chrome profile stored in application-local AppData
(%LOCALAPPDATA%\\ShopeeImageDownloader\\ChromeUserData).

Launches Google Chrome as a normal external process with a remote debugging endpoint,
keeps the browser open under manual user control without automated interference,
handles verification challenges without premature closure, and finalizes authentication
upon explicit user confirmation via 'Hoàn tất đăng nhập'.
"""

from collections.abc import Callable
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.parse import parse_qsl, urlsplit

from shopee_image_downloader.core.path_safety import (
    is_forbidden_chrome_profile,
    validate_safe_writable_path,
)
from shopee_image_downloader.core.url_resolver import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

APP_DIR_NAME: str = "ShopeeImageDownloader"
BROWSER_PROFILE_DIR_NAME: str = "ChromeUserData"
AUTH_STATE_FILENAME: str = "auth_state.json"
DEFAULT_REMOTE_DEBUGGING_PORT: int = 9222

# UI and Session Status Constants
STATUS_NOT_LOGGED_IN: str = "Chưa đăng nhập"
STATUS_OPENING_CHROME: str = "Đang mở Chrome..."
STATUS_WAITING_FOR_LOGIN: str = "Đang chờ người dùng đăng nhập..."
STATUS_VERIFICATION_REQUIRED: str = "Shopee đang yêu cầu xác minh"
STATUS_CHECKING_SESSION: str = "Đang kiểm tra phiên Shopee..."
STATUS_LOGGED_IN: str = "Đã đăng nhập"
STATUS_SESSION_EXPIRED: str = "Phiên không hợp lệ"
STATUS_LOGIN_REQUIRED: str = "Cần đăng nhập Shopee"
STATUS_LOGIN_GRACE: str = "Đã phát hiện tài khoản - vui lòng kiểm tra và nhấn 'Hoàn tất đăng nhập'"
STATUS_LOGIN_VERIFY: str = "Shopee đang yêu cầu xác minh. Trình duyệt sẽ được giữ mở."
STATUS_LOGIN_VERIFY_TEMP_FAIL: str = "Shopee đang yêu cầu xác minh. Trình duyệt sẽ được giữ mở."
STATUS_LOGIN_TIMEOUT: str = "Đăng nhập Shopee hết thời gian - vui lòng thử lại"

# State Machine Constants
LOGIN_STATE_WAITING: str = "WAITING_FOR_LOGIN"
LOGIN_STATE_DETECTED: str = "LOGIN_DETECTED"
LOGIN_STATE_GRACE: str = "POST_LOGIN_GRACE"
LOGIN_STATE_VERIFICATION: str = "WAITING_FOR_VERIFICATION"
LOGIN_STATE_AUTHENTICATED: str = "AUTHENTICATED"

DEFAULT_LOGIN_TIMEOUT: float = 300.0  # 5 minutes maximum for manual login flow
DEFAULT_GRACE_DURATION: float = 30.0

# Standard candidate paths for installed Google Chrome executable on Windows
_CHROME_EXECUTABLE_CANDIDATES: tuple[str, ...] = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

# Known genuine user authentication cookie names used by Shopee
_AUTH_COOKIE_NAMES: frozenset[str] = frozenset(
    {"shopee_token", "SPC_EC", "SPC_ST"}
)


def get_default_browser_profile_dir() -> Path:
    """Return the default path to the persistent application-owned Chrome profile directory outside git repo."""
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        base_dir = Path(os.getenv("LOCALAPPDATA", "")) / APP_DIR_NAME
    else:
        base_dir = Path.home() / f".{APP_DIR_NAME.lower()}"
    profile_dir = base_dir / BROWSER_PROFILE_DIR_NAME
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_chrome_executable_path() -> Path | None:
    """Locate the installed real Google Chrome executable on the system."""
    for cand in _CHROME_EXECUTABLE_CANDIDATES:
        p = Path(cand)
        if p.is_file():
            return p

    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        local_chrome = Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if local_chrome.is_file():
            return local_chrome

    return None


def is_port_in_use(port: int) -> bool:
    """Check whether a local TCP port is already open/in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def extract_auth_cookie_status(cookies: list[dict]) -> tuple[bool, bool]:
    """Check a list of cookies for valid, non-expired Shopee user authentication.

    Returns:
        tuple[bool, bool]: (has_valid_auth, is_expired)
    """
    has_auth = False
    is_expired = False
    current_time = time.time()

    for c in cookies:
        name = c.get("name", "")
        value = str(c.get("value", "")).strip()
        if not value or value in {"-", "0", "null", "undefined"}:
            continue

        is_auth_cookie = False
        if name in _AUTH_COOKIE_NAMES and len(value) > 5:
            is_auth_cookie = True
        elif name == "SPC_U" and value.isdigit() and int(value) > 0:
            is_auth_cookie = True

        if is_auth_cookie:
            expires = c.get("expires", -1)
            if 0 < expires < current_time:
                is_expired = True
            else:
                has_auth = True

    if has_auth:
        return True, False
    elif is_expired:
        return False, True
    return False, False


def is_unauthenticated_url(url: str) -> bool:
    """Check if a URL destination indicates that the user is not authenticated or is in login flow."""
    if not url:
        return False
    try:
        parts = urlsplit(url)
        query_dict = dict(parse_qsl(parts.query, keep_blank_values=True))
        if query_dict.get("is_logged_in", "").lower() == "false":
            return True
        path_lower = parts.path.lower()
        if path_lower.startswith(("/buyer/login", "/buyer/signup", "/buyer/reset")):
            return True
    except Exception:
        pass
    return False


def is_verification_url(url: str, content: str = "") -> bool:
    """Check if URL or page content indicates a human verification / captcha challenge page."""
    if not url:
        return False
    url_lower = url.lower()
    if (
        "/verify" in url_lower
        or "/robot" in url_lower
        or "/traffic/error" in url_lower
        or "captcha" in url_lower
    ):
        return True
    if content:
        c_lower = content.lower()
        if any(
            marker in c_lower
            for marker in (
                "shopee verification",
                "vui lòng xác minh",
                "robot check",
                "security check",
                "captcha",
            )
        ):
            return True
    return False


def is_verification_temporarily_blocked(url: str = "", content: str = "") -> bool:
    """Check if Shopee displays a temporary block or failure to verify."""
    combined = f"{url} {content}".lower()
    markers = (
        "vui lòng thử lại sau",
        "chưa thể hoàn tất xác thực lúc này",
        "chua the hoan tat xac thuc luc nay",
        "try again later",
        "quá nhiều yêu cầu",
        "too many requests",
        "verification temporarily unavailable",
    )
    return any(marker in combined for marker in markers)


def is_unauthenticated_page(url: str, content: str = "") -> bool:
    """Check if either the URL or page content indicates an unauthenticated session."""
    if is_unauthenticated_url(url):
        return True
    if content:
        content_lower = content.lower()
        if "is_logged_in=false" in content_lower:
            return True
        if "cần đăng nhập" in content_lower and "shopee" in content_lower:
            return True
        if "vui lòng đăng nhập" in content_lower and "shopee" in content_lower:
            return True
    return False


def detect_shopee_username(page) -> str | None:
    """Extract visible Shopee account username from page DOM or JavaScript state."""
    if page is None:
        return None
    try:
        js_script = """() => {
            try {
                // If login link is still clearly shown in header, not logged in
                const loginLink = document.querySelector('a[href*="/buyer/login"]');

                // Try specific username selectors
                const selectors = [
                    '.navbar__username',
                    'span.navbar__username',
                    'div.navbar__username',
                    '[class*="navbar__username"]',
                    '[class*="account-dropdown"] [class*="username"]',
                    'div[class*="navbar__link--account"] span',
                    'div[class*="navbar__link--account"] div',
                    'a[href*="/user/account"]',
                    'a[href*="/user/purchase"]'
                ];
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el) {
                        const txt = (el.innerText || el.textContent || '').trim();
                        if (txt && txt.length > 0 && !txt.includes('Đăng Nhập') && !txt.includes('Đăng Ký') && !txt.includes('Login') && !txt.includes('Sign Up')) {
                            return txt;
                        }
                    }
                }

                // Check localStorage or window state
                const lsUser = localStorage.getItem('username') || localStorage.getItem('user_name');
                if (lsUser && lsUser.trim().length > 0 && lsUser !== 'null' && lsUser !== 'undefined') {
                    return lsUser.trim();
                }

                return null;
            } catch(e) {
                return null;
            }
        }"""
        username = page.evaluate(js_script)
        if username and isinstance(username, str) and username.strip():
            cleaned = username.strip().splitlines()[0].strip()
            if cleaned and cleaned not in {"Đăng nhập", "Đăng ký", "Login", "Sign up"}:
                return cleaned
    except Exception as e:
        logger.debug("Error detecting username from DOM: %s", e)

    return None


class ShopeeSessionManager:
    """Manages persistent Google Chrome browser sessions, external processes, auth state, and manual login."""

    def __init__(
        self,
        profile_dir: Path | str | None = None,
        user_agent: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        chrome_executable: Path | str | None = None,
        remote_debugging_port: int = DEFAULT_REMOTE_DEBUGGING_PORT,
    ) -> None:
        target_dir = Path(profile_dir) if profile_dir else get_default_browser_profile_dir()

        # Strict safety guard: reject personal Chrome User Data and Profile 10
        if is_forbidden_chrome_profile(target_dir):
            raise PermissionError(
                f"Cannot use personal Chrome profile as automation directory: {target_dir}"
            )

        validate_safe_writable_path(target_dir)

        self.profile_dir = target_dir
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.chrome_executable = Path(chrome_executable) if chrome_executable else get_chrome_executable_path()
        self.remote_debugging_port = remote_debugging_port

        self._chrome_process: subprocess.Popen | None = None
        self._playwright = None
        self._context = None
        self._cdp_browser = None
        self._authenticated_username: str | None = None

    @property
    def auth_state_file(self) -> Path:
        """Return path to the session auth state file."""
        return self.profile_dir / AUTH_STATE_FILENAME

    def is_auth_browser_open(self) -> bool:
        """Check whether the tool-owned Google Chrome process is currently running."""
        if self._chrome_process is None:
            return False
        return self._chrome_process.poll() is None

    def start_context(self, headless: bool = False):
        """Start and return persistent Playwright context for product extraction and automation."""
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("Playwright is not installed.")
            return None

        if self._context is not None:
            return self._context

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        validate_safe_writable_path(self.profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs: dict = {
            "user_data_dir": str(self.profile_dir),
            "headless": headless,
            "user_agent": self.user_agent,
            "locale": "vi-VN",
            "viewport": {"width": 1280, "height": 800},
            "channel": "chrome",
        }
        if self.chrome_executable and self.chrome_executable.is_file():
            launch_kwargs["executable_path"] = str(self.chrome_executable)

        try:
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            return self._context
        except Exception as e:
            logger.warning("Persistent context launch attempt failed (%s), fallback...", e)
            if "channel" in launch_kwargs:
                del launch_kwargs["channel"]
            try:
                self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
                return self._context
            except Exception as ex2:
                logger.error("Failed to launch persistent context: %s", ex2)
                return None

    def wait_for_manual_login(
        self,
        page,
        login_url: str = "https://shopee.vn/buyer/login",
        on_status_change: Callable[[str], None] | None = None,
        timeout: float = DEFAULT_LOGIN_TIMEOUT,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> bool:
        """Keep the browser open and wait for manual user login (backward compatibility)."""
        if on_status_change:
            on_status_change(STATUS_LOGIN_REQUIRED)
        start_t = time.time()
        while time.time() - start_t < timeout:
            if is_cancelled and is_cancelled():
                return False
            if self.is_logged_in() or (page and detect_shopee_username(page)):
                return True
            time.sleep(1.0)
        return False

    def get_session_status(self) -> str:
        """Check whether the persistent profile contains a confirmed valid Shopee session.

        Note: A saved username alone is NEVER treated as proof that the session is valid.
        The actual auth cookies must be confirmed.
        """
        auth_file = self.auth_state_file
        if not auth_file.is_file():
            return STATUS_NOT_LOGGED_IN

        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cookies = data.get("cookies", [])
            has_auth, is_expired = extract_auth_cookie_status(cookies)

            if has_auth:
                return STATUS_LOGGED_IN
            elif is_expired:
                return STATUS_SESSION_EXPIRED
            else:
                return STATUS_NOT_LOGGED_IN
        except Exception as e:
            logger.debug("Error checking auth state file: %s", e)
            return STATUS_NOT_LOGGED_IN

    def get_authenticated_username(self) -> str | None:
        """Return persisted username if session is authenticated."""
        if not self.is_logged_in():
            return None
        if self._authenticated_username:
            return self._authenticated_username
        auth_file = self.auth_state_file
        if not auth_file.is_file():
            return None
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._authenticated_username = data.get("username")
            return self._authenticated_username
        except Exception:
            return None

    def is_logged_in(self) -> bool:
        """Return True if session status is currently confirmed as authenticated."""
        return self.get_session_status() == STATUS_LOGGED_IN

    def open_auth_browser(self, url: str = "https://shopee.vn/buyer/login") -> bool:
        """Launch the installed Google Chrome executable as a normal external process.

        Uses ONLY the dedicated application-owned ChromeUserData profile and a remote debugging port.
        Does NOT inject anti-detection flags or automation hooks that interfere with human login.
        """
        validate_safe_writable_path(self.profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        if self.is_auth_browser_open():
            logger.info("Authentication Chrome process is already running (PID %s).", self._chrome_process.pid)
            return True

        if not self.chrome_executable or not self.chrome_executable.is_file():
            logger.error("Installed Google Chrome executable not found at: %s", self.chrome_executable)
            return False

        logger.info("Chrome executable selected: %s", self.chrome_executable)
        logger.info("Dedicated Chrome profile opened: %s", self.profile_dir)

        args = [
            str(self.chrome_executable),
            f"--user-data-dir={self.profile_dir}",
            f"--remote-debugging-port={self.remote_debugging_port}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ]

        try:
            logger.info("Spawning dedicated Google Chrome process...")
            self._chrome_process = subprocess.Popen(args)
            logger.info("Dedicated Chrome process started with PID: %s", self._chrome_process.pid)
            return True
        except Exception as e:
            logger.error("Failed to launch Google Chrome process: %s", e)
            self._chrome_process = None
            return False

    def close_auth_browser(self) -> None:
        """Close only the tool-owned Google Chrome process cleanly without touching any other Chrome instances."""
        self._disconnect_cdp()

        if self._chrome_process is not None:
            pid = getattr(self._chrome_process, "pid", "unknown")
            logger.info("Terminating application-owned Chrome process (PID %s)...", pid)
            try:
                if self._chrome_process.poll() is None:
                    self._chrome_process.terminate()
                    try:
                        self._chrome_process.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        logger.warning("Chrome process PID %s did not terminate in time, killing...", pid)
                        self._chrome_process.kill()
                        self._chrome_process.wait(timeout=2.0)
            except Exception as e:
                logger.debug("Note terminating Chrome PID %s: %s", pid, e)
            finally:
                self._chrome_process = None

    def _disconnect_cdp(self) -> None:
        """Cleanly disconnect active CDP connection without closing external browser windows."""
        if self._cdp_browser is not None:
            try:
                self._cdp_browser.close()
            except Exception as e:
                logger.debug("Error disconnecting CDP browser: %s", e)
            finally:
                self._cdp_browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.debug("Error stopping Playwright instance: %s", e)
            finally:
                self._playwright = None

    def connect_cdp(self, timeout: float = 5.0):
        """Connect to the running dedicated Chrome process over CDP."""
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("Playwright is not available for CDP connection.")
            return None

        if self._cdp_browser is not None:
            try:
                if self._cdp_browser.is_connected():
                    return self._cdp_browser
            except Exception:
                pass

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        endpoint = f"http://127.0.0.1:{self.remote_debugging_port}"
        start_t = time.time()

        while time.time() - start_t < timeout:
            try:
                self._cdp_browser = self._playwright.chromium.connect_over_cdp(endpoint)
                return self._cdp_browser
            except Exception:
                time.sleep(0.5)

        logger.debug("Could not connect to CDP endpoint: %s", endpoint)
        return None

    def monitor_login_loop(
        self,
        on_status_change: Callable[[str], None] | None = None,
        on_username_detected: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Monitor running Chrome session in background to detect username and verification prompts.

        CRITICAL: Never closes or restarts Chrome on verification challenges or temporary blocks.
        """
        logger.info("Starting login session monitor...")
        if on_status_change:
            on_status_change(STATUS_WAITING_FOR_LOGIN)

        detected_uname: str | None = None
        poll_interval = 1.0

        while True:
            if is_cancelled and is_cancelled():
                logger.info("Login monitoring cancelled.")
                break

            if not self.is_auth_browser_open():
                logger.info("Chrome process closed.")
                break

            browser = self.connect_cdp(timeout=1.0)
            if browser is not None:
                try:
                    contexts = browser.contexts
                    context = contexts[0] if contexts else None
                    if context:
                        pages = context.pages
                        active_page = pages[0] if pages else None

                        if active_page:
                            url = active_page.url or ""
                            logger.info("Current Shopee URL: %s", url)

                            # Diagnostic checks
                            is_verify = is_verification_url(url)
                            page_text = ""
                            try:
                                page_text = active_page.inner_text("body") or ""
                            except Exception:
                                pass

                            is_temp_blocked = is_verification_temporarily_blocked(url, page_text)

                            if is_verify or is_temp_blocked:
                                logger.info("Shopee verification requested (%s). Keeping Chrome open.", url)
                                if on_status_change:
                                    on_status_change(STATUS_LOGIN_VERIFY)

                            # Username detection
                            uname = detect_shopee_username(active_page)
                            if uname and uname != detected_uname:
                                detected_uname = uname
                                self._authenticated_username = detected_uname
                                logger.info("Detected Shopee username: %s", detected_uname)
                                if on_username_detected:
                                    on_username_detected(detected_uname)
                                if on_status_change:
                                    on_status_change(f"Đã phát hiện: {detected_uname} - nhấn 'Hoàn tất đăng nhập'")
                except Exception as e:
                    logger.debug("CDP monitor iteration note: %s", e)

            time.sleep(poll_interval)

    def validate_and_finalize_session(self) -> tuple[bool, str, str]:
        """Validate actual Shopee session upon user clicking 'Hoàn tất đăng nhập'.

        Extracts cookies via CDP or persistent storage, verifies authentication status,
        persists auth state, and closes tool-owned Chrome only on success.

        Returns:
            tuple[bool, str, str]: (is_success, username_or_status, message)
        """
        logger.info("User requested session finalization ('Hoàn tất đăng nhập')...")

        # 1. Try extracting cookies from active CDP connection
        cookies = []
        browser = self.connect_cdp(timeout=2.0)
        detected_uname: str | None = self._authenticated_username

        if browser is not None:
            try:
                contexts = browser.contexts
                if contexts:
                    ctx = contexts[0]
                    cookies = ctx.cookies()
                    if not detected_uname and ctx.pages:
                        detected_uname = detect_shopee_username(ctx.pages[0])
            except Exception as e:
                logger.debug("Error getting cookies over CDP: %s", e)

        # 2. Check auth cookies status
        has_auth, is_expired = extract_auth_cookie_status(cookies)

        # Fallback to checking disk auth file if cookies not retrieved over CDP
        if not has_auth and self.auth_state_file.exists():
            try:
                with open(self.auth_state_file, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                has_auth, is_expired = extract_auth_cookie_status(disk_data.get("cookies", []))
                if not detected_uname:
                    detected_uname = disk_data.get("username")
            except Exception:
                pass

        if has_auth:
            final_username = detected_uname or "Đã đăng nhập"
            self._authenticated_username = final_username

            # Save state
            try:
                validate_safe_writable_path(self.profile_dir)
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                save_data = {
                    "username": final_username,
                    "cookies": cookies,
                    "saved_at": time.time(),
                }
                with open(self.auth_state_file, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, indent=2)
                logger.info("Saved verified auth state to: %s (username: %s)", self.auth_state_file, final_username)
            except Exception as e:
                logger.error("Error saving verified auth state: %s", e)

            # Cleanly close only the tool-owned Chrome process
            self.close_auth_browser()
            logger.info("Authentication finalized successfully.")
            return True, final_username, "Đã đăng nhập Shopee thành công"

        elif is_expired:
            logger.warning("Authentication failed: Session cookies are expired.")
            return False, "", "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại trên trình duyệt."

        else:
            logger.warning("Authentication failed: No valid Shopee auth cookies detected.")
            return False, "", "Chưa hoàn tất đăng nhập Shopee (thiếu cookie xác thực). Vui lòng hoàn tất trên trình duyệt rồi nhấn 'Hoàn tất đăng nhập'."

    def logout(self) -> bool:
        """Safely clear the application's Shopee authenticated session and profile data."""
        validate_safe_writable_path(self.profile_dir)
        logger.info("Logging out and clearing application persistent profile: %s", self.profile_dir)
        self._authenticated_username = None
        self.close_auth_browser()

        if self.profile_dir.exists():
            try:
                # Delete auth state file
                if self.auth_state_file.exists():
                    self.auth_state_file.unlink()

                # Remove persistent profile directory contents safely
                for item in self.profile_dir.iterdir():
                    try:
                        validate_safe_writable_path(item)
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                    except Exception as e:
                        logger.debug("Note deleting profile item %s: %s", item, e)
                return True
            except Exception as e:
                logger.error("Error clearing persistent profile: %s", e)
                return False
        return True

    def close(self) -> None:
        """Backward-compatible helper to close tool-owned Chrome process and CDP."""
        self.close_auth_browser()


# Alias for backward compatibility
PlaywrightSessionManager = ShopeeSessionManager
