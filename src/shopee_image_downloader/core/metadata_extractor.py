"""Product metadata extraction module for Shopee listings.

Extracts real product metadata (product_name, shop_id, item_id, final_url, error)
using structured page data (JSON-LD, OpenGraph tags, page titles, DOM elements)
via HTTP requests and Playwright persistent browser sessions.
"""

from collections.abc import Callable
from dataclasses import dataclass
import html
import json
import logging
import re
import socket
import urllib.error
import urllib.request

from shopee_image_downloader.core.browser_session import (
    STATUS_LOGIN_REQUIRED,
    PlaywrightSessionManager,
    is_unauthenticated_page,
    is_unauthenticated_url,
)
from shopee_image_downloader.core.url_resolver import (
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    ResolvedUrl,
    ShopeeUrlResolver,
    extract_ids_from_url,
    is_error_page_url,
)

logger = logging.getLogger(__name__)

# Standard error messages
ERROR_VERIFICATION_REQUIRED: str = "Shopee yêu cầu xác minh"
ERROR_PRODUCT_NOT_FOUND: str = "Không tìm thấy sản phẩm"
ERROR_INVALID_URL: str = "URL không hợp lệ"
ERROR_NETWORK: str = "Lỗi kết nối mạng"

# Generic titles that do not represent an actual product name
GENERIC_TITLES: frozenset[str] = frozenset(
    {
        "shopee việt nam | mua và bán trên ứng dụng di động hoặc website",
        "shopee việt nam",
        "shopee vn",
        "shopee",
        "shopping cart icon",
        "shopee singapore",
        "shopee malaysia",
        "shopee philippines",
        "shopee thailand",
        "shopee indonesia",
        "shopee taiwan",
        "oops! page not found",
        "trang không tìm thấy",
        "trang không tồn tại",
        "sản phẩm không tồn tại",
        "sản phẩm đã bị xóa",
        "404 not found",
        "robot check",
        "shopee verification",
        "captcha",
    }
)

# Regex to remove Shopee brand suffixes
_RE_SHOPEE_SUFFIX = re.compile(
    r"\s*(?:[|–—-]\s*)Shopee(?:\s+(?:Việt\s+Nam|VN|Singapore|Malaysia|Philippines|Thailand|Indonesia|Taiwan|[A-Za-z]+))?.*$",
    re.IGNORECASE,
)

# Regex for JSON-LD and meta tags
_RE_JSON_LD = re.compile(
    r'<script\b[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_RE_OG_TITLE = re.compile(
    r'<meta\b[^>]*property=[\'"](?:og:title|twitter:title)[\'"][^>]*content=[\'"](.*?)[\'"][^>]*>',
    re.IGNORECASE,
)
_RE_OG_TITLE_ALT = re.compile(
    r'<meta\b[^>]*content=[\'"](.*?)[\'"][^>]*property=[\'"](?:og:title|twitter:title)[\'"][^>]*>',
    re.IGNORECASE,
)
_RE_TITLE_TAG = re.compile(r"<title\b[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ProductMetadata:
    """Represents extracted metadata for a Shopee product listing."""

    product_name: str | None = None
    shop_id: str | None = None
    item_id: str | None = None
    final_url: str | None = None
    error: str | None = None


def clean_product_name(raw_name: str | None) -> str | None:
    """Sanitize and normalize a raw product name extracted from HTML/JSON.

    - Unescapes HTML entities.
    - Strips trailing Shopee brand suffixes (e.g. ` | Shopee Việt Nam`).
    - Collapses consecutive whitespace and trims ends.
    - Rejects generic homepage/placeholder titles.

    Returns:
        Cleaned product name string, or None if invalid/generic.
    """
    if not raw_name:
        return None

    # Unescape HTML entities (e.g. &amp; -> &, &#39; -> ')
    name = html.unescape(raw_name)

    # Remove trailing Shopee suffix
    name = _RE_SHOPEE_SUFFIX.sub("", name)

    # Normalize whitespace
    name = re.sub(r"\s+", " ", name).strip()

    if not name:
        return None

    # Check against generic placeholder titles
    if name.lower() in GENERIC_TITLES:
        return None

    # Check for short generic prefixes
    if name.lower().startswith("shopee việt nam |"):
        return None

    return name


def is_verification_indicator(url: str, content: str = "") -> bool:
    """Check whether a URL or response content indicates a human verification challenge."""
    if not url:
        return False

    url_lower = url.lower()
    # Note: verify/traffic with is_logged_in=false is handled separately as authentication required
    if is_unauthenticated_url(url):
        return False

    if "/verify" in url_lower or "/robot" in url_lower:
        return True

    if content:
        content_lower = content.lower()
        if (
            "shopee verification" in content_lower
            or "vui lòng xác minh" in content_lower
            or "robot check" in content_lower
            or "security check" in content_lower
        ):
            return True

    return False


def is_not_found_indicator(title: str = "") -> bool:
    """Check whether a page title indicates a deleted or non-existent product."""
    if not title:
        return False
    title_lower = title.lower().strip()
    return title_lower in GENERIC_TITLES or "404 not found" in title_lower or "page not found" in title_lower


def extract_metadata_from_html(
    html_content: str,
    base_url: str | None = None,
    shop_id: str | None = None,
    item_id: str | None = None,
) -> ProductMetadata | None:
    """Attempt extraction of product metadata from static HTML content.

    Inspects:
    1. Schema.org JSON-LD scripts (BreadcrumbList, Product)
    2. OpenGraph / Twitter meta tags
    3. HTML <title> tag

    Returns:
        ProductMetadata if a valid product name is found, otherwise None.
    """
    if not html_content:
        return None

    extracted_name: str | None = None
    extracted_shop_id: str | None = shop_id
    extracted_item_id: str | None = item_id

    # 1. Search JSON-LD scripts
    for script_match in _RE_JSON_LD.finditer(html_content):
        script_text = script_match.group(1).strip()
        if not script_text:
            continue
        try:
            data = json.loads(script_text)
            if not isinstance(data, (dict, list)):
                continue

            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                entry_type = str(entry.get("@type", "")).lower()

                # Case A: BreadcrumbList (leaf item is usually the product)
                if entry_type == "breadcrumblist":
                    items = entry.get("itemListElement", [])
                    if isinstance(items, list) and items:
                        last_item = items[-1]
                        if isinstance(last_item, dict):
                            candidate_name = None
                            nested_item = last_item.get("item")
                            if isinstance(nested_item, dict):
                                candidate_name = nested_item.get("name")
                                item_url = nested_item.get("@id") or nested_item.get("url")
                                if item_url:
                                    s_id, i_id = extract_ids_from_url(str(item_url))
                                    if s_id and i_id:
                                        extracted_shop_id = s_id
                                        extracted_item_id = i_id
                            if not candidate_name:
                                candidate_name = last_item.get("name")

                            cleaned = clean_product_name(candidate_name)
                            if cleaned:
                                extracted_name = cleaned
                                break

                # Case B: Product schema
                elif entry_type == "product":
                    candidate_name = entry.get("name")
                    cleaned = clean_product_name(candidate_name)
                    if cleaned:
                        extracted_name = cleaned
                        break

            if extracted_name:
                break
        except Exception:
            continue

    # 2. Search OpenGraph and Twitter meta tags
    if not extracted_name:
        og_matches = _RE_OG_TITLE.findall(html_content) + _RE_OG_TITLE_ALT.findall(html_content)
        for og_content in og_matches:
            cleaned = clean_product_name(og_content)
            if cleaned:
                extracted_name = cleaned
                break

    # 3. Search <title> tag
    if not extracted_name:
        title_match = _RE_TITLE_TAG.search(html_content)
        if title_match:
            cleaned = clean_product_name(title_match.group(1))
            if cleaned:
                extracted_name = cleaned

    if extracted_name:
        return ProductMetadata(
            product_name=extracted_name,
            shop_id=extracted_shop_id,
            item_id=extracted_item_id,
            final_url=base_url,
            error=None,
        )

    return None


class ShopeeMetadataExtractor:
    """Extracts product metadata from resolved Shopee product URLs and rendered pages."""

    def __init__(
        self,
        resolver: ShopeeUrlResolver | None = None,
        session_manager: PlaywrightSessionManager | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str | None = None,
        use_playwright_fallback: bool = True,
    ) -> None:
        self.resolver = resolver or ShopeeUrlResolver(timeout=timeout, user_agent=user_agent)
        self.session_manager = session_manager or PlaywrightSessionManager(
            user_agent=user_agent, timeout=timeout
        )
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.use_playwright_fallback = use_playwright_fallback

    def extract_from_page(
        self,
        page,
        shop_id: str | None = None,
        item_id: str | None = None,
    ) -> ProductMetadata:
        """Extract product metadata from an active Playwright page in the persistent session."""
        current_url = page.url
        content = page.content()

        # 1. Verification check (non-login captcha challenge)
        if is_verification_indicator(current_url, content):
            return ProductMetadata(
                shop_id=shop_id,
                item_id=item_id,
                final_url=current_url,
                error=ERROR_VERIFICATION_REQUIRED,
            )

        extracted_name: str | None = None
        extracted_shop_id: str | None = shop_id
        extracted_item_id: str | None = item_id

        # 3. Check JSON-LD in DOM
        ld_elements = page.query_selector_all('script[type="application/ld+json"]')
        for el in ld_elements:
            txt = el.text_content()
            if not txt:
                continue
            try:
                data = json.loads(txt)
                entries = data if isinstance(data, list) else [data]
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    etype = str(entry.get("@type", "")).lower()
                    if etype == "breadcrumblist":
                        items = entry.get("itemListElement", [])
                        if isinstance(items, list) and items:
                            last_item = items[-1]
                            if isinstance(last_item, dict):
                                c_name = None
                                nested = last_item.get("item")
                                if isinstance(nested, dict):
                                    c_name = nested.get("name")
                                    item_url = nested.get("@id") or nested.get("url")
                                    if item_url:
                                        s_id, i_id = extract_ids_from_url(str(item_url))
                                        if s_id and i_id:
                                            extracted_shop_id = s_id
                                            extracted_item_id = i_id
                                if not c_name:
                                    c_name = last_item.get("name")
                                cleaned = clean_product_name(c_name)
                                if cleaned:
                                    extracted_name = cleaned
                                    break
                    elif etype == "product":
                        cleaned = clean_product_name(entry.get("name"))
                        if cleaned:
                            extracted_name = cleaned
                            break
                if extracted_name:
                    break
            except Exception:
                continue

        # 4. Check OpenGraph meta tag
        if not extracted_name:
            og_el = page.query_selector('meta[property="og:title"], meta[name="twitter:title"]')
            if og_el:
                c_name = og_el.get_attribute("content")
                cleaned = clean_product_name(c_name)
                if cleaned:
                    extracted_name = cleaned

        # 5. Check DOM headings and product title selectors
        if not extracted_name:
            for selector in [
                "h1",
                "span.x-product-name",
                "div._44qnta",
                "div.V3eGg6",
                "div[class*='product-briefing'] h1",
            ]:
                el = page.query_selector(selector)
                if el:
                    txt = el.text_content()
                    cleaned = clean_product_name(txt)
                    if cleaned:
                        extracted_name = cleaned
                        break

        # 6. Check page title
        if not extracted_name:
            page_title = page.title()
            cleaned = clean_product_name(page_title)
            if cleaned:
                extracted_name = cleaned

        if extracted_name:
            return ProductMetadata(
                product_name=extracted_name,
                shop_id=extracted_shop_id,
                item_id=extracted_item_id,
                final_url=current_url,
                error=None,
            )
        else:
            return ProductMetadata(
                shop_id=shop_id,
                item_id=item_id,
                final_url=current_url,
                error=ERROR_PRODUCT_NOT_FOUND,
            )

    def extract(
        self,
        target: str | ResolvedUrl,
        page=None,
        on_status_change: Callable[[str], None] | None = None,
    ) -> ProductMetadata:
        """Extract metadata for a Shopee URL via persistent browser page (if provided) or HTTP."""
        if isinstance(target, str):
            resolved = self.resolver.resolve_url(target)
        else:
            resolved = target

        if resolved.error is not None:
            return ProductMetadata(
                shop_id=resolved.shop_id,
                item_id=resolved.item_id,
                final_url=resolved.final_url or resolved.original_url,
                error=resolved.error,
            )

        final_url = resolved.final_url or resolved.original_url
        shop_id = resolved.shop_id
        item_id = resolved.item_id

        if is_error_page_url(final_url):
            return ProductMetadata(
                shop_id=shop_id,
                item_id=item_id,
                final_url=final_url,
                error=ERROR_PRODUCT_NOT_FOUND,
            )

        if is_verification_indicator(final_url):
            return ProductMetadata(
                shop_id=shop_id,
                item_id=item_id,
                final_url=final_url,
                error=ERROR_VERIFICATION_REQUIRED,
            )

        # 1. If active Playwright page is provided, extract using browser session
        if page is not None:
            try:
                page.goto(final_url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                page.wait_for_timeout(2000)
            except Exception as e:
                logger.debug("Page goto error: %s", e)

            current_url = page.url
            content = page.content()

            if is_unauthenticated_page(current_url, content):
                if self.session_manager:
                    login_success = self.session_manager.wait_for_manual_login(
                        page=page,
                        login_url=current_url,
                        on_status_change=on_status_change,
                        timeout=300.0,
                    )
                    if login_success:
                        if on_status_change:
                            on_status_change("Đang lấy thông tin")
                        try:
                            page.goto(final_url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                            page.wait_for_timeout(2000)
                        except Exception as e:
                            logger.debug("Page reload after login error: %s", e)
                    else:
                        return ProductMetadata(
                            shop_id=shop_id,
                            item_id=item_id,
                            final_url=current_url,
                            error=STATUS_LOGIN_REQUIRED,
                        )

            return self.extract_from_page(page, shop_id, item_id)

        # 2. HTTP extraction fallback
        http_result = self._extract_via_http(final_url, shop_id, item_id)
        if http_result is not None:
            return http_result

        return ProductMetadata(
            shop_id=shop_id,
            item_id=item_id,
            final_url=final_url,
            error=ERROR_PRODUCT_NOT_FOUND,
        )

    def _extract_via_http(
        self,
        url: str,
        shop_id: str | None,
        item_id: str | None,
    ) -> ProductMetadata | None:
        """Fetch product page via HTTP and extract structured metadata."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://shopee.vn/",
        }

        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                actual_url = str(response.geturl())
                raw_bytes = response.read()
                content = raw_bytes.decode("utf-8", errors="ignore")

            if is_unauthenticated_page(actual_url, content):
                return None

            if is_verification_indicator(actual_url, content):
                return ProductMetadata(
                    shop_id=shop_id,
                    item_id=item_id,
                    final_url=actual_url,
                    error=ERROR_VERIFICATION_REQUIRED,
                )

            if is_not_found_indicator(content):
                return ProductMetadata(
                    shop_id=shop_id,
                    item_id=item_id,
                    final_url=actual_url,
                    error=ERROR_PRODUCT_NOT_FOUND,
                )

            meta = extract_metadata_from_html(
                content,
                base_url=actual_url,
                shop_id=shop_id,
                item_id=item_id,
            )
            return meta

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ProductMetadata(
                    shop_id=shop_id,
                    item_id=item_id,
                    final_url=url,
                    error=ERROR_PRODUCT_NOT_FOUND,
                )
            return None
        except (TimeoutError, socket.timeout):
            return ProductMetadata(
                shop_id=shop_id,
                item_id=item_id,
                final_url=url,
                error="Quá thời gian kết nối (Timeout)",
            )
        except urllib.error.URLError as e:
            return ProductMetadata(
                shop_id=shop_id,
                item_id=item_id,
                final_url=url,
                error=f"Lỗi mạng: {e.reason}",
            )
        except Exception as e:
            logger.debug("HTTP extraction failed: %s", e)
            return None
