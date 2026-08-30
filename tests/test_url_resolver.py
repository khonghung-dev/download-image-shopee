"""Unit tests for Shopee URL resolver, ID extraction, tracking parameter cleaning, and worker."""

from unittest.mock import MagicMock, patch
import urllib.error
import socket

from shopee_image_downloader.core.url_resolver import (
    ResolvedUrl,
    ShopeeUrlResolver,
    clean_tracking_params,
    extract_ids_from_url,
)
from shopee_image_downloader.workers.url_resolver_worker import UrlResolverWorker


def _make_mock_response(url: str) -> MagicMock:
    """Helper to construct a mock urllib response with __enter__ and geturl."""
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.geturl.return_value = str(url)
    return mock_resp


def test_extract_ids_dash_i_pattern() -> None:
    """Verify extraction of shop_id and item_id from standard -i.shop_id.item_id pattern."""
    url = "https://shopee.vn/Ao-Thun-Nam-Cotton-Form-Rong-i.12345678.9876543210"
    shop_id, item_id = extract_ids_from_url(url)
    assert shop_id == "12345678"
    assert item_id == "9876543210"


def test_extract_ids_product_path() -> None:
    """Verify extraction of shop_id and item_id from /product/shop_id/item_id pattern."""
    url = "https://shopee.vn/product/87654321/1122334455"
    shop_id, item_id = extract_ids_from_url(url)
    assert shop_id == "87654321"
    assert item_id == "1122334455"


def test_extract_ids_legacy_dot() -> None:
    """Verify extraction of shop_id and item_id from legacy .shop_id.item_id pattern."""
    url = "https://shopee.vn/Giay-The-Thao-Nam.55667788.99887766"
    shop_id, item_id = extract_ids_from_url(url)
    assert shop_id == "55667788"
    assert item_id == "99887766"


def test_extract_ids_query_params() -> None:
    """Verify extraction of shop_id and item_id from query parameters."""
    url = "https://shopee.vn/product?shop_id=999888&item_id=777666"
    shop_id, item_id = extract_ids_from_url(url)
    assert shop_id == "999888"
    assert item_id == "777666"


def test_extract_ids_not_found() -> None:
    """Verify returning (None, None) for non-product URLs."""
    url = "https://shopee.vn/daily_discover"
    shop_id, item_id = extract_ids_from_url(url)
    assert shop_id is None
    assert item_id is None


def test_clean_tracking_params() -> None:
    """Verify removal of tracking query parameters and fragments while preserving destination."""
    dirty_url = (
        "https://shopee.vn/Ao-Thun-i.123.456"
        "?sp_atk=349d7990-bfae-4f36-b7ff-15335d106622"
        "&utm_source=facebook&utm_medium=cpc&utm_campaign=summer_sale"
        "&xptdk=349d7990&gclid=Cj0KCQj&fbclid=IwAR2"
        "#reviews"
    )
    cleaned = clean_tracking_params(dirty_url)
    assert cleaned == "https://shopee.vn/Ao-Thun-i.123.456"


def test_clean_tracking_params_preserves_custom_query() -> None:
    """Verify non-tracking parameters are retained when appropriate."""
    url = "https://shopee.vn/search?keyword=ao+thun&utm_source=google"
    cleaned = clean_tracking_params(url)
    assert cleaned == "https://shopee.vn/search?keyword=ao+thun"


def test_resolve_normal_shopee_url_success() -> None:
    """Verify resolving a standard Shopee product URL."""
    resolver = ShopeeUrlResolver()
    target_url = "https://shopee.vn/Ao-Thun-i.12345.67890?sp_atk=abc123"

    mock_resp = _make_mock_response(target_url)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = resolver.resolve_url(target_url)

    assert result.error is None
    assert result.original_url == target_url
    assert result.final_url == "https://shopee.vn/Ao-Thun-i.12345.67890"
    assert result.shop_id == "12345"
    assert result.item_id == "67890"


def test_resolve_shortened_url_success() -> None:
    """Verify resolving a shortened s.shopee.vn link to its final destination."""
    resolver = ShopeeUrlResolver()
    short_url = "https://s.shopee.vn/6AV2mK8s01"
    redirected_url = "https://shopee.vn/universal-link/Vay-Nu-Xinh-i.998877.112233?sp_atk=def456"

    mock_resp = _make_mock_response(redirected_url)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = resolver.resolve_url(short_url)

    assert result.error is None
    assert result.original_url == short_url
    assert result.final_url == "https://shopee.vn/universal-link/Vay-Nu-Xinh-i.998877.112233"
    assert result.shop_id == "998877"
    assert result.item_id == "112233"


def test_resolve_non_shopee_url_rejected() -> None:
    """Verify non-Shopee URLs are rejected without network request."""
    resolver = ShopeeUrlResolver()
    result = resolver.resolve_url("https://lazada.vn/some-product")
    assert result.error == "Link không phải địa chỉ Shopee hợp lệ"
    assert result.final_url is None


def test_resolve_empty_url() -> None:
    """Verify empty input is handled cleanly."""
    resolver = ShopeeUrlResolver()
    result = resolver.resolve_url("   ")
    assert result.error == "URL trống"
    assert result.final_url is None


def test_resolve_http_error() -> None:
    """Verify HTTP error (e.g. 404) returns a clear error message without raising exceptions."""
    resolver = ShopeeUrlResolver()
    target_url = "https://shopee.vn/product/123/456"

    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(target_url, 404, "Not Found", {}, None)):
        result = resolver.resolve_url(target_url)

    assert result.error == "HTTP 404: Not Found"
    assert result.final_url is None


def test_resolve_network_url_error() -> None:
    """Verify URLError (e.g. DNS or connection failure) returns an error message."""
    resolver = ShopeeUrlResolver()
    target_url = "https://shopee.vn/product/123/456"

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        result = resolver.resolve_url(target_url)

    assert "Lỗi mạng" in (result.error or "")
    assert result.final_url is None


def test_resolve_timeout_error() -> None:
    """Verify TimeoutError returns a descriptive timeout error message."""
    resolver = ShopeeUrlResolver()
    target_url = "https://shopee.vn/product/123/456"

    with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
        result = resolver.resolve_url(target_url)

    assert result.error == "Quá thời gian kết nối (Timeout)"
    assert result.final_url is None


def test_resolve_batch_mixed_resilience() -> None:
    """Verify that a failure on one URL does not stop subsequent URLs in batch."""
    resolver = ShopeeUrlResolver()
    urls = [
        "https://shopee.vn/product-1-i.111.222",
        "https://shopee.vn/error-product",
        "https://shopee.vn/product-3-i.333.444",
    ]

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "error-product" in url:
            raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)
        return _make_mock_response(url)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        results = resolver.resolve_batch(urls)

    assert len(results) == 3
    assert results[0].error is None
    assert results[0].shop_id == "111"
    assert results[0].item_id == "222"

    assert results[1].error == "HTTP 500: Internal Server Error"
    assert results[1].final_url is None

    assert results[2].error is None
    assert results[2].shop_id == "333"
    assert results[2].item_id == "444"


def test_url_resolver_worker_execution() -> None:
    """Verify UrlResolverWorker emits all lifecycle signals accurately."""
    mock_resolver = MagicMock()
    mock_resolver.resolve_url.side_effect = [
        ResolvedUrl(original_url="https://shopee.vn/p1", final_url="https://shopee.vn/p1-i.1.2", shop_id="1", item_id="2"),
        ResolvedUrl(original_url="https://shopee.vn/p2", error="HTTP 404: Not Found"),
    ]

    worker = UrlResolverWorker(
        items=[(0, "https://shopee.vn/p1"), (1, "https://shopee.vn/p2")],
        resolver=mock_resolver,
    )

    started_events: list[tuple[int, str]] = []
    resolved_events: list[tuple[int, ResolvedUrl]] = []
    progress_events: list[tuple[int, int]] = []
    finished_results: list[list[ResolvedUrl]] = []

    worker.item_started.connect(lambda row, url: started_events.append((row, url)))
    worker.item_resolved.connect(lambda row, res: resolved_events.append((row, res)))
    worker.progress_updated.connect(lambda c, t: progress_events.append((c, t)))
    worker.batch_finished.connect(lambda res_list: finished_results.append(res_list))

    worker.run()

    assert started_events == [(0, "https://shopee.vn/p1"), (1, "https://shopee.vn/p2")]
    assert len(resolved_events) == 2
    assert resolved_events[0][1].shop_id == "1"
    assert resolved_events[1][1].error == "HTTP 404: Not Found"
    assert progress_events == [(1, 2), (2, 2)]
    assert len(finished_results) == 1
    assert len(finished_results[0]) == 2


def test_url_resolver_worker_interruption() -> None:
    """Verify UrlResolverWorker halts gracefully when interruption/cancellation is requested."""
    mock_resolver = MagicMock()
    mock_resolver.resolve_url.side_effect = lambda url: ResolvedUrl(original_url=url, final_url=url)

    worker = UrlResolverWorker(
        items=[(0, "https://shopee.vn/p1"), (1, "https://shopee.vn/p2"), (2, "https://shopee.vn/p3")],
        resolver=mock_resolver,
    )
    worker.cancel()
    worker.run()

    # Since interruption was requested before loop, no items should be processed
    assert mock_resolver.resolve_url.call_count == 0


def test_clean_tracking_params_encoded_vietnamese_slug() -> None:
    """Verify cleaning tracking params from URL-encoded Vietnamese slug."""
    encoded_url = "https://shopee.vn/%C3%81o-thun-nam-cotton-i.12345.67890?sp_atk=abc&utm_source=fb"
    cleaned = clean_tracking_params(encoded_url)
    assert cleaned == "https://shopee.vn/%C3%81o-thun-nam-cotton-i.12345.67890"
    shop_id, item_id = extract_ids_from_url(cleaned)
    assert shop_id == "12345"
    assert item_id == "67890"


# --- Regression Tests for Task 005 Acceptance Fixes ---

def test_regression_valid_dash_i_product_url() -> None:
    """Regression Test 1: Valid -i.<shop_id>.<item_id> product URL resolves successfully."""
    resolver = ShopeeUrlResolver()
    url = "https://shopee.vn/Ao-Thun-Cotton-Cao-Cap-i.12345678.987654321"

    mock_resp = _make_mock_response(url)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = resolver.resolve_url(url)

    assert result.error is None
    assert result.final_url == url
    assert result.shop_id == "12345678"
    assert result.item_id == "987654321"


def test_regression_generic_non_product_url_rejected() -> None:
    """Regression Test 2: Shopee generic/non-product URL is rejected even if HTTP 200."""
    resolver = ShopeeUrlResolver()
    url = "https://shopee.vn/abcxyz"

    mock_resp = _make_mock_response(url)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = resolver.resolve_url(url)

    assert result.error == "URL không phải link sản phẩm Shopee hợp lệ"
    assert result.final_url is None
    assert result.shop_id is None
    assert result.item_id is None


def test_regression_short_url_resolving_to_error_page_rejected() -> None:
    """Regression Test 3: Short URL resolving to error page (e.g. shopee.ee/error_page) is rejected."""
    resolver = ShopeeUrlResolver()
    short_url = "https://s.shopee.vn/invalidcode"
    error_destination = "https://shopee.ee/error_page"

    mock_resp = _make_mock_response(error_destination)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = resolver.resolve_url(short_url)

    assert result.error == "Link chuyển hướng đến trang lỗi Shopee (error_page)"
    assert result.final_url is None
    assert result.shop_id is None
    assert result.item_id is None


def test_regression_valid_short_url_resolving_to_product() -> None:
    """Regression Test 4: Valid short URL resolving to product page is accepted with IDs."""
    resolver = ShopeeUrlResolver()
    short_url = "https://s.shopee.vn/6AV2mK8s01"
    product_destination = "https://shopee.vn/universal-link/Ao-Thun-Nam-i.777888.999000?sp_atk=trace123"

    mock_resp = _make_mock_response(product_destination)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = resolver.resolve_url(short_url)

    assert result.error is None
    assert result.final_url == "https://shopee.vn/universal-link/Ao-Thun-Nam-i.777888.999000"
    assert result.shop_id == "777888"
    assert result.item_id == "999000"


