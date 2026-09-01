"""Small app-local registry for durable product-folder ownership."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import uuid
from typing import Any

from PySide6.QtCore import QStandardPaths

logger = logging.getLogger(__name__)

REGISTRY_SCHEMA_VERSION: int = 1
REGISTRY_FILE_NAME: str = "product-folders.json"


class ProductRegistryError(RuntimeError):
    """Raised when durable registry state cannot be committed safely."""


def get_default_registry_path() -> Path:
    """Return the platform-approved application-local registry path."""
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        return (
            Path(os.environ["LOCALAPPDATA"])
            / "ShopeeImageDownloader"
            / REGISTRY_FILE_NAME
        )
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    if location:
        return Path(location) / REGISTRY_FILE_NAME
    return Path.home() / ".shopeeimagedownloader" / REGISTRY_FILE_NAME


class ProductIdentityRegistry:
    """Persist only normalized output-root/product-key folder mappings."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else get_default_registry_path()

    @property
    def path(self) -> Path:
        """Return the injectable registry JSON path."""
        return self._path

    def get_folder(self, output_root: Path, product_key: str) -> str | None:
        """Return one stored relative folder component, if validly shaped."""
        products = self._load()["products"]
        entry = products.get(self._mapping_key(output_root, product_key))
        if not isinstance(entry, dict):
            return None
        folder = entry.get("folder")
        return folder if isinstance(folder, str) and folder else None

    def set_folder(
        self,
        output_root: Path,
        product_key: str,
        folder_name: str,
    ) -> None:
        """Atomically set one durable ownership mapping."""
        data = self._load()
        data["products"][self._mapping_key(output_root, product_key)] = {
            "folder": folder_name
        }
        self._write_atomic(data)

    def remove(self, output_root: Path, product_key: str) -> None:
        """Atomically remove one stale mapping when it exists."""
        data = self._load()
        key = self._mapping_key(output_root, product_key)
        if key not in data["products"]:
            return
        del data["products"][key]
        self._write_atomic(data)

    def _load(self) -> dict[str, Any]:
        empty: dict[str, Any] = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "products": {},
        }
        try:
            if not self._path.is_file():
                return empty
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.warning("Bỏ qua registry hỏng tại %s: %s", self._path, exc)
            return empty
        if (
            not isinstance(loaded, dict)
            or loaded.get("schema_version") != REGISTRY_SCHEMA_VERSION
            or not isinstance(loaded.get("products"), dict)
        ):
            logger.warning("Bỏ qua registry sai schema tại %s", self._path)
            return empty
        return loaded

    def _write_atomic(self, data: dict[str, Any]) -> None:
        temporary = self._path.with_name(
            f"{self._path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("x", encoding="utf-8", newline="\n") as output:
                json.dump(data, output, ensure_ascii=False, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self._path)
        except OSError as exc:
            raise ProductRegistryError(
                f"Không thể lưu registry định danh sản phẩm: {exc}"
            ) from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Không thể xóa registry tạm: %s", temporary)

    @staticmethod
    def _mapping_key(output_root: Path, product_key: str) -> str:
        normalized_root = os.path.normcase(str(output_root.resolve(strict=True)))
        return f"{normalized_root}|{product_key}"
