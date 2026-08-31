"""Tests for Windows-safe per-product folder creation."""

from __future__ import annotations

from pathlib import Path

import pytest

from shopee_image_downloader.storage.product_folder import (
    MAX_PRODUCT_FOLDER_NAME_LENGTH,
    ProductFolderError,
    ensure_product_folder,
    sanitize_product_folder_name,
)


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("Túi đựng đồ du lịch CSHome", "Túi đựng đồ du lịch CSHome"),
        (
            'Túi du lịch / chống nước: size L? <mới>|"x"*',
            "Túi du lịch _ chống nước_ size L_ _mới_x_",
        ),
        ("  Túi   đựng  đồ  ", "Túi đựng đồ"),
        ("Sản phẩm   ", "Sản phẩm"),
        ("Sản phẩm...   ", "Sản phẩm"),
        ("Sản\x00phẩm\x1ftốt", "Sản_phẩm_tốt"),
        (".", "product_123_456"),
        ("..", "product_123_456"),
        ("", "product_123_456"),
        ("<>:\"/\\|?*", "product_123_456"),
    ],
)
def test_sanitize_product_folder_name(raw_name: str, expected: str) -> None:
    assert sanitize_product_folder_name(raw_name, "123", "456") == expected


def test_very_long_title_is_truncated_without_losing_unicode() -> None:
    title = "Áo khoác tiếng Việt " * 20

    result = sanitize_product_folder_name(title, "123", "456")

    assert 0 < len(result) <= MAX_PRODUCT_FOLDER_NAME_LENGTH
    assert result.startswith("Áo khoác tiếng Việt")
    assert not result.endswith((" ", "."))


@pytest.mark.parametrize(
    "reserved_name",
    [
        "CON",
        "con",
        "CON.txt",
        "PRN",
        "AUX",
        "AUX.anything",
        "NUL",
        "COM1",
        "COM9",
        "LPT1",
        "LPT9",
    ],
)
def test_reserved_device_names_are_prefixed(reserved_name: str) -> None:
    result = sanitize_product_folder_name(reserved_name, "123", "456")

    assert result == f"_{reserved_name}"


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../../Windows",
        "..\\..\\Windows",
        "C:\\Windows\\System32",
        "/etc/passwd",
        "foo/bar",
        "foo\\bar",
    ],
)
def test_path_like_names_always_create_inside_output_root(
    tmp_path: Path,
    malicious_name: str,
) -> None:
    result = ensure_product_folder(tmp_path, malicious_name, "123", "456")

    assert result.parent.resolve() == tmp_path.resolve()
    assert result.is_dir()
    assert len(list(tmp_path.iterdir())) == 1


def test_collision_uses_stable_product_identity_suffix(tmp_path: Path) -> None:
    existing = tmp_path / "Same Product Name"
    existing.mkdir()

    result = ensure_product_folder(tmp_path, "Same Product Name", "123", "456")

    assert result == tmp_path / "Same Product Name [123-456]"
    assert existing.is_dir()
    assert result.is_dir()


def test_id_fallback_does_not_append_redundant_identity(tmp_path: Path) -> None:
    first = ensure_product_folder(tmp_path, "..", "123", "456")
    second = ensure_product_folder(tmp_path, "..", "123", "456")

    assert first == second == tmp_path / "product_123_456"


@pytest.mark.parametrize("output_root", [None, ""])
def test_missing_output_root_fails_cleanly(output_root: str | None) -> None:
    with pytest.raises(ProductFolderError, match="Chưa chọn"):
        ensure_product_folder(output_root, "Sản phẩm", "123", "456")


def test_unavailable_or_non_directory_output_root_fails_cleanly(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ProductFolderError, match="không tồn tại"):
        ensure_product_folder(missing, "Sản phẩm", "123", "456")

    file_root = tmp_path / "file.txt"
    file_root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ProductFolderError, match="không phải thư mục"):
        ensure_product_folder(file_root, "Sản phẩm", "123", "456")
