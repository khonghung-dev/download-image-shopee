"""Deterministic Task 016A identity and Windows release-definition gates."""

from __future__ import annotations

import json
from pathlib import Path

from build_support.extension_identity import (
    extension_id_from_manifest,
    extension_origin_from_manifest,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
STABLE_EXTENSION_ID = "bhbnfalghoklngoohdpnjedcdcplbjhm"
HISTORICAL_EXTENSION_ID = "kjkgdknadhnpigglcpjbgkkbcngclhgf"
HOST_NAME = "com.shopee_image_downloader.bridge"


def test_stable_extension_identity_is_key_derived_and_path_independent(
    tmp_path: Path,
) -> None:
    manifest_path = REPO_ROOT / "chrome_extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest.get("key")
    assert extension_id_from_manifest(manifest_path) == STABLE_EXTENSION_ID
    assert extension_origin_from_manifest(manifest_path) == (
        f"chrome-extension://{STABLE_EXTENSION_ID}/"
    )

    relocated = tmp_path / "different-user" / "different-folder" / "manifest.json"
    relocated.parent.mkdir(parents=True)
    relocated.write_text(json.dumps(manifest), encoding="utf-8")
    assert extension_id_from_manifest(relocated) == STABLE_EXTENSION_ID


def test_no_historical_id_in_production_runtime_or_host_configuration() -> None:
    production_files = [
        *(REPO_ROOT / "chrome_extension").glob("*.js"),
        REPO_ROOT / "chrome_extension" / "manifest.json",
        REPO_ROOT / "native_host" / f"{HOST_NAME}.json",
        REPO_ROOT / "native_host" / f"{HOST_NAME}.json.template",
        REPO_ROOT / "native_host" / "build_host.ps1",
        REPO_ROOT / "native_host" / "install_host.ps1",
    ]
    for path in production_files:
        assert HISTORICAL_EXTENSION_ID not in path.read_text(
            encoding="utf-8-sig"
        ), path


def test_release_install_script_is_self_locating_key_derived_and_hkcu_only() -> None:
    script = (
        REPO_ROOT / "packaging" / "install_native_host.ps1"
    ).read_text(encoding="utf-8")

    assert "$PSScriptRoot" in script
    assert "FromBase64String" in script
    assert "SHA256" in script
    assert "allowed_origins = @($ExtensionOrigin)" in script
    assert "HKCU:\\Software\\Google\\Chrome\\NativeMessagingHosts\\$HostName" in script
    assert HOST_NAME in script
    assert "HKLM" not in script
    assert "HKEY_LOCAL_MACHINE" not in script
    assert "chrome-extension://*" not in script
    assert HISTORICAL_EXTENSION_ID not in script
    assert "Chrome\\User Data" not in script
    assert "Stop-Process" not in script


def test_desktop_spec_is_canonical_onedir_and_release_readme_has_exact_id() -> None:
    spec = (REPO_ROOT / "packaging" / "ShopeeImageDownloader.spec").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "packaging" / "README_FIRST.txt").read_text(
        encoding="utf-8"
    )

    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec
    assert "onefile" not in spec.lower()
    assert "ShopeeImageDownloader" in spec
    assert STABLE_EXTENSION_ID in readme
    assert "chrome://extensions" in readme
    assert "chrome_extension" in readme
    assert "install_native_host.ps1" in readme
    assert "ShopeeImageDownloader.exe" in readme
    assert "tab Shopee thật" in readme


def test_native_host_builder_propagates_pyinstaller_failure() -> None:
    build_script = (REPO_ROOT / "native_host" / "build_host.ps1").read_text(
        encoding="utf-8"
    )

    assert "[string]$DistDir" in build_script
    assert "[string]$WorkDir" in build_script
    assert "if ($LASTEXITCODE -ne 0)" in build_script
    assert "exit $LASTEXITCODE" in build_script
