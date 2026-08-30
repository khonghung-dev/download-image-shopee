"""Settings management and persistence for Shopee Image Downloader."""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

APP_DIR_NAME: str = "ShopeeImageDownloader"
SETTINGS_FILE_NAME: str = "settings.json"
KEY_OUTPUT_FOLDER: str = "output_folder"


def get_default_config_path() -> Path:
    """Return the default cross-platform configuration file path."""
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        base_dir = Path(os.getenv("LOCALAPPDATA", "")) / APP_DIR_NAME
    else:
        base_dir = Path.home() / f".{APP_DIR_NAME.lower()}"
    return base_dir / SETTINGS_FILE_NAME


class SettingsManager:
    """Manages application configuration persistence with JSON storage."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is not None:
            self._config_path = Path(config_path)
        else:
            self._config_path = get_default_config_path()

    @property
    def config_path(self) -> Path:
        """Return the current configuration file path."""
        return self._config_path

    def load(self) -> dict[str, Any]:
        """Load settings from the configuration file safely."""
        if not self._config_path.is_file():
            return {}

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                logger.warning("Config file did not contain a valid JSON object: %s", self._config_path)
                return {}
        except (json.JSONDecodeError, OSError) as err:
            logger.error("Failed to load settings from %s: %s", self._config_path, err)
            return {}

    def save(self, data: dict[str, Any]) -> bool:
        """Save settings dictionary to the configuration file safely."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except OSError as err:
            logger.error("Failed to save settings to %s: %s", self._config_path, err)
            return False

    def get_output_folder(self) -> str | None:
        """Retrieve the persisted output folder path if it exists on disk."""
        data = self.load()
        folder_str = data.get(KEY_OUTPUT_FOLDER)
        if not folder_str or not isinstance(folder_str, str):
            return None

        folder_path = Path(folder_str)
        if folder_path.is_dir():
            return str(folder_path)

        return None

    def set_output_folder(self, folder_path: str | Path) -> bool:
        """Persist the output folder path to settings."""
        norm_path = str(Path(folder_path))
        data = self.load()
        data[KEY_OUTPUT_FOLDER] = norm_path
        return self.save(data)

    def clear(self) -> bool:
        """Clear all stored settings."""
        if self._config_path.exists():
            try:
                self._config_path.unlink()
                return True
            except OSError as err:
                logger.error("Failed to delete settings file %s: %s", self._config_path, err)
                return False
        return True
