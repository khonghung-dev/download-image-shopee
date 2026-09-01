"""Derive and validate the Chrome extension identity from its manifest key."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
from typing import Any

EXTENSION_ID_ALPHABET = "abcdefghijklmnop"


class ExtensionIdentityError(ValueError):
    """Raised when extension identity configuration is missing or inconsistent."""


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object or raise a diagnostic identity error."""
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExtensionIdentityError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExtensionIdentityError(f"Expected a JSON object in {path}")
    return value


def public_key_der_from_manifest(manifest: dict[str, Any]) -> bytes:
    """Decode the manifest's public SPKI DER key from strict Base64."""
    manifest_key = manifest.get("key")
    if not isinstance(manifest_key, str) or not manifest_key.strip():
        raise ExtensionIdentityError('Chrome extension manifest must contain a non-empty "key"')
    try:
        return base64.b64decode(manifest_key, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ExtensionIdentityError('Chrome extension manifest "key" is not valid Base64') from exc


def extension_id_from_public_key_der(public_key_der: bytes) -> str:
    """Apply Chromium's SHA-256/first-128-bit/nibble-to-a-p ID algorithm."""
    first_128_bits = hashlib.sha256(public_key_der).digest()[:16]
    return "".join(
        EXTENSION_ID_ALPHABET[nibble]
        for byte in first_128_bits
        for nibble in (byte >> 4, byte & 0x0F)
    )


def extension_id_from_manifest(manifest_path: Path) -> str:
    """Return the deterministic extension ID established by a manifest key."""
    manifest = load_json_object(manifest_path)
    return extension_id_from_public_key_der(public_key_der_from_manifest(manifest))


def extension_origin_from_manifest(manifest_path: Path) -> str:
    """Return the one exact Native Messaging origin for the keyed extension."""
    return f"chrome-extension://{extension_id_from_manifest(manifest_path)}/"


def validate_native_manifest(manifest_path: Path, native_manifest_path: Path) -> str:
    """Fail unless a Native Messaging manifest allows only the keyed extension."""
    extension_origin = extension_origin_from_manifest(manifest_path)
    native_manifest = load_json_object(native_manifest_path)
    allowed_origins = native_manifest.get("allowed_origins")
    if allowed_origins != [extension_origin]:
        raise ExtensionIdentityError(
            f"{native_manifest_path} allowed_origins must equal [{extension_origin!r}], "
            f"got {allowed_origins!r}"
        )
    return extension_origin.removeprefix("chrome-extension://").removesuffix("/")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--check-native-manifest", type=Path)
    parser.add_argument("--print-origin", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Print canonical identity data and optionally validate a host manifest."""
    args = _parse_args()
    if args.check_native_manifest is not None:
        extension_id = validate_native_manifest(args.manifest, args.check_native_manifest)
    else:
        extension_id = extension_id_from_manifest(args.manifest)
    if args.print_origin:
        print(f"chrome-extension://{extension_id}/")
    else:
        print(extension_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
