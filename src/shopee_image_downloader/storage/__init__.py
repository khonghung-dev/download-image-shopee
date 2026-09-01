"""Storage and persistence package for Shopee Image Downloader."""

from shopee_image_downloader.storage.product_folder import (
    MAX_PRODUCT_FOLDER_NAME_LENGTH,
    PRODUCT_ID_MARKER_FILENAME,
    ProductFolderError,
    ensure_product_folder,
    sanitize_product_folder_name,
)
from shopee_image_downloader.storage.settings import SettingsManager

__all__ = [
    "MAX_PRODUCT_FOLDER_NAME_LENGTH",
    "PRODUCT_ID_MARKER_FILENAME",
    "ProductFolderError",
    "SettingsManager",
    "ensure_product_folder",
    "sanitize_product_folder_name",
]
