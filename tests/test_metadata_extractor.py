"""Unit and integration tests for Shopee product metadata extractor, persistent session, and worker."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from shopee_image_downloader.core.browser_session import (
    STATUS_LOGIN_REQUIRED,
    PlaywrightSessionManager,
    get_default_browser_profile_dir,
    is_unauthenticated_page,
    is_unauthenticated_url,
)
from shopee_image_downloader.core.metadata_extractor import (
    ERROR_INVALID_URL,
    ERROR_NETWORK,
    ERROR_PRODUCT_NOT_FOUND,
    ERROR_VERIFICATION_REQUIRED,
    ProductMetadata,
    ShopeeMetadataExtractor,
    clean_product_name,
    extract_metadata_from_html,
    is_not_found_indicator,
    is_verification_indicator,
)
from shopee_image_downloader.core.url_resolver import ResolvedUrl, ShopeeUrlResolver
from shopee_image_downloader.workers.metadata_worker import MetadataExtractorWorker


class TestBrowserSessionHelpers:
    """Tests for persistent session and authentication detection utilities."""

    def test_default_browser_profile_dir(self) -> None:
        profile_dir = get_default_browser_profile_dir()
        assert profile_dir.name == "ChromeUserData"
        assert profile_dir.is_dir()

    def test_is_unauthenticated_url(self) -> None:
        assert is_unauthenticated_url(
            "https://shopee.vn/verify/traffic/error?home_url=https%3A%2F%2Fshopee.vn&is_logged_in=false&tracking_id=123"
        ) is True
        assert is_unauthenticated_url("https://shopee.vn/buyer/login") is True
        assert is_unauthenticated_url("https://shopee.vn/product/123/456") is False

    def test_is_unauthenticated_page(self) -> None:
        assert is_unauthenticated_page("https://shopee.vn/some-page", "Vui lòng đăng nhập Shopee. Cần đăng nhập để tiếp tục") is True
        assert is_unauthenticated_page("https://shopee.vn/some-page", "is_logged_in=false") is True
        assert is_unauthenticated_page("https://shopee.vn/product/123/456", "Áo thun nam cotton") is False


class TestCleanProductName:
    """Tests for clean_product_name sanitization."""

    def test_clean_normal_name(self) -> None:
        raw = "Áo Thun Nam Cổ Tròn Cotton 100%"
        assert clean_product_name(raw) == "Áo Thun Nam Cổ Tròn Cotton 100%"

    def test_clean_html_entities(self) -> None:
        raw = "Áo &amp; Quần Nam &quot;Cao Cấp&#39; 2024"
        assert clean_product_name(raw) == "Áo & Quần Nam \"Cao Cấp' 2024"

    def test_clean_shopee_brand_suffixes(self) -> None:
        cases = [
            ("Củ Sạc Anker 20W | Shopee Việt Nam", "Củ Sạc Anker 20W"),
            ("Củ Sạc Anker 20W | Shopee VN", "Củ Sạc Anker 20W"),
            ("Củ Sạc Anker 20W - Shopee Việt Nam", "Củ Sạc Anker 20W"),
            ("Củ Sạc Anker 20W | Shopee Singapore", "Củ Sạc Anker 20W"),
            ("Củ Sạc Anker 20W | Shopee Malaysia", "Củ Sạc Anker 20W"),
            ("Củ Sạc Anker 20W | Shopee", "Củ Sạc Anker 20W"),
        ]
        for raw, expected in cases:
            assert clean_product_name(raw) == expected

    def test_clean_whitespace_and_newlines(self) -> None:
        raw = "   Củ   Sạc \n\n Anker \t  20W   \n  "
        assert clean_product_name(raw) == "Củ Sạc Anker 20W"

    def test_reject_generic_placeholder_titles(self) -> None:
        generic_cases = [
            "Shopee Việt Nam | Mua và Bán Trên Ứng Dụng Di Động Hoặc Website",
            "Shopee Việt Nam",
            "Shopee VN",
            "Shopee",
            "Shopping Cart Icon",
            "404 Not Found",
            "Oops! Page not found",
            "Sản phẩm không tồn tại",
            "Sản phẩm đã bị xóa",
            "Robot Check",
            "Shopee Verification",
            "Captcha",
            "",
            "   \n  \t  ",
            None,
        ]
        for raw in generic_cases:
            assert clean_product_name(raw) is None


class TestExtractMetadataFromHtml:
    """Tests for HTML parsing logic."""

    def test_extract_from_json_ld_breadcrumbs(self) -> None:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "http://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "item": {"@id": "https://shopee.vn/", "name": "Shopee"}
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "item": {
                            "@id": "https://shopee.vn/Ao-Thun-Nam-i.12345.67890",
                            "name": "Áo Thun Nam Cao Cấp"
                        }
                    }
                ]
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        meta = extract_metadata_from_html(html_content, base_url="https://shopee.vn/Ao-Thun-Nam-i.12345.67890")
        assert meta is not None
        assert meta.product_name == "Áo Thun Nam Cao Cấp"
        assert meta.shop_id == "12345"
        assert meta.item_id == "67890"

    def test_extract_from_json_ld_product_schema(self) -> None:
        html_content = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "http://schema.org",
                "@type": "Product",
                "name": "Tai Nghe Bluetooth Không Dây",
                "description": "Tai nghe pin trâu"
            }
            </script>
        </head>
        </html>
        """
        meta = extract_metadata_from_html(
            html_content,
            base_url="https://shopee.vn/product/111/222",
            shop_id="111",
            item_id="222",
        )
        assert meta is not None
        assert meta.product_name == "Tai Nghe Bluetooth Không Dây"
        assert meta.shop_id == "111"
        assert meta.item_id == "222"

    def test_extract_from_og_title(self) -> None:
        html_content = """
        <html>
        <head>
            <meta property="og:title" content="Bàn Phím Cơ Không Dây | Shopee Việt Nam">
        </head>
        </html>
        """
        meta = extract_metadata_from_html(
            html_content,
            base_url="https://shopee.vn/product/333/444",
            shop_id="333",
            item_id="444",
        )
        assert meta is not None
        assert meta.product_name == "Bàn Phím Cơ Không Dây"

    def test_extract_from_title_tag(self) -> None:
        html_content = """
        <html>
        <head>
            <title>Chuột Gaming Siêu Nhẹ | Shopee Việt Nam</title>
        </head>
        </html>
        """
        meta = extract_metadata_from_html(
            html_content,
            base_url="https://shopee.vn/product/555/666",
            shop_id="555",
            item_id="666",
        )
        assert meta is not None
        assert meta.product_name == "Chuột Gaming Siêu Nhẹ"

    def test_extract_from_empty_or_generic_html(self) -> None:
        html_content = """
        <html>
        <head>
            <title>Shopee Việt Nam | Mua và Bán Trên Ứng Dụng Di Động Hoặc Website</title>
        </head>
        </html>
        """
        meta = extract_metadata_from_html(html_content, base_url="https://shopee.vn/product/123/456")
        assert meta is None


class TestShopeeMetadataExtractor:
    """Tests for ShopeeMetadataExtractor workflow, persistent session, and error handling."""

    def test_propagate_resolution_error(self) -> None:
        mock_resolver = MagicMock(spec=ShopeeUrlResolver)
        mock_resolver.resolve_url.return_value = ResolvedUrl(
            original_url="https://example.com/invalid",
            error="Link không phải địa chỉ Shopee hợp lệ",
        )

        extractor = ShopeeMetadataExtractor(resolver=mock_resolver, use_playwright_fallback=False)
        result = extractor.extract("https://example.com/invalid")

        assert result.error == "Link không phải địa chỉ Shopee hợp lệ"
        assert result.product_name is None

    def test_extract_http_success(self) -> None:
        mock_resolver = MagicMock(spec=ShopeeUrlResolver)
        mock_resolver.resolve_url.return_value = ResolvedUrl(
            original_url="https://shopee.vn/test-i.123.456",
            final_url="https://shopee.vn/test-i.123.456",
            shop_id="123",
            item_id="456",
            error=None,
        )

        sample_html = """
        <html>
        <head>
            <meta property="og:title" content="Loa Bluetooth Mini | Shopee Việt Nam">
        </head>
        </html>
        """.encode("utf-8")

        mock_response = MagicMock()
        mock_response.geturl.return_value = "https://shopee.vn/test-i.123.456"
        mock_response.read.return_value = sample_html
        mock_response.__enter__.return_value = mock_response

        extractor = ShopeeMetadataExtractor(resolver=mock_resolver, use_playwright_fallback=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = extractor.extract("https://shopee.vn/test-i.123.456")

        assert result.error is None
        assert result.product_name == "Loa Bluetooth Mini"
        assert result.shop_id == "123"
        assert result.item_id == "456"

    def test_extract_http_404_not_found(self) -> None:
        mock_resolver = MagicMock(spec=ShopeeUrlResolver)
        mock_resolver.resolve_url.return_value = ResolvedUrl(
            original_url="https://shopee.vn/product/123/456",
            final_url="https://shopee.vn/product/123/456",
            shop_id="123",
            item_id="456",
        )

        http_404 = urllib.error.HTTPError(
            url="https://shopee.vn/product/123/456",
            code=404,
            msg="Not Found",
            hdrs={},  # type: ignore[arg-type]
            fp=None,
        )

        extractor = ShopeeMetadataExtractor(resolver=mock_resolver, use_playwright_fallback=False)
        with patch("urllib.request.urlopen", side_effect=http_404):
            result = extractor.extract("https://shopee.vn/product/123/456")

        assert result.error == ERROR_PRODUCT_NOT_FOUND
        assert result.product_name is None

    def test_regression_fake_url_rejected_when_empty_shell(self) -> None:
        """Regression test for structurally valid but non-existent fake URL."""
        fake_url = "https://shopee.vn/A--i.1439789223.43705417224"
        mock_resolver = MagicMock(spec=ShopeeUrlResolver)
        mock_resolver.resolve_url.return_value = ResolvedUrl(
            original_url=fake_url,
            final_url=fake_url,
            shop_id="1439789223",
            item_id="43705417224",
        )

        empty_shell_html = """
        <!doctype html><html><head>
        <title>Shopee Việt Nam | Mua và Bán Trên Ứng Dụng Di Động Hoặc Website</title>
        </head><body><div id="main"></div></body></html>
        """.encode("utf-8")

        mock_response = MagicMock()
        mock_response.geturl.return_value = fake_url
        mock_response.read.return_value = empty_shell_html
        mock_response.__enter__.return_value = mock_response

        extractor = ShopeeMetadataExtractor(resolver=mock_resolver, use_playwright_fallback=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = extractor.extract(fake_url)

        assert result.error == ERROR_PRODUCT_NOT_FOUND
        assert result.product_name is None

    def test_persistent_browser_unauthenticated_prompts_login_and_succeeds(self) -> None:
        """Test flow when session is unauthenticated, prompts manual login, and succeeds."""
        url = "https://shopee.vn/product/100/200"
        mock_resolver = MagicMock(spec=ShopeeUrlResolver)
        mock_resolver.resolve_url.return_value = ResolvedUrl(
            original_url=url,
            final_url=url,
            shop_id="100",
            item_id="200",
        )

        mock_session_mgr = MagicMock(spec=PlaywrightSessionManager)
        mock_session_mgr.wait_for_manual_login.return_value = True

        mock_page = MagicMock()
        mock_page.url = "https://shopee.vn/verify/traffic/error?is_logged_in=false"
        mock_page.content.return_value = "<html><body>Cần đăng nhập Shopee</body></html>"

        extractor = ShopeeMetadataExtractor(
            resolver=mock_resolver,
            session_manager=mock_session_mgr,
            use_playwright_fallback=True,
        )

        with patch.object(
            extractor,
            "extract_from_page",
            return_value=ProductMetadata(
                product_name="Cáp Sạc Nhanh Type-C 65W",
                shop_id="100",
                item_id="200",
                final_url=url,
                error=None,
            ),
        ):
            result = extractor.extract(url, page=mock_page)

        assert result.error is None
        assert result.product_name == "Cáp Sạc Nhanh Type-C 65W"
        assert result.shop_id == "100"
        assert result.item_id == "200"

    def test_persistent_browser_unauthenticated_login_cancelled(self) -> None:
        """Test flow when user closes browser or cancels login."""
        url = "https://shopee.vn/product/100/200"
        mock_resolver = MagicMock(spec=ShopeeUrlResolver)
        mock_resolver.resolve_url.return_value = ResolvedUrl(
            original_url=url,
            final_url=url,
            shop_id="100",
            item_id="200",
        )

        mock_session_mgr = MagicMock(spec=PlaywrightSessionManager)
        mock_session_mgr.wait_for_manual_login.return_value = False

        mock_page = MagicMock()
        mock_page.url = "https://shopee.vn/verify/traffic/error?is_logged_in=false"
        mock_page.content.return_value = "<html><body>is_logged_in=false</body></html>"

        extractor = ShopeeMetadataExtractor(
            resolver=mock_resolver,
            session_manager=mock_session_mgr,
            use_playwright_fallback=True,
        )

        result = extractor.extract(url, page=mock_page)
        assert result is not None
        assert result.error == STATUS_LOGIN_REQUIRED
        assert result.product_name is None


class TestMetadataExtractorWorker:
    """Tests for background QThread MetadataExtractorWorker."""

    def test_worker_processes_batch_resiliently(self) -> None:
        items = [
            (0, "https://shopee.vn/valid-product-1"),
            (1, "https://shopee.vn/invalid-product-2"),
            (2, "https://shopee.vn/valid-product-3"),
        ]

        def mock_extract(url: str, page=None, on_status_change=None) -> ProductMetadata:
            if "valid-product-1" in url:
                return ProductMetadata(
                    product_name="Sản Phẩm Số 1",
                    shop_id="111",
                    item_id="222",
                    final_url=url,
                )
            if "invalid-product-2" in url:
                return ProductMetadata(
                    final_url=url,
                    error=ERROR_PRODUCT_NOT_FOUND,
                )
            return ProductMetadata(
                product_name="Sản Phẩm Số 3",
                shop_id="333",
                item_id="444",
                final_url=url,
            )

        mock_extractor = MagicMock(spec=ShopeeMetadataExtractor)
        mock_extractor.extract.side_effect = mock_extract

        worker = MetadataExtractorWorker(items=items, extractor=mock_extractor)

        started_events: list[tuple[int, str]] = []
        status_events: list[tuple[int, str]] = []
        completed_events: list[tuple[int, ProductMetadata]] = []
        progress_events: list[tuple[int, int]] = []
        batch_finished_events: list[list[ProductMetadata]] = []

        worker.item_started.connect(lambda r, u: started_events.append((r, u)))
        worker.item_status_updated.connect(lambda r, s: status_events.append((r, s)))
        worker.item_completed.connect(lambda r, m: completed_events.append((r, m)))
        worker.progress_updated.connect(lambda c, t: progress_events.append((c, t)))
        worker.batch_finished.connect(lambda results: batch_finished_events.append(results))

        # Run synchronously for test
        worker.run()

        assert len(started_events) == 3
        assert len(status_events) == 3
        assert len(completed_events) == 3
        assert len(progress_events) == 3
        assert len(batch_finished_events) == 1

        results = batch_finished_events[0]
        assert len(results) == 3
        assert results[0].product_name == "Sản Phẩm Số 1"
        assert results[1].error == ERROR_PRODUCT_NOT_FOUND
        assert results[2].product_name == "Sản Phẩm Số 3"
