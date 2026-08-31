"""Protocol definition and message validation for the Extension ↔ Desktop bridge."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Protocol Configuration Constants
PROTOCOL_VERSION: int = 1
DEFAULT_BRIDGE_HOST: str = "127.0.0.1"
DEFAULT_BRIDGE_PORT: int = 8765
MAX_MESSAGE_SIZE: int = 5 * 1024 * 1024  # 5 MB safety limit

# Protocol Message Types
MSG_TYPE_HELLO: str = "hello"
MSG_TYPE_HELLO_ACK: str = "hello_ack"
MSG_TYPE_PRODUCT_RESULT: str = "product_result"
MSG_TYPE_PRODUCT_RESULT_ACK: str = "product_result_ack"
MSG_TYPE_OPEN_PRODUCT: str = "open_product"
MSG_TYPE_PROCESS_PROGRESS: str = "process_progress"
MSG_TYPE_PROCESS_ERROR: str = "process_error"
MSG_TYPE_CANCEL_PROCESSING: str = "cancel_processing"
MSG_TYPE_BATCH_FINISHED: str = "batch_finished"
MSG_TYPE_ERROR: str = "error"


@dataclass(frozen=True)
class BridgeProductData:
    """Represents product information transmitted from the Chrome Extension."""

    url: str
    product_name: str
    shop_id: str
    item_id: str
    images: list[str]
    request_id: str | None = None
    input_url: str = ""
    final_url: str = ""
    image_count: int | None = None

    @property
    def product_key(self) -> str:
        """Return canonical deduplication key for this product listing."""
        return f"{self.shop_id}:{self.item_id}"


def create_hello_ack_message(protocol_version: int = PROTOCOL_VERSION) -> str:
    """Create a hello_ack handshake response message."""
    return json.dumps({
        "type": MSG_TYPE_HELLO_ACK,
        "protocol_version": protocol_version,
    })


def create_product_result_ack_message(
    success: bool = True,
    message: str = "Received",
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    """Create an acknowledgment message for product_result."""
    return json.dumps({
        "type": MSG_TYPE_PRODUCT_RESULT_ACK,
        "protocol_version": protocol_version,
        "success": success,
        "message": message,
    })


def create_open_product_message(
    request_id: str,
    url: str,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    """Create an open_product command message for the Chrome Extension."""
    return json.dumps({
        "type": MSG_TYPE_OPEN_PRODUCT,
        "protocol_version": protocol_version,
        "request_id": request_id,
        "url": url,
    })


def create_cancel_processing_message(
    request_id: str | None = None,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    """Create a cancel_processing command message."""
    payload: dict[str, Any] = {
        "type": MSG_TYPE_CANCEL_PROCESSING,
        "protocol_version": protocol_version,
    }
    if request_id is not None:
        payload["request_id"] = request_id
    return json.dumps(payload)


def create_batch_finished_message(
    success_count: int = 0,
    fail_count: int = 0,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    """Create a batch_finished notification message for the Chrome Extension."""
    return json.dumps({
        "type": MSG_TYPE_BATCH_FINISHED,
        "protocol_version": protocol_version,
        "success_count": success_count,
        "fail_count": fail_count,
    })


def create_error_message(
    error: str,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    """Create a protocol error response."""
    return json.dumps({
        "type": MSG_TYPE_ERROR,
        "protocol_version": protocol_version,
        "error": error,
    })


def validate_incoming_message(
    raw_message: str | bytes | None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Validate raw incoming WebSocket message string or bytes against schema.

    Returns:
        tuple[is_valid, parsed_dict_or_none, error_message_or_none]
    """
    if raw_message is None:
        return False, None, "Tin nhắn trống"

    if isinstance(raw_message, bytes):
        if len(raw_message) > MAX_MESSAGE_SIZE:
            return False, None, f"Kích thước tin nhắn vượt quá giới hạn ({len(raw_message)} > {MAX_MESSAGE_SIZE})"
        try:
            raw_str = raw_message.decode("utf-8")
        except UnicodeDecodeError:
            return False, None, "Không thể giải mã UTF-8"
    elif isinstance(raw_message, str):
        if len(raw_message.encode("utf-8")) > MAX_MESSAGE_SIZE:
            return False, None, f"Kích thước tin nhắn vượt quá giới hạn ({len(raw_message)} > {MAX_MESSAGE_SIZE})"
        raw_str = raw_message
    else:
        return False, None, f"Định dạng tin nhắn không hợp lệ: {type(raw_message)}"

    try:
        data = json.loads(raw_str)
    except (json.JSONDecodeError, ValueError) as err:
        return False, None, f"JSON không hợp lệ: {err}"

    if not isinstance(data, dict):
        return False, None, "Payload phải là JSON object (dict)"

    msg_type = data.get("type")
    if not isinstance(msg_type, str) or not msg_type:
        return False, None, "Thiếu trường 'type' hoặc 'type' không hợp lệ"

    version = data.get("protocol_version")
    if version != PROTOCOL_VERSION:
        return False, None, f"Phiên bản giao thức không được hỗ trợ: {version} (yêu cầu: {PROTOCOL_VERSION})"

    if msg_type == MSG_TYPE_HELLO:
        client = data.get("client")
        if not isinstance(client, str) or not client:
            return False, None, "Trường 'client' không hợp lệ trong handshake hello"
        return True, data, None

    if msg_type == MSG_TYPE_PROCESS_PROGRESS:
        req_id = data.get("request_id")
        stage = data.get("stage")
        if not isinstance(req_id, str) or not req_id.strip():
            return False, None, "Trường 'request_id' không hợp lệ hoặc bị thiếu trong process_progress"
        if not isinstance(stage, str) or not stage.strip():
            return False, None, "Trường 'stage' không hợp lệ hoặc bị thiếu trong process_progress"
        return True, data, None

    if msg_type == MSG_TYPE_PROCESS_ERROR:
        req_id = data.get("request_id")
        msg = data.get("message")
        if not isinstance(req_id, str) or not req_id.strip():
            return False, None, "Trường 'request_id' không hợp lệ hoặc bị thiếu trong process_error"
        if not isinstance(msg, str):
            return False, None, "Trường 'message' không hợp lệ hoặc bị thiếu trong process_error"
        return True, data, None

    if msg_type == MSG_TYPE_PRODUCT_RESULT:
        product_data = data.get("data")
        if not isinstance(product_data, dict):
            return False, None, "Trường 'data' trong product_result phải là object"

        url = product_data.get("url") or product_data.get("input_url") or product_data.get("final_url")
        product_name = product_data.get("product_name")
        shop_id = product_data.get("shop_id")
        item_id = product_data.get("item_id")
        images = product_data.get("images")

        if not isinstance(url, str) or not url.strip():
            return False, None, "Trường 'url' không hợp lệ hoặc bị thiếu"
        if not isinstance(product_name, str) or not product_name.strip():
            return False, None, "Trường 'product_name' không hợp lệ hoặc bị thiếu"
        if shop_id is None or str(shop_id).strip() in ("", "N/A"):
            return False, None, "Trường 'shop_id' không hợp lệ hoặc bị thiếu"
        if item_id is None or str(item_id).strip() in ("", "N/A"):
            return False, None, "Trường 'item_id' không hợp lệ hoặc bị thiếu"
        if not isinstance(images, list):
            return False, None, "Trường 'images' phải là danh sách (list)"

        # Ensure all image URLs are non-empty strings
        for idx, img in enumerate(images):
            if not isinstance(img, str) or not img.strip():
                return False, None, f"URL ảnh tại vị trí {idx} không hợp lệ"

        # Protocol Integrity Check: Validate image_count == len(images) if provided
        declared_count = product_data.get("image_count")
        if declared_count is not None:
            if not isinstance(declared_count, int) or declared_count != len(images):
                return False, None, f"PROTOCOL_INTEGRITY_ERROR: image_count ({declared_count}) != len(images) ({len(images)})"

        return True, data, None

    return False, None, f"Loại tin nhắn không xác định: '{msg_type}'"


def parse_bridge_product_data(data_dict: dict[str, Any]) -> BridgeProductData:
    """Extract a validated BridgeProductData instance from a product_result message dict."""
    inner = data_dict["data"]
    req_id = data_dict.get("request_id")
    url = str(inner.get("url") or inner.get("input_url") or inner.get("final_url") or "").strip()
    input_url = str(inner.get("input_url") or url).strip()
    final_url = str(inner.get("final_url") or url).strip()
    parsed_images = [str(img).strip() for img in inner.get("images", []) if isinstance(img, str) and img.strip()]
    declared_count = inner.get("image_count")
    final_count = declared_count if isinstance(declared_count, int) else len(parsed_images)

    return BridgeProductData(
        url=url,
        product_name=str(inner["product_name"]).strip(),
        shop_id=str(inner["shop_id"]).strip(),
        item_id=str(inner["item_id"]).strip(),
        images=parsed_images,
        image_count=final_count,
        request_id=str(req_id).strip() if req_id else None,
        input_url=input_url,
        final_url=final_url,
    )
