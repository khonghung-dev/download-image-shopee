"""Canonical Shopee product identity helpers."""

from __future__ import annotations

import re


_NUMERIC_ID = re.compile(r"^[0-9]+$")


def canonical_product_key(shop_id: object, item_id: object) -> str:
    """Return the one persistent Shopee identity, ``shop_id:item_id``.

    Shopee's authoritative identifiers are positive decimal integers. Keeping
    validation here prevents marker ownership and runtime deduplication from
    quietly accepting title-, URL-, or folder-derived substitutes.
    """
    shop = str(shop_id).strip()
    item = str(item_id).strip()
    if (
        not _NUMERIC_ID.fullmatch(shop)
        or not _NUMERIC_ID.fullmatch(item)
        or int(shop) <= 0
        or int(item) <= 0
    ):
        raise ValueError("Shopee shop_id and item_id must be positive integers")
    return f"{shop}:{item}"


def is_canonical_product_key(value: object) -> bool:
    """Return whether ``value`` is an exact canonical product-key string."""
    if not isinstance(value, str) or value.count(":") != 1:
        return False
    shop_id, item_id = value.split(":", 1)
    try:
        return canonical_product_key(shop_id, item_id) == value
    except ValueError:
        return False
