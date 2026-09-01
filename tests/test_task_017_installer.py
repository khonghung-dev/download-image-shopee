"""Static safety gates for the Task 017 Inno Setup definition."""

from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGING = REPO_ROOT / "packaging"
INSTALLER = PACKAGING / "ShopeeImageDownloader.iss"
INSTALLER_README = PACKAGING / "README_INSTALLER.txt"
BUILD_SCRIPT = PACKAGING / "build_windows_installer.ps1"
APP_ID = "119CCD27-4A4F-4083-B6C1-ABAA41D31978"
EXTENSION_ID = "bhbnfalghoklngoohdpnjedcdcplbjhm"
HISTORICAL_EXTENSION_ID = "kjkgdknadhnpigglcpjbgkkbcngclhgf"
HOST_NAME = "com.shopee_image_downloader.bridge"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_installer_has_fixed_identity_version_and_per_user_defaults() -> None:
    installer = _read(INSTALLER)
    build_script = _read(BUILD_SCRIPT)
    project = tomllib.loads(_read(REPO_ROOT / "pyproject.toml"))
    version = project["project"]["version"]

    assert installer.count("AppId=") == 1
    assert f"AppId={{{{{APP_ID}}}" in installer
    assert f'#define MyAppVersion "{version}"' in installer
    assert "AppVersion={#MyAppVersion}" in installer
    assert "PrivilegesRequired=lowest" in installer
    assert (
        "DefaultDirName={localappdata}\\Programs\\ShopeeImageDownloader"
        in installer
    )
    assert "OutputDir=..\\release\\installer" in installer
    assert "ShopeeImageDownloader-Setup-{#MyAppVersion}" in installer
    assert "PrivilegesRequiredOverridesAllowed" not in installer
    assert "CloseApplications=yes" in installer
    assert "CloseApplications=force" not in installer
    assert (
        "$env:LOCALAPPDATA\\Programs\\Inno Setup 6\\ISCC.exe"
        in build_script
    )


def test_installer_uses_proven_payload_and_generates_path_specific_manifest() -> None:
    installer = _read(INSTALLER)
    build_script = _read(BUILD_SCRIPT)

    assert '..\\release\\ShopeeImageDownloader-Windows\\*' in installer
    assert "recursesubdirs" in installer
    assert f"native_host\\{{#MyHostName}}.json" in installer
    assert "README_INSTALLER.txt" in installer
    assert "install_native_host.ps1" in installer
    assert "uninstall_native_host.ps1" in installer
    assert "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File" in installer
    assert "CurUninstallStepChanged" in installer
    assert "ResultCode <> 0" in installer
    assert installer.count("RaiseException(") == 2

    for required in (
        "ShopeeImageDownloader.exe",
        "_internal",
        "native_host\\shopee_native_host.exe",
        "chrome_extension\\manifest.json",
        "install_native_host.ps1",
        "uninstall_native_host.ps1",
        "README_FIRST.txt",
    ):
        assert f'"{required}"' in build_script
    assert f'ExpectedExtensionId = "{EXTENSION_ID}"' in build_script
    assert "INNO_SETUP_COMPILER_MISSING" in build_script


def test_installer_does_not_automate_chrome_or_request_machine_access() -> None:
    production_text = "\n".join(
        _read(path) for path in (INSTALLER, BUILD_SCRIPT, INSTALLER_README)
    )

    for forbidden in (
        "HKLM",
        "HKEY_LOCAL_MACHINE",
        "ExtensionInstallForcelist",
        "Chrome\\User Data",
        "Stop-Process",
        "taskkill",
        "Program Files\\ShopeeImageDownloader",
        HISTORICAL_EXTENSION_ID,
        "D:\\download-picture-shopee",
        "C:\\Users\\khong",
    ):
        assert forbidden not in production_text

    assert "PrivilegesRequired=lowest" in production_text
    assert "chrome://extensions" in production_text
    assert EXTENSION_ID in production_text
    assert HOST_NAME in production_text


def test_installed_guide_is_vietnamese_manual_extension_and_safe_uninstall() -> None:
    readme = _read(INSTALLER_README)

    assert "Setup.exe đã cài ứng dụng và đăng ký Native Host tự động" in readme
    assert "%LOCALAPPDATA%\\Programs\\ShopeeImageDownloader\\chrome_extension" in readme
    assert "Tải tiện ích đã giải nén" in readme
    assert EXTENSION_ID in readme
    assert "worker tab" in readme
    assert "thực hiện thủ công" in readme
    assert "registry định danh thư mục sản phẩm và ảnh đã tải được giữ nguyên" in readme


def test_no_private_extension_key_file_is_present() -> None:
    private_suffixes = {".pem", ".key", ".p12", ".pfx"}
    matches = [
        path
        for path in (REPO_ROOT / "chrome_extension").rglob("*")
        if path.is_file() and path.suffix.lower() in private_suffixes
    ]

    assert matches == []
