"""Unit tests for Bridge Protocol definitions and validation."""

import json
import pytest

from shopee_image_downloader.core.bridge_protocol import (
    CLIENT_IDENTIFIER,
    MAX_MESSAGE_SIZE,
    MSG_TYPE_ERROR,
    MSG_TYPE_HELLO,
    MSG_TYPE_HELLO_ACK,
    MSG_TYPE_PRODUCT_RESULT,
    MSG_TYPE_PRODUCT_RESULT_ACK,
    PROTOCOL_VERSION,
    BridgeProductData,
    create_error_message,
    create_hello_ack_message,
    create_hello_message,
    create_product_result_ack_message,
    parse_bridge_product_data,
    validate_incoming_message,
)


def test_create_messages():
    """Test protocol message creation helpers."""
    hello = json.loads(create_hello_message())
    assert hello["type"] == MSG_TYPE_HELLO
    assert hello["protocol_version"] == PROTOCOL_VERSION
    assert hello["client"] == CLIENT_IDENTIFIER

    hello_ack = json.loads(create_hello_ack_message())
    assert hello_ack["type"] == MSG_TYPE_HELLO_ACK
    assert hello_ack["protocol_version"] == PROTOCOL_VERSION

    prod_ack = json.loads(create_product_result_ack_message(True, "OK"))
    assert prod_ack["type"] == MSG_TYPE_PRODUCT_RESULT_ACK
    assert prod_ack["success"] is True
    assert prod_ack["message"] == "OK"

    err_msg = json.loads(create_error_message("Something went wrong"))
    assert err_msg["type"] == MSG_TYPE_ERROR
    assert err_msg["error"] == "Something went wrong"


def test_validate_valid_hello():
    """Test validation of valid hello handshake."""
    msg = json.dumps({
        "type": MSG_TYPE_HELLO,
        "protocol_version": PROTOCOL_VERSION,
        "client": CLIENT_IDENTIFIER,
    })
    is_valid, parsed, err = validate_incoming_message(msg)
    assert is_valid is True
    assert parsed is not None
    assert parsed["client"] == CLIENT_IDENTIFIER
    assert err is None


def test_validate_valid_hello_bytes():
    """Test validation with UTF-8 encoded bytes."""
    msg_bytes = json.dumps({
        "type": MSG_TYPE_HELLO,
        "protocol_version": PROTOCOL_VERSION,
        "client": CLIENT_IDENTIFIER,
    }).encode("utf-8")
    is_valid, parsed, err = validate_incoming_message(msg_bytes)
    assert is_valid is True
    assert parsed is not None
    assert err is None


def test_validate_valid_product_result():
    """Test validation and parsing of valid product_result message."""
    raw_payload = {
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "data": {
            "url": "https://shopee.vn/product/12345/67890",
            "product_name": "Áo thun cotton cao cấp",
            "shop_id": "12345",
            "item_id": "67890",
            "images": [
                "https://down-vn.img.susercontent.com/file/img1.jpg",
                "https://down-vn.img.susercontent.com/file/img2.jpg",
            ],
        },
    }
    is_valid, parsed, err = validate_incoming_message(json.dumps(raw_payload))
    assert is_valid is True
    assert parsed is not None
    assert err is None

    product_data = parse_bridge_product_data(parsed)
    assert isinstance(product_data, BridgeProductData)
    assert product_data.url == "https://shopee.vn/product/12345/67890"
    assert product_data.product_name == "Áo thun cotton cao cấp"
    assert product_data.shop_id == "12345"
    assert product_data.item_id == "67890"
    assert len(product_data.images) == 2
    assert product_data.product_key == "12345:67890"


def test_validate_malformed_json():
    """Test rejection of malformed JSON strings."""
    is_valid, parsed, err = validate_incoming_message("NOT_JSON_DATA{}}")
    assert is_valid is False
    assert parsed is None
    assert "JSON không hợp lệ" in err


def test_validate_empty_message():
    """Test rejection of empty or None message."""
    is_valid, parsed, err = validate_incoming_message(None)
    assert is_valid is False
    assert "trống" in err

    is_valid, parsed, err = validate_incoming_message("")
    assert is_valid is False


def test_validate_oversized_message():
    """Test rejection of oversized messages exceeding safety cap."""
    oversized = "a" * (MAX_MESSAGE_SIZE + 100)
    is_valid, parsed, err = validate_incoming_message(oversized)
    assert is_valid is False
    assert "vượt quá giới hạn" in err


def test_validate_protocol_version_mismatch():
    """Test rejection when protocol version is unsupported."""
    msg = json.dumps({
        "type": MSG_TYPE_HELLO,
        "protocol_version": 999,
        "client": CLIENT_IDENTIFIER,
    })
    is_valid, parsed, err = validate_incoming_message(msg)
    assert is_valid is False
    assert "không được hỗ trợ" in err


def test_validate_missing_type():
    """Test rejection when 'type' field is missing or invalid."""
    msg = json.dumps({
        "protocol_version": PROTOCOL_VERSION,
        "client": CLIENT_IDENTIFIER,
    })
    is_valid, parsed, err = validate_incoming_message(msg)
    assert is_valid is False
    assert "Thiếu trường 'type'" in err


def test_validate_unknown_type():
    """Test rejection of unknown message types."""
    msg = json.dumps({
        "type": "custom_remote_eval",
        "protocol_version": PROTOCOL_VERSION,
    })
    is_valid, parsed, err = validate_incoming_message(msg)
    assert is_valid is False
    assert "không xác định" in err


def test_validate_missing_product_fields():
    """Test rejection when required fields are missing in product_result data."""
    # Missing product_name
    msg1 = json.dumps({
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "data": {
            "url": "https://shopee.vn/product",
            "shop_id": "123",
            "item_id": "456",
            "images": [],
        },
    })
    is_valid, parsed, err = validate_incoming_message(msg1)
    assert is_valid is False
    assert "product_name" in err

    # Missing shop_id
    msg2 = json.dumps({
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "data": {
            "url": "https://shopee.vn/product",
            "product_name": "Tên SP",
            "item_id": "456",
            "images": [],
        },
    })
    is_valid, parsed, err = validate_incoming_message(msg2)
    assert is_valid is False
    assert "shop_id" in err

    # Missing item_id
    msg3 = json.dumps({
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "data": {
            "url": "https://shopee.vn/product",
            "product_name": "Tên SP",
            "shop_id": "123",
            "images": [],
        },
    })
    is_valid, parsed, err = validate_incoming_message(msg3)
    assert is_valid is False
    assert "item_id" in err

    # Images not a list
    msg4 = json.dumps({
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "data": {
            "url": "https://shopee.vn/product",
            "product_name": "Tên SP",
            "shop_id": "123",
            "item_id": "456",
            "images": "not_a_list",
        },
    })
    is_valid, parsed, err = validate_incoming_message(msg4)
    assert is_valid is False
    assert "images" in err


def test_validate_batch_queue_messages():
    """Verify validation of process_url, process_progress, process_error, and cancel_processing."""
    from shopee_image_downloader.core.bridge_protocol import (
        MSG_TYPE_CANCEL_PROCESSING,
        MSG_TYPE_PROCESS_ERROR,
        MSG_TYPE_PROCESS_PROGRESS,
        MSG_TYPE_PROCESS_URL,
        MSG_TYPE_VERIFICATION_REQUIRED,
        create_cancel_processing_message,
        create_process_error_message,
        create_process_progress_message,
        create_process_url_message,
        create_verification_required_message,
    )

    # 1. process_url
    msg_url = create_process_url_message("req-123", "https://shopee.vn/test")
    is_valid, parsed, err = validate_incoming_message(msg_url)
    assert is_valid is True
    assert parsed["type"] == MSG_TYPE_PROCESS_URL
    assert parsed["request_id"] == "req-123"
    assert parsed["url"] == "https://shopee.vn/test"

    # 2. process_progress
    msg_prog = create_process_progress_message("req-123", "scanning_gallery")
    is_valid, parsed, err = validate_incoming_message(msg_prog)
    assert is_valid is True
    assert parsed["type"] == MSG_TYPE_PROCESS_PROGRESS
    assert parsed["stage"] == "scanning_gallery"

    # 3. process_error
    msg_err = create_process_error_message("req-123", "https://shopee.vn/test", "TIMEOUT", "Hết thời gian")
    is_valid, parsed, err = validate_incoming_message(msg_err)
    assert is_valid is True
    assert parsed["type"] == MSG_TYPE_PROCESS_ERROR
    assert parsed["error_code"] == "TIMEOUT"
    assert parsed["message"] == "Hết thời gian"

    # 4. cancel_processing
    msg_cancel = create_cancel_processing_message("req-123")
    is_valid, parsed, err = validate_incoming_message(msg_cancel)
    assert is_valid is True
    assert parsed["type"] == MSG_TYPE_CANCEL_PROCESSING

    # 5. verification_required
    msg_ver = create_verification_required_message("req-123", "https://shopee.vn/test")
    is_valid, parsed, err = validate_incoming_message(msg_ver)
    assert is_valid is True
    assert parsed["type"] == MSG_TYPE_VERIFICATION_REQUIRED


def test_validate_product_result_image_count_integrity_success():
    """Verify product_result with exact matching image_count passes validation and parses image_count."""
    payload = {
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "req-authoritative-9",
        "data": {
            "url": "https://shopee.vn/product-i.78513158.28469164720",
            "product_name": "Áo Thun Cotton",
            "shop_id": "78513158",
            "item_id": "28469164720",
            "images": [f"https://img.com/{i}.jpg" for i in range(1, 10)],
            "image_count": 9,
        },
    }
    is_valid, parsed, err = validate_incoming_message(json.dumps(payload))
    assert is_valid is True
    assert err is None
    data = parse_bridge_product_data(parsed)
    assert len(data.images) == 9
    assert data.image_count == 9


def test_validate_product_result_image_count_mismatch_rejected():
    """Verify product_result with mismatched image_count is rejected with PROTOCOL_INTEGRITY_ERROR."""
    payload = {
        "type": MSG_TYPE_PRODUCT_RESULT,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "req-mismatch",
        "data": {
            "url": "https://shopee.vn/product-i.78513158.28469164720",
            "product_name": "Áo Thun Cotton",
            "shop_id": "78513158",
            "item_id": "28469164720",
            "images": [f"https://img.com/{i}.jpg" for i in range(1, 5)],  # 4 images
            "image_count": 9,  # Declared 9 images -> MISMATCH!
        },
    }
    is_valid, parsed, err = validate_incoming_message(json.dumps(payload))
    assert is_valid is False
    assert "PROTOCOL_INTEGRITY_ERROR" in err

