"""Shopee Vietnam URL parsing, validation, and deduplication logic."""

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

STATUS_PENDING: str = "Đang chờ"
STATUS_INVALID: str = "Link không hợp lệ"

# Allowed host patterns for Shopee Vietnam
# e.g., shopee.vn, s.shopee.vn, www.shopee.vn, etc.
_SHOPEE_VN_HOST_PATTERN = re.compile(
    r"^(?:[a-zA-Z0-9-]+\.)*shopee\.vn$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedUrl:
    """Represents a parsed URL line with validation outcome and status."""

    url: str
    is_valid: bool
    status: str


def is_shopee_vn_url(url: str) -> bool:
    """Validate whether the given string is a valid Shopee Vietnam URL.

    Accepts URLs from domains ending with shopee.vn (e.g. shopee.vn, s.shopee.vn).
    Handles URLs with or without http/https scheme.
    Rejects non-Shopee URLs, invalid domain names, and empty/malformed inputs.
    """
    cleaned = url.strip()
    if not cleaned:
        return False

    # Prepend scheme if missing for reliable urlsplit parsing
    target = cleaned if re.match(r"^[a-zA-Z][a-zA-Z0-9+-.]*://", cleaned) else f"https://{cleaned}"

    try:
        parts = urlsplit(target)
    except Exception:
        return False

    # Must have http or https scheme
    if parts.scheme.lower() not in ("http", "https"):
        return False

    hostname = parts.hostname
    if not hostname:
        return False

    # Check hostname strictly matches *.shopee.vn or shopee.vn
    if not _SHOPEE_VN_HOST_PATTERN.match(hostname):
        return False

    # Ensure hostname contains valid dot separator (shopee.vn)
    if hostname.lower() != "shopee.vn" and not hostname.lower().endswith(".shopee.vn"):
        return False

    return True


def parse_url_lines(text: str) -> list[ParsedUrl]:
    """Parse multiline input into deduplicated ParsedUrl entries.

    - Splits input by newline characters.
    - Trims leading and trailing whitespace from each line.
    - Discards empty / whitespace-only lines.
    - Removes exact duplicate URLs while preserving the order of appearance.
    - Marks valid Shopee Vietnam URLs with STATUS_PENDING ("Đang chờ")
      and invalid URLs with STATUS_INVALID ("Link không hợp lệ").
    """
    results: list[ParsedUrl] = []
    seen: set[str] = set()

    for line in text.splitlines():
        cleaned_line = line.strip()
        if not cleaned_line:
            continue

        if cleaned_line in seen:
            continue
        seen.add(cleaned_line)

        valid = is_shopee_vn_url(cleaned_line)
        status = STATUS_PENDING if valid else STATUS_INVALID

        results.append(
            ParsedUrl(
                url=cleaned_line,
                is_valid=valid,
                status=status,
            )
        )

    return results
