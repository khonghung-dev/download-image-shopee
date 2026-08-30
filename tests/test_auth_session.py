"""Unit and regression tests for Shopee authentication, verification handling, and session management."""

import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest
from shopee_image_downloader.core.browser_session import (
    AUTH_STATE_FILENAME,
    BROWSER_PROFILE_DIR_NAME,
    STATUS_CHECKING_SESSION,
    STATUS_LOGGED_IN,
    STATUS_LOGIN_REQUIRED,
    STATUS_LOGIN_VERIFY,
    STATUS_NOT_LOGGED_IN,
    STATUS_OPENING_CHROME,
    STATUS_SESSION_EXPIRED,
    STATUS_VERIFICATION_REQUIRED,
    STATUS_WAITING_FOR_LOGIN,
    ShopeeSessionManager,
    detect_shopee_username,
    extract_auth_cookie_status,
    get_chrome_executable_path,
    get_default_browser_profile_dir,
    is_unauthenticated_page,
    is_unauthenticated_url,
    is_verification_temporarily_blocked,
    is_verification_url,
)
from shopee_image_downloader.core.path_safety import (
    get_allowed_writable_roots,
    is_forbidden_chrome_profile,
    is_safe_writable_path,
    validate_safe_writable_path,
)
from shopee_image_downloader.workers.auth_worker import AuthLoginWorker


def test_get_default_browser_profile_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify application-owned ChromeUserData directory resolution outside git repository."""
    fake_localappdata = tmp_path / "AppData" / "Local"
    fake_localappdata.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))

    profile_dir = get_default_browser_profile_dir()
    assert str(fake_localappdata) in str(profile_dir)
    assert profile_dir.name == "ChromeUserData"
    assert profile_dir.is_dir()


def test_get_chrome_executable_path_candidate_found(tmp_path: Path) -> None:
    """Verify get_chrome_executable_path locates chrome.exe when present."""
    fake_chrome = tmp_path / "chrome.exe"
    fake_chrome.write_text("mock chrome executable")

    with patch("shopee_image_downloader.core.browser_session._CHROME_EXECUTABLE_CANDIDATES", (str(fake_chrome),)):
        found = get_chrome_executable_path()
        assert found == fake_chrome


def test_path_safety_allowed_roots(tmp_path: Path) -> None:
    """Verify allowed writable roots include repo, AppData, and temp dirs."""
    roots = get_allowed_writable_roots(allow_temp=True)
    assert len(roots) >= 2
    assert is_safe_writable_path(tmp_path, allow_temp=True) is True


def test_path_safety_rejects_personal_chrome_user_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Strict safety guard: Personal Chrome User Data and Profile 10 MUST be rejected."""
    fake_localappdata = tmp_path / "AppData" / "Local"
    personal_chrome_dir = fake_localappdata / "Google" / "Chrome" / "User Data"
    personal_chrome_dir.mkdir(parents=True)
    profile_10_dir = personal_chrome_dir / "Profile 10"
    profile_10_dir.mkdir(parents=True)

    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))

    assert is_forbidden_chrome_profile(personal_chrome_dir) is True
    assert is_forbidden_chrome_profile(profile_10_dir) is True
    assert is_safe_writable_path(personal_chrome_dir) is False
    assert is_safe_writable_path(profile_10_dir) is False

    with pytest.raises(PermissionError):
        validate_safe_writable_path(personal_chrome_dir)

    with pytest.raises(PermissionError):
        validate_safe_writable_path(profile_10_dir)


def test_path_safety_rejects_system_roots() -> None:
    """Strict safety guard: Root drives and system directories must never be writable targets."""
    forbidden_roots = [
        "C:\\",
        "C:/",
        "D:\\",
        "D:/",
        "C:\\Users",
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    ]
    for r in forbidden_roots:
        assert is_safe_writable_path(r) is False
        with pytest.raises(PermissionError):
            validate_safe_writable_path(r)


def test_session_manager_rejects_personal_chrome_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify ShopeeSessionManager refuses to initialize with personal Chrome User Data or Profile 10."""
    fake_localappdata = tmp_path / "AppData" / "Local"
    personal_profile = fake_localappdata / "Google" / "Chrome" / "User Data" / "Profile 10"
    personal_profile.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))

    with pytest.raises(PermissionError) as excinfo:
        ShopeeSessionManager(profile_dir=personal_profile)

    assert "personal Chrome profile" in str(excinfo.value)


def test_session_manager_rejects_unsafe_profile_dir() -> None:
    """Verify ShopeeSessionManager refuses to initialize with unsafe root system directories."""
    with pytest.raises(PermissionError):
        ShopeeSessionManager(profile_dir="C:\\Windows")


def test_open_auth_browser_launches_external_chrome_process(tmp_path: Path) -> None:
    """Verify open_auth_browser spawns chrome.exe with dedicated user-data-dir and remote-debugging-port."""
    profile_dir = tmp_path / "test_profile"
    fake_chrome = tmp_path / "chrome.exe"
    fake_chrome.write_text("mock chrome")

    manager = ShopeeSessionManager(
        profile_dir=profile_dir,
        chrome_executable=fake_chrome,
        remote_debugging_port=9222,
    )

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = None
    mock_process.pid = 12345

    with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
        opened = manager.open_auth_browser("https://shopee.vn/buyer/login")
        assert opened is True
        assert manager.is_auth_browser_open() is True

        mock_popen.assert_called_once()
        args, _ = mock_popen.call_args
        cmd = args[0]
        assert str(fake_chrome) in cmd
        assert f"--user-data-dir={profile_dir}" in cmd
        assert "--remote-debugging-port=9222" in cmd
        assert "https://shopee.vn/buyer/login" in cmd


def test_close_auth_browser_only_terminates_own_process(tmp_path: Path) -> None:
    """Verify close_auth_browser cleanly terminates only the spawned child process."""
    profile_dir = tmp_path / "test_profile"
    manager = ShopeeSessionManager(profile_dir=profile_dir)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = None
    mock_process.pid = 9999
    manager._chrome_process = mock_process

    manager.close_auth_browser()

    mock_process.terminate.assert_called_once()
    assert manager._chrome_process is None


def test_is_unauthenticated_url() -> None:
    """Verify detection of login, signup, verify, and unauthenticated URLs."""
    assert is_unauthenticated_url("https://shopee.vn/buyer/login") is True
    assert is_unauthenticated_url("https://shopee.vn/buyer/login?next=https%3A%2F%2Fshopee.vn") is True
    assert is_unauthenticated_url("https://shopee.vn/buyer/signup") is True
    assert is_unauthenticated_url("https://shopee.vn/verify/traffic/error?is_logged_in=false") is True
    assert is_unauthenticated_url("https://shopee.vn/Ao-Thun-Nam-i.111.222") is False
    assert is_unauthenticated_url("https://shopee.vn/user/account/profile") is False
    assert is_unauthenticated_url("") is False


def test_is_verification_url() -> None:
    """Verify detection of human/robot verification challenge URLs and page contents."""
    assert is_verification_url("https://shopee.vn/verify/traffic/error") is True
    assert is_verification_url("https://shopee.vn/verify/captcha") is True
    assert is_verification_url("https://shopee.vn/verify/ivs") is True
    assert is_verification_url("https://shopee.vn/verify/recaptcha") is True
    assert is_verification_url("https://shopee.vn/robot/check") is True
    assert is_verification_url("https://shopee.vn/item", "Shopee verification is required") is True
    assert is_verification_url("https://shopee.vn/item", "Vui lòng xác minh bảo mật") is True
    assert is_verification_url("https://shopee.vn/Ao-Thun-Nam-i.111.222", "<html><body>Chi tiết sản phẩm</body></html>") is False


def test_is_verification_temporarily_blocked() -> None:
    """Verify detection of temporary verification failure / rate block messages."""
    assert is_verification_temporarily_blocked("https://shopee.vn/verify/captcha", "Vui lòng thử lại sau") is True
    assert is_verification_temporarily_blocked("https://shopee.vn/verify/captcha", "Chưa thể hoàn tất xác thực lúc này") is True
    assert is_verification_temporarily_blocked("https://shopee.vn/verify/captcha", "Please try again later") is True
    assert is_verification_temporarily_blocked("https://shopee.vn/verify/traffic/error", "Quá nhiều yêu cầu") is True
    assert is_verification_temporarily_blocked("https://shopee.vn/verify/captcha", "Kéo thanh trượt để ghép hình") is False


def test_is_unauthenticated_page() -> None:
    """Verify detection of unauthenticated page contents."""
    assert is_unauthenticated_page("https://shopee.vn/buyer/login") is True
    assert is_unauthenticated_page("https://shopee.vn/item", "Vui lòng đăng nhập Shopee để tiếp tục") is True
    assert is_unauthenticated_page("https://shopee.vn/item", "Cần đăng nhập Shopee") is True
    assert is_unauthenticated_page("https://shopee.vn/item", "<html><head><title>Sản phẩm</title></head></html>") is False


def test_detect_shopee_username() -> None:
    """Verify extracting Shopee username from page evaluate script."""
    mock_page = MagicMock()
    mock_page.evaluate.return_value = "chuasudung4526\nAccount Menu"

    username = detect_shopee_username(mock_page)
    assert username == "chuasudung4526"

    mock_page.evaluate.return_value = "Đăng nhập"
    assert detect_shopee_username(mock_page) is None

    mock_page.evaluate.return_value = None
    assert detect_shopee_username(mock_page) is None


def test_extract_auth_cookie_status_guest_cookies_only() -> None:
    """Verify anonymous tracking/guest cookies (SPC_T_ID, SPC_T_IV, etc.) do NOT count as authenticated."""
    guest_cookies = [
        {"name": "SPC_T_ID", "value": "t_id_guest_123456", "expires": time.time() + 86400},
        {"name": "SPC_T_IV", "value": "t_iv_guest_123456", "expires": time.time() + 86400},
        {"name": "SPC_R_T_ID", "value": "r_t_id_guest_123456", "expires": time.time() + 86400},
        {"name": "SPC_F", "value": "f_guest_123456", "expires": time.time() + 86400},
        {"name": "SPC_SI", "value": "si_guest_123456", "expires": time.time() + 86400},
        {"name": "SPC_U", "value": "-", "expires": time.time() + 86400},
    ]
    has_auth, is_expired = extract_auth_cookie_status(guest_cookies)
    assert has_auth is False
    assert is_expired is False


def test_extract_auth_cookie_status_valid_spc_ec() -> None:
    """Verify genuine SPC_EC token counts as authenticated."""
    auth_cookies = [
        {"name": "SPC_EC", "value": "valid_ec_encrypted_session_token_123", "expires": time.time() + 86400},
        {"name": "SPC_T_ID", "value": "t_id_123", "expires": time.time() + 86400},
    ]
    has_auth, is_expired = extract_auth_cookie_status(auth_cookies)
    assert has_auth is True
    assert is_expired is False


def test_extract_auth_cookie_status_valid_spc_u_numeric() -> None:
    """Verify genuine numeric SPC_U user ID counts as authenticated."""
    auth_cookies = [
        {"name": "SPC_U", "value": "12345678", "expires": time.time() + 86400},
        {"name": "SPC_ST", "value": "valid_st_session_token_456", "expires": time.time() + 86400},
    ]
    has_auth, is_expired = extract_auth_cookie_status(auth_cookies)
    assert has_auth is True
    assert is_expired is False


def test_session_manager_initial_state_not_logged_in(tmp_path: Path) -> None:
    """Verify initial session status is Chưa đăng nhập when profile is empty."""
    profile_dir = tmp_path / "test_profile"
    manager = ShopeeSessionManager(profile_dir=profile_dir)

    assert manager.get_session_status() == STATUS_NOT_LOGGED_IN
    assert manager.is_logged_in() is False
    assert manager.get_authenticated_username() is None


def test_session_manager_saved_username_without_auth_cookies_is_not_logged_in(tmp_path: Path) -> None:
    """Requirement: A previously saved username alone must NEVER be treated as proof of valid session."""
    profile_dir = tmp_path / "test_profile"
    profile_dir.mkdir(parents=True)
    auth_file = profile_dir / AUTH_STATE_FILENAME

    data = {
        "username": "chuasudung4526",
        "cookies": [
            {"name": "SPC_T_ID", "value": "guest_123", "expires": time.time() + 86400}
        ]
    }
    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    manager = ShopeeSessionManager(profile_dir=profile_dir)
    assert manager.get_session_status() == STATUS_NOT_LOGGED_IN
    assert manager.is_logged_in() is False
    assert manager.get_authenticated_username() is None


def test_session_manager_with_valid_auth_state_and_username(tmp_path: Path) -> None:
    """Verify session status is Đã đăng nhập and username is restored when genuine auth cookies exist."""
    profile_dir = tmp_path / "test_profile"
    profile_dir.mkdir(parents=True)
    auth_file = profile_dir / AUTH_STATE_FILENAME

    valid_auth_data = {
        "username": "chuasudung4526",
        "cookies": [
            {
                "name": "SPC_EC",
                "value": "fake_ec_token_12345",
                "domain": ".shopee.vn",
                "path": "/",
                "expires": time.time() + 86400,
            },
            {
                "name": "SPC_U",
                "value": "999999",
                "domain": ".shopee.vn",
                "path": "/",
                "expires": time.time() + 86400,
            },
        ],
    }
    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(valid_auth_data, f)

    manager = ShopeeSessionManager(profile_dir=profile_dir)
    assert manager.get_session_status() == STATUS_LOGGED_IN
    assert manager.is_logged_in() is True
    assert manager.get_authenticated_username() == "chuasudung4526"


def test_session_manager_with_expired_auth_state(tmp_path: Path) -> None:
    """Verify session status is Phiên không hợp lệ when auth cookies are expired."""
    profile_dir = tmp_path / "test_profile"
    profile_dir.mkdir(parents=True)
    auth_file = profile_dir / AUTH_STATE_FILENAME

    expired_auth_data = {
        "cookies": [
            {
                "name": "SPC_EC",
                "value": "expired_token_12345",
                "domain": ".shopee.vn",
                "path": "/",
                "expires": time.time() - 3600,  # 1 hour in the past
            }
        ]
    }
    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(expired_auth_data, f)

    manager = ShopeeSessionManager(profile_dir=profile_dir)
    assert manager.get_session_status() == STATUS_SESSION_EXPIRED
    assert manager.is_logged_in() is False


def test_validate_and_finalize_session_success(tmp_path: Path) -> None:
    """Verify validate_and_finalize_session extracts valid cookies, saves state, and closes Chrome."""
    profile_dir = tmp_path / "test_profile"
    manager = ShopeeSessionManager(profile_dir=profile_dir)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = None
    manager._chrome_process = mock_process

    mock_page = MagicMock()
    mock_page.evaluate.return_value = "chuasudung4526"

    mock_context = MagicMock()
    mock_context.pages = [mock_page]
    mock_context.cookies.return_value = [
        {"name": "SPC_EC", "value": "valid_ec_token_123", "expires": time.time() + 86400},
        {"name": "SPC_U", "value": "888888", "expires": time.time() + 86400},
    ]

    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    with patch.object(manager, "connect_cdp", return_value=mock_browser):
        success, username, message = manager.validate_and_finalize_session()

    assert success is True
    assert username == "chuasudung4526"
    assert "thành công" in message
    assert manager.is_logged_in() is True
    assert manager.auth_state_file.exists() is True
    assert mock_process.terminate.called is True


def test_validate_and_finalize_session_without_cookies_keeps_browser_open(tmp_path: Path) -> None:
    """Verify validate_and_finalize_session fails safely and keeps browser open when unauthenticated."""
    profile_dir = tmp_path / "test_profile"
    manager = ShopeeSessionManager(profile_dir=profile_dir)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = None
    manager._chrome_process = mock_process

    mock_context = MagicMock()
    mock_context.pages = []
    mock_context.cookies.return_value = [
        {"name": "SPC_T_ID", "value": "guest_123", "expires": time.time() + 86400}
    ]

    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    with patch.object(manager, "connect_cdp", return_value=mock_browser):
        success, username, message = manager.validate_and_finalize_session()

    assert success is False
    assert "Chưa hoàn tất đăng nhập" in message
    # Must NOT terminate Chrome process
    assert mock_process.terminate.called is False
    assert manager.is_logged_in() is False


def test_monitor_login_loop_verification_retains_browser(tmp_path: Path) -> None:
    """Verify monitor_login_loop detects verification challenges and NEVER terminates Chrome."""
    profile_dir = tmp_path / "test_profile"
    manager = ShopeeSessionManager(profile_dir=profile_dir)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = None
    manager._chrome_process = mock_process

    mock_page = MagicMock()
    mock_page.url = "https://shopee.vn/verify/captcha"
    mock_page.inner_text.return_value = "Vui lòng thử lại sau"
    mock_page.evaluate.return_value = None

    mock_context = MagicMock()
    mock_context.pages = [mock_page]

    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    status_updates = []
    iterations = 0

    def mock_is_cancelled() -> bool:
        nonlocal iterations
        iterations += 1
        return iterations >= 2

    with patch.object(manager, "connect_cdp", return_value=mock_browser):
        with patch("time.sleep", return_value=None):
            manager.monitor_login_loop(
                on_status_change=lambda s: status_updates.append(s),
                is_cancelled=mock_is_cancelled,
            )

    assert STATUS_LOGIN_VERIFY in status_updates
    # Process must not have been terminated
    assert mock_process.terminate.called is False


def test_session_manager_logout_clears_profile_and_state(tmp_path: Path) -> None:
    """Verify logout cleanly removes session file and profile contents safely."""
    profile_dir = tmp_path / "test_profile"
    profile_dir.mkdir(parents=True)
    auth_file = profile_dir / AUTH_STATE_FILENAME
    auth_file.write_text('{"username": "user1", "cookies": [{"name": "SPC_EC", "value": "valid_token_xyz", "expires": 9999999999}]}', encoding="utf-8")

    sub_dir = profile_dir / "Default" / "Network"
    sub_dir.mkdir(parents=True)
    (sub_dir / "Cookies").write_text("mock binary cookies", encoding="utf-8")

    manager = ShopeeSessionManager(profile_dir=profile_dir)
    assert manager.is_logged_in() is True

    result = manager.logout()
    assert result is True
    assert auth_file.exists() is False
    assert manager.get_session_status() == STATUS_NOT_LOGGED_IN
    assert manager.is_logged_in() is False
    assert manager.get_authenticated_username() is None


def test_auth_login_worker_launches_browser_and_monitors(tmp_path: Path) -> None:
    """Verify AuthLoginWorker opens Chrome process and runs monitoring loop."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from shopee_image_downloader.app import create_application

    app = create_application([])
    assert app is not None

    profile_dir = tmp_path / "test_profile"
    manager = ShopeeSessionManager(profile_dir=profile_dir)

    with patch.object(manager, "open_auth_browser", return_value=True) as mock_open:
        with patch.object(manager, "monitor_login_loop") as mock_monitor:
            worker = AuthLoginWorker(session_manager=manager)

            status_events = []
            worker.status_updated.connect(lambda s: status_events.append(s))

            worker.start()
            worker.wait(3000)
            app.processEvents()

            mock_open.assert_called_once()
            mock_monitor.assert_called_once()
            assert STATUS_OPENING_CHROME in status_events
