"""Shopee URL Resolver module.

Resolves standard and shortened Shopee Vietnam URLs to their final canonical/normalized
product URLs, validates product destination structure, cleans tracking query parameters,
and extracts shop_id and item_id.
"""

from dataclasses import dataclass
import re
import socket
import urllib.error
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit
import urllib.request

from shopee_image_downloader.core.url_validator import is_shopee_vn_url

DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT: float = 10.0

# Known tracking query parameter keys to remove
_TRACKING_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "sp_atk",
        "sp_from",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "gclid",
        "fbclid",
        "aff_source",
        "xptdk",
        "is_from_login",
        "smtt",
        "extra_params",
        "from_page",
        "deep_and_deferred",
        "previous_page",
        "seller_voucher",
        "recommend_index",
        "request_id",
        "search_item_id",
        "version",
        "__classic__",
        "entry_point",
        "uls_trackid",
    }
)

# Regex patterns to extract shop_id and item_id
_PATTERN_DASH_I = re.compile(
    r"(?:[-_.]i|/i)\.(?P<shop_id>\d+)\.(?P<item_id>\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)
_PATTERN_PRODUCT_PATH = re.compile(
    r"/product/(?P<shop_id>\d+)/(?P<item_id>\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)
_PATTERN_LEGACY_DOT = re.compile(
    r"(?:/|%2F)[^/?#]+\.(?P<shop_id>\d+)\.(?P<item_id>\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResolvedUrl:
    """Represents the resolution result for a Shopee URL."""

    original_url: str
    final_url: str | None = None
    shop_id: str | None = None
    item_id: str | None = None
    error: str | None = None


def is_error_page_url(url: str) -> bool:
    """Check if a URL points to a Shopee error page or shortlink error destination."""
    if not url:
        return True
    try:
        parts = urlsplit(url)
    except Exception:
        return True

    hostname = (parts.hostname or "").lower()
    path = (parts.path or "").lower()

    # Shopee shortener error domain (e.g., https://shopee.ee/error_page)
    if hostname == "shopee.ee" or hostname.endswith(".shopee.ee"):
        return True

    # Error paths across Shopee domains
    if "error_page" in path or path.startswith(("/error", "/buyer/login", "/user/purchase")):
        return True

    return False


def extract_ids_from_url(url: str) -> tuple[str | None, str | None]:
    """Extract shop_id and item_id from a Shopee product URL if present.

    Returns:
        (shop_id, item_id) tuple if found, or (None, None).
    """
    if not url:
        return None, None

    decoded_url = unquote(url)

    # 1. Match -i.{shop_id}.{item_id} (standard web pattern)
    match = _PATTERN_DASH_I.search(decoded_url)
    if match:
        return match.group("shop_id"), match.group("item_id")

    # 2. Match /product/{shop_id}/{item_id}
    match = _PATTERN_PRODUCT_PATH.search(decoded_url)
    if match:
        return match.group("shop_id"), match.group("item_id")

    # 3. Match legacy .{shop_id}.{item_id}
    match = _PATTERN_LEGACY_DOT.search(decoded_url)
    if match:
        return match.group("shop_id"), match.group("item_id")

    # 4. Check query parameters (e.g. ?shopid=...&itemid=...)
    try:
        parts = urlsplit(decoded_url)
        query_dict = dict(parse_qsl(parts.query, keep_blank_values=True))
        shop_id = (
            query_dict.get("shopid")
            or query_dict.get("shop_id")
            or query_dict.get("shopId")
        )
        item_id = (
            query_dict.get("itemid")
            or query_dict.get("item_id")
            or query_dict.get("itemId")
        )
        if shop_id and item_id and shop_id.isdigit() and item_id.isdigit():
            return shop_id, item_id
    except Exception:
        pass

    return None, None


def is_shopee_product_url(url: str) -> bool:
    """Check if a URL is structurally a valid Shopee product listing URL."""
    if not url or is_error_page_url(url):
        return False
    shop_id, item_id = extract_ids_from_url(url)
    return bool(shop_id and item_id and shop_id.isdigit() and item_id.isdigit())


def clean_tracking_params(url: str) -> str:
    """Remove unnecessary tracking and marketing query parameters from a URL while preserving destination."""
    if not url:
        return url

    try:
        parts = urlsplit(url)
    except Exception:
        return url

    # Enforce https scheme if scheme is present or http
    scheme = "https" if parts.scheme.lower() in ("http", "https") else parts.scheme
    netloc = parts.netloc.lower()

    # Parse and filter query parameters
    query_tuples = parse_qsl(parts.query, keep_blank_values=True)
    cleaned_query: list[tuple[str, str]] = []

    # Check if IDs are already in the path
    has_path_ids = bool(
        _PATTERN_DASH_I.search(parts.path)
        or _PATTERN_PRODUCT_PATH.search(parts.path)
        or _PATTERN_LEGACY_DOT.search(parts.path)
    )

    for k, v in query_tuples:
        k_lower = k.lower()
        if k_lower in _TRACKING_QUERY_KEYS:
            continue
        if k_lower.startswith(("utm_", "sp_", "fb_", "ga_")):
            continue
        # If path already uniquely identifies the item, remove generic redundant tracking params
        if has_path_ids and k_lower in ("is_from_signup", "page_from", "referral"):
            continue
        cleaned_query.append((k, v))

    # Re-encode remaining query if any
    new_query = urlencode(cleaned_query) if cleaned_query else ""

    # Reassemble URL without fragment
    return urlunsplit((scheme, netloc, parts.path, new_query, ""))


class ShopeeUrlResolver:
    """Resolves Shopee URLs following HTTP redirects and normalizes destination product links."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_USER_AGENT

    def resolve_url(self, url: str) -> ResolvedUrl:
        """Resolve a single Shopee URL into its canonical/normalized product destination."""
        cleaned_input = url.strip()
        if not cleaned_input:
            return ResolvedUrl(
                original_url=url,
                error="URL trống",
            )

        # Ensure scheme
        target_url = (
            cleaned_input
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+-.]*://", cleaned_input)
            else f"https://{cleaned_input}"
        )

        if not is_shopee_vn_url(target_url):
            return ResolvedUrl(
                original_url=url,
                error="Link không phải địa chỉ Shopee hợp lệ",
            )

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        try:
            req = urllib.request.Request(
                target_url,
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                final_url = str(response.geturl())

            # 1. Reject error page destinations (e.g. https://shopee.ee/error_page)
            if is_error_page_url(final_url):
                return ResolvedUrl(
                    original_url=url,
                    error="Link chuyển hướng đến trang lỗi Shopee (error_page)",
                )

            normalized_url = clean_tracking_params(final_url)
            shop_id, item_id = extract_ids_from_url(normalized_url)

            # 2. Reject non-product pages lacking valid shop_id and item_id
            if not shop_id or not item_id or not shop_id.isdigit() or not item_id.isdigit():
                return ResolvedUrl(
                    original_url=url,
                    error="URL không phải link sản phẩm Shopee hợp lệ",
                )

            return ResolvedUrl(
                original_url=url,
                final_url=normalized_url,
                shop_id=shop_id,
                item_id=item_id,
                error=None,
            )

        except urllib.error.HTTPError as e:
            return ResolvedUrl(
                original_url=url,
                error=f"HTTP {e.code}: {e.reason}",
            )
        except urllib.error.URLError as e:
            reason = str(e.reason)
            return ResolvedUrl(
                original_url=url,
                error=f"Lỗi mạng: {reason}",
            )
        except (TimeoutError, socket.timeout):
            return ResolvedUrl(
                original_url=url,
                error="Quá thời gian kết nối (Timeout)",
            )
        except Exception as e:
            return ResolvedUrl(
                original_url=url,
                error=f"Lỗi không xác định: {e}",
            )

    def resolve_batch(self, urls: list[str]) -> list[ResolvedUrl]:
        """Resolve a batch of URLs sequentially."""
        return [self.resolve_url(u) for u in urls]
