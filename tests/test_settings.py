"""Unit tests for SettingsManager and local configuration persistence."""

import json
from pathlib import Path
from shopee_image_downloader.storage.settings import (
    KEY_OUTPUT_FOLDER,
    SettingsManager,
    get_default_config_path,
)


def test_default_config_path() -> None:
    """Verify that default config path is a valid Path object with settings.json."""
    default_path = get_default_config_path()
    assert isinstance(default_path, Path)
    assert default_path.name == "settings.json"


def test_settings_load_non_existent(tmp_path: Path) -> None:
    """Verify loading from a non-existent file returns an empty dictionary."""
    config_file = tmp_path / "non_existent_settings.json"
    manager = SettingsManager(config_path=config_file)
    assert manager.load() == {}
    assert manager.get_output_folder() is None


def test_settings_save_and_load(tmp_path: Path) -> None:
    """Verify saving settings persists to disk and can be reloaded."""
    config_file = tmp_path / "test_settings.json"
    manager = SettingsManager(config_path=config_file)

    data = {"custom_key": "custom_value", "number": 42}
    assert manager.save(data) is True
    assert config_file.is_file()

    loaded = manager.load()
    assert loaded == data


def test_settings_corrupted_json(tmp_path: Path) -> None:
    """Verify that a corrupted JSON file is safely handled without raising exceptions."""
    config_file = tmp_path / "corrupted.json"
    config_file.write_text("NOT_VALID_JSON{:::}", encoding="utf-8")

    manager = SettingsManager(config_path=config_file)
    assert manager.load() == {}
    assert manager.get_output_folder() is None


def test_get_output_folder_existing_and_missing(tmp_path: Path) -> None:
    """Verify get_output_folder returns the path only when the folder actually exists."""
    config_file = tmp_path / "settings.json"
    manager = SettingsManager(config_path=config_file)

    # 1. Path does not exist on disk
    missing_dir = tmp_path / "missing_folder"
    manager.set_output_folder(missing_dir)
    assert manager.get_output_folder() is None

    # 2. Path created on disk
    existing_dir = tmp_path / "valid_folder"
    existing_dir.mkdir()
    manager.set_output_folder(existing_dir)
    assert manager.get_output_folder() == str(existing_dir)


def test_set_output_folder_persistence(tmp_path: Path) -> None:
    """Verify set_output_folder writes to the JSON file correctly."""
    config_file = tmp_path / "sub" / "settings.json"
    manager = SettingsManager(config_path=config_file)

    target_dir = tmp_path / "images"
    target_dir.mkdir(parents=True)

    manager.set_output_folder(target_dir)

    # Inspect raw JSON
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get(KEY_OUTPUT_FOLDER) == str(target_dir)


def test_settings_clear(tmp_path: Path) -> None:
    """Verify clear removes the settings file."""
    config_file = tmp_path / "settings.json"
    manager = SettingsManager(config_path=config_file)
    manager.save({"some": "value"})
    assert config_file.exists()

    assert manager.clear() is True
    assert not config_file.exists()
