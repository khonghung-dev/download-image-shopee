"""Filesystem safety validation and path guards for Shopee Image Downloader.

Ensures that all persistent file and directory operations (read/write/delete) remain
strictly within application-owned directories or allowed repository roots, and never
touch or mutate personal user browser profiles or sensitive system paths.
"""

import logging
import os
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)

APP_DIR_NAME: str = "ShopeeImageDownloader"

# Off-limits directory name substrings and fragments that must NEVER be targeted
_FORBIDDEN_PROFILE_PATTERNS: tuple[str, ...] = (
    "profile 10",
    "google\\chrome\\user data",
    "google/chrome/user data",
)

# Standard root system directories that must NEVER be modified or deleted
_SYSTEM_ROOT_PATTERNS: tuple[str, ...] = (
    "c:\\",
    "c:/",
    "d:\\",
    "d:/",
    "c:\\users",
    "c:/users",
    "c:\\windows",
    "c:/windows",
    "c:\\program files",
    "c:/program files",
    "c:\\program files (x86)",
    "c:/program files (x86)",
)


def get_allowed_writable_roots(allow_temp: bool = True) -> list[Path]:
    """Return the list of canonical base directories where write/delete operations are permitted."""
    roots: list[Path] = []

    # 1. Project repository root (where code resides)
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    try:
        roots.append(repo_root.resolve())
    except Exception:
        roots.append(repo_root)

    # 2. Application AppData directory
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        app_data_root = Path(os.getenv("LOCALAPPDATA", "")) / APP_DIR_NAME
    else:
        app_data_root = Path.home() / f".{APP_DIR_NAME.lower()}"

    try:
        roots.append(app_data_root.resolve())
    except Exception:
        roots.append(app_data_root)

    # 3. Temporary directories (for test execution)
    if allow_temp:
        try:
            temp_root = Path(tempfile.gettempdir()).resolve()
            roots.append(temp_root)
        except Exception:
            pass

    return roots


def is_forbidden_chrome_profile(path: Path | str) -> bool:
    """Return True if the given path points to personal Chrome user data or Profile 10."""
    try:
        resolved_str = str(Path(path).resolve()).lower()
    except Exception:
        resolved_str = str(path).lower()

    # Check for personal Chrome User Data or Profile 10 markers
    for pattern in _FORBIDDEN_PROFILE_PATTERNS:
        if pattern in resolved_str:
            return True

    # Check if inside standard personal Google Chrome User Data directory
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        personal_chrome_user_data = (Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data").resolve()
        try:
            target_resolved = Path(path).resolve()
            if target_resolved == personal_chrome_user_data or personal_chrome_user_data in target_resolved.parents:
                return True
        except Exception:
            pass

    return False


def is_safe_writable_path(path: Path | str, allow_temp: bool = True) -> bool:
    """Check whether a path is strictly inside one of the allowed writable roots.

    Returns False for system roots, personal browser profiles, or paths outside allowed roots.
    """
    if not path:
        return False

    try:
        target = Path(path).resolve()
    except Exception:
        return False

    target_str = str(target).lower().rstrip("\\/")

    # Explicitly check system roots
    for sys_root in _SYSTEM_ROOT_PATTERNS:
        if target_str == sys_root.lower().rstrip("\\/"):
            return False

    # Check if pointing to personal Chrome profile
    if is_forbidden_chrome_profile(target):
        return False

    # Check if target is equal to or a subpath of any allowed root
    allowed_roots = get_allowed_writable_roots(allow_temp=allow_temp)
    for root in allowed_roots:
        try:
            root_resolved = root.resolve()
            if target == root_resolved or root_resolved in target.parents:
                return True
        except Exception:
            continue

    return False


def validate_safe_writable_path(path: Path | str, allow_temp: bool = True) -> Path:
    """Validate that a path is safe for write/delete operations.

    Returns:
        Path: Canonical resolved path if safe.

    Raises:
        PermissionError: If path violates filesystem safety rules or points to forbidden locations.
    """
    target = Path(path).resolve()
    if is_forbidden_chrome_profile(target):
        msg = f"Operation blocked: Target path '{target}' points to a protected personal Chrome profile."
        logger.error(msg)
        raise PermissionError(msg)

    if not is_safe_writable_path(target, allow_temp=allow_temp):
        msg = f"Operation blocked: Target path '{target}' is outside allowed writable roots."
        logger.error(msg)
        raise PermissionError(msg)

    return target
