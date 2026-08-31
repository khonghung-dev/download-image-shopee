"""Tests for the active Native Host ↔ desktop protocol."""

import json

from shopee_image_downloader.core.bridge_protocol import (
    MAX_MESSAGE_SIZE,
    MSG_TYPE_BATCH_FINISHED,
    MSG_TYPE_CANCEL_PROCESSING,
    MSG_TYPE_ERROR,
    MSG_TYPE_HELLO,
    MSG_TYPE_HELLO_ACK,
    MSG_TYPE_OPEN_PRODUCT,
    MSG_TYPE_PROCESS_ERROR,
    MSG_TYPE_PROCESS_PROGRESS,
    MSG_TYPE_PRODUCT_RESULT,
    MSG_TYPE_PRODUCT_RESULT_ACK,
    PROTOCOL_VERSION,
    BridgeProductData,
    create_batch_finished_message,
    create_cancel_processing_message,
    create_error_message,
    create_hello_ack_message,
    create_open_product_message,
    create_product_result_ack_message,
    parse_bridge_product_data,
    validate_incoming_message,
)

NATIVE_HOST_CLIENT = "shopee_chrome_extension"


def _incoming(message_type: str, **fields: object) -> str:
    return json.dumps({
        "type": message_type,
        "protocol_version": PROTOCOL_VERSION,
        **fields,
    })


def _product_payload(images: list[str] | None = None) -> dict[str, object]:
    image_urls = images or [
        "https://down-vn.img.susercontent.com/file/img1.jpg",
        "https://down-vn.img.susercontent.com/file/img2.jpg",
    ]
    return {
        "url": "https://shopee.vn/product/12345/67890",
        "product_name": "Áo thun cotton cao cấp",
        "shop_id": "12345",
        "item_id": "67890",
        "images": image_urls,
        "image_count": len(image_urls),
    }


def test_active_desktop_outbound_message_builders() -> None:
    hello_ack = json.loads(create_hello_ack_message())
    assert hello_ack == {
        "type": MSG_TYPE_HELLO_ACK,
        "protocol_version": PROTOCOL_VERSION,
    }

    product_ack = json.loads(create_product_result_ack_message(True, "OK"))
    assert product_ack["type"] == MSG_TYPE_PRODUCT_RESULT_ACK
    assert product_ack["success"] is True
    assert product_ack["message"] == "OK"

    open_product = json.loads(create_open_product_message("req-1", "https://shopee.vn/item"))
    assert open_product["type"] == MSG_TYPE_OPEN_PRODUCT
    assert open_product["request_id"] == "req-1"

    cancel = json.loads(create_cancel_processing_message("req-1"))
    assert cancel["type"] == MSG_TYPE_CANCEL_PROCESSING
    assert cancel["request_id"] == "req-1"

    finished = json.loads(create_batch_finished_message(2, 1))
    assert finished["type"] == MSG_TYPE_BATCH_FINISHED
    assert finished["success_count"] == 2
    assert finished["fail_count"] == 1

    error = json.loads(create_error_message("bad message"))
    assert error["type"] == MSG_TYPE_ERROR


def test_validate_native_host_hello_as_text_and_bytes() -> None:
    message = _incoming(MSG_TYPE_HELLO, client=NATIVE_HOST_CLIENT)
    for raw in (message, message.encode("utf-8")):
        valid, parsed, error = validate_incoming_message(raw)
        assert valid is True
        assert parsed is not None
        assert parsed["client"] == NATIVE_HOST_CLIENT
        assert error is None


def test_validate_progress_and_error_from_extension() -> None:
    progress = _incoming(MSG_TYPE_PROCESS_PROGRESS, request_id="req-1", stage="waiting_page")
    valid, parsed, error = validate_incoming_message(progress)
    assert valid is True
    assert parsed is not None and parsed["stage"] == "waiting_page"
    assert error is None

    process_error = _incoming(
        MSG_TYPE_PROCESS_ERROR,
        request_id="req-1",
        url="https://shopee.vn/item",
        error_code="PRODUCT_TIMEOUT",
        message="Timed out",
    )
    valid, parsed, error = validate_incoming_message(process_error)
    assert valid is True
    assert parsed is not None and parsed["error_code"] == "PRODUCT_TIMEOUT"
    assert error is None


def test_validate_and_parse_product_result() -> None:
    raw = _incoming(MSG_TYPE_PRODUCT_RESULT, request_id="req-1", data=_product_payload())
    valid, parsed, error = validate_incoming_message(raw)
    assert valid is True
    assert parsed is not None
    assert error is None

    product = parse_bridge_product_data(parsed)
    assert isinstance(product, BridgeProductData)
    assert product.url == "https://shopee.vn/product/12345/67890"
    assert product.product_name == "Áo thun cotton cao cấp"
    assert product.product_key == "12345:67890"
    assert product.request_id == "req-1"
    assert product.image_count == 2


def test_reject_malformed_empty_oversized_and_wrong_version_messages() -> None:
    valid, _, error = validate_incoming_message("NOT_JSON_DATA{}}")
    assert valid is False and "JSON không hợp lệ" in str(error)

    for raw in (None, ""):
        valid, _, _ = validate_incoming_message(raw)
        assert valid is False

    valid, _, error = validate_incoming_message("a" * (MAX_MESSAGE_SIZE + 100))
    assert valid is False and "vượt quá giới hạn" in str(error)

    wrong_version = json.dumps({
        "type": MSG_TYPE_HELLO,
        "protocol_version": 999,
        "client": NATIVE_HOST_CLIENT,
    })
    valid, _, error = validate_incoming_message(wrong_version)
    assert valid is False and "không được hỗ trợ" in str(error)


def test_reject_missing_or_unknown_message_type() -> None:
    valid, _, error = validate_incoming_message(json.dumps({"protocol_version": PROTOCOL_VERSION}))
    assert valid is False and "Thiếu trường 'type'" in str(error)

    for message_type in (
        "process_url",
        "verification_required",
        "RUN_FULL_SCAN",
        "custom_remote_eval",
    ):
        valid, _, error = validate_incoming_message(_incoming(message_type))
        assert valid is False
        assert "không xác định" in str(error)


def test_desktop_outbound_types_are_not_accepted_as_inbound() -> None:
    """Message ownership is directional at the desktop validation boundary."""
    messages = [
        create_hello_ack_message(),
        create_product_result_ack_message(),
        create_open_product_message("req-1", "https://shopee.vn/item"),
        create_cancel_processing_message("req-1"),
        create_batch_finished_message(),
        create_error_message("bad"),
    ]
    for message in messages:
        valid, _, error = validate_incoming_message(message)
        assert valid is False
        assert "không xác định" in str(error)


def test_reject_missing_product_fields_and_invalid_images() -> None:
    for field in ("product_name", "shop_id", "item_id"):
        payload = _product_payload()
        payload.pop(field)
        valid, _, error = validate_incoming_message(
            _incoming(MSG_TYPE_PRODUCT_RESULT, data=payload)
        )
        assert valid is False
        assert field in str(error)

    payload = _product_payload()
    payload["images"] = "not-a-list"
    valid, _, error = validate_incoming_message(_incoming(MSG_TYPE_PRODUCT_RESULT, data=payload))
    assert valid is False and "images" in str(error)

    payload = _product_payload()
    payload["images"] = ["https://example.com/1.jpg", ""]
    payload["image_count"] = 2
    valid, _, error = validate_incoming_message(_incoming(MSG_TYPE_PRODUCT_RESULT, data=payload))
    assert valid is False and "URL ảnh" in str(error)


def test_product_result_image_count_integrity() -> None:
    nine_images = [f"https://img.example/{index}.jpg" for index in range(1, 10)]
    payload = _product_payload(nine_images)
    valid, parsed, error = validate_incoming_message(
        _incoming(MSG_TYPE_PRODUCT_RESULT, request_id="req-9", data=payload)
    )
    assert valid is True
    assert error is None
    assert parsed is not None
    assert parse_bridge_product_data(parsed).image_count == 9

    payload["images"] = nine_images[:4]
    valid, _, error = validate_incoming_message(
        _incoming(MSG_TYPE_PRODUCT_RESULT, request_id="req-mismatch", data=payload)
    )
    assert valid is False
    assert "PROTOCOL_INTEGRITY_ERROR" in str(error)
