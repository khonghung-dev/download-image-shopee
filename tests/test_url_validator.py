"""Unit tests for Shopee URL validation, parsing, and deduplication logic."""

import pytest
from shopee_image_downloader.core.url_validator import (
    STATUS_INVALID,
    STATUS_PENDING,
    ParsedUrl,
    is_shopee_vn_url,
    parse_url_lines,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://shopee.vn/product-name-i.123456.7891011",
        "http://shopee.vn/ao-thun-nam-i.111.222",
        "shopee.vn/universal-link/product-name-i.123.456",
        "https://www.shopee.vn/some-product-i.999.888",
        "https://vn.shopee.vn/product/123/456",
        "http://sub.domain.shopee.vn/item-i.1.2",
    ],
)
def test_valid_normal_shopee_urls(url: str) -> None:
    """Verify standard Shopee Vietnam URLs are identified as valid."""
    assert is_shopee_vn_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://s.shopee.vn/12345XYZ",
        "http://s.shopee.vn/abcdef",
        "s.shopee.vn/link123",
        "https://s.shopee.vn/abc?share_channel_code=1",
    ],
)
def test_valid_shortened_shopee_urls(url: str) -> None:
    """Verify shortened Shopee URLs (s.shopee.vn) are identified as valid."""
    assert is_shopee_vn_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://lazada.vn/products/item-123.html",
        "https://tiki.vn/san-pham-p123.html",
        "https://google.com",
        "https://fake-shopee.vn/item-1",
        "https://shopee.vn.evilattacker.com/item-1",
        "shopee.com/product",
        "https://shopee.sg/product",
        "random non url string",
        "ftp://shopee.vn/product",
        "",
        "   ",
    ],
)
def test_invalid_non_shopee_urls(url: str) -> None:
    """Verify non-Shopee URLs and invalid strings are rejected."""
    assert is_shopee_vn_url(url) is False


def test_parse_url_lines_with_whitespace_and_empty_lines() -> None:
    """Verify lines with leading/trailing whitespace and blank lines are handled properly."""
    input_text = """
    
        https://shopee.vn/product-1    
        
        https://s.shopee.vn/shortlink1  
        
    """
    results = parse_url_lines(input_text)
    assert len(results) == 2
    assert results[0] == ParsedUrl(
        url="https://shopee.vn/product-1",
        is_valid=True,
        status=STATUS_PENDING,
    )
    assert results[1] == ParsedUrl(
        url="https://s.shopee.vn/shortlink1",
        is_valid=True,
        status=STATUS_PENDING,
    )


def test_parse_url_lines_deduplication_preserves_order() -> None:
    """Verify exact duplicate URLs are removed while preserving the original input order."""
    input_text = """https://shopee.vn/item-1
https://shopee.vn/item-2
https://shopee.vn/item-1
https://s.shopee.vn/item-3
https://shopee.vn/item-2
https://shopee.vn/item-1"""

    results = parse_url_lines(input_text)
    assert len(results) == 3
    assert [item.url for item in results] == [
        "https://shopee.vn/item-1",
        "https://shopee.vn/item-2",
        "https://s.shopee.vn/item-3",
    ]
    assert all(item.is_valid for item in results)
    assert all(item.status == STATUS_PENDING for item in results)


def test_parse_url_lines_mixed_valid_and_invalid() -> None:
    """Verify that a batch with mixed valid and invalid URLs assigns correct statuses."""
    input_text = """https://shopee.vn/valid-product
https://lazada.vn/invalid-item
   https://s.shopee.vn/valid-shortlink   
not-a-valid-url
https://shopee.vn/another-valid"""

    results = parse_url_lines(input_text)
    assert len(results) == 5

    assert results[0].url == "https://shopee.vn/valid-product"
    assert results[0].is_valid is True
    assert results[0].status == STATUS_PENDING

    assert results[1].url == "https://lazada.vn/invalid-item"
    assert results[1].is_valid is False
    assert results[1].status == STATUS_INVALID

    assert results[2].url == "https://s.shopee.vn/valid-shortlink"
    assert results[2].is_valid is True
    assert results[2].status == STATUS_PENDING

    assert results[3].url == "not-a-valid-url"
    assert results[3].is_valid is False
    assert results[3].status == STATUS_INVALID

    assert results[4].url == "https://shopee.vn/another-valid"
    assert results[4].is_valid is True
    assert results[4].status == STATUS_PENDING


def test_parse_url_lines_empty_input() -> None:
    """Verify empty or whitespace-only input returns empty list."""
    assert parse_url_lines("") == []
    assert parse_url_lines("   \n\n  \t  \n  ") == []
