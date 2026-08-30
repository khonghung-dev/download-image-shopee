# Task 005 Specification: Shopee URL Resolver

## Objective

Implement the Shopee URL resolution engine and concurrency worker to resolve each accepted Shopee URL into its final normalized product URL, extract `shop_id` and `item_id`, strip unnecessary tracking parameters, handle network/redirect errors gracefully on a per-URL basis, and integrate the status transitions seamlessly with the PySide6 UI results table.

## Requirements & Scope

### In Scope

1. **Shopee URL Resolution**:
   - Resides in `src/shopee_image_downloader/core/url_resolver.py` decoupled from Qt UI.
   - Accepts validated Shopee Vietnam URLs:
     - Standard web product URLs (e.g., `https://shopee.vn/product/{shop_id}/{item_id}`, `https://shopee.vn/{product_slug}-i.{shop_id}.{item_id}`).
     - Shortened URLs (e.g., `https://s.shopee.vn/{code}`).
     - Universal links and redirect paths.
   - Follows HTTP redirects (301, 302, 303, 307, 308) using Python's standard library `urllib.request`.
   - Uses realistic browser request headers (`User-Agent`, `Accept`, `Accept-Language`).
   - Uses sensible network timeouts (default: 10.0 seconds per URL).
   - Resolves via normal HTTP requests without requiring Playwright.

2. **Destination Validation & Error Page Rejection**:
   - Validates that the resolved destination URL is structurally a Shopee product listing before considering it resolved.
   - Rejects error pages (e.g., `https://shopee.ee/error_page`, paths containing `/error_page`, `/error`, `/buyer/login`).
   - Rejects generic non-product Shopee pages (e.g., `https://shopee.vn/abcxyz`, `https://shopee.vn/daily_discover`, `https://shopee.vn/flash_sale`).
   - Accepts known product URL structures that contain valid `shop_id` and `item_id`.
   - On error page or non-product destination, marks the item with status `"Không thể xử lý link"` and an informative error message.

3. **URL Normalization & Tracking Parameter Stripping**:
   - Removes superfluous tracking/query parameters (e.g., `sp_atk`, `sp_from`, `utm_*`, `gclid`, `fbclid`, `aff_source`, `xptdk`, `is_from_login`, `smtt`, `extra_params`, `from_page`, `deep_and_deferred`, `previous_page`, etc.).
   - Preserves destination product identity.
   - Strips URL fragments (`#...`).


3. **Identifier Extraction (`shop_id` & `item_id`)**:
   - Extracts `shop_id` and `item_id` from the resolved/normalized URL when possible:
     - Format: `-i.{shop_id}.{item_id}` or `_i.{shop_id}.{item_id}`
     - Format: `/product/{shop_id}/{item_id}`
     - Format: `.{shop_id}.{item_id}`
     - Query parameters: `shopid`/`shop_id` and `itemid`/`item_id`

4. **Result Data Model**:
   - `ResolvedUrl` dataclass containing:
     - `original_url: str`
     - `final_url: str | None`
     - `shop_id: str | None`
     - `item_id: str | None`
     - `error: str | None`

5. **Fault Tolerance & Resilience**:
   - Errors (e.g., HTTP 404, HTTP 500, network timeouts, DNS failures, connection drops) are handled per URL.
   - An error on one URL must **never** halt or crash the batch processing of subsequent URLs.
   - Records descriptive error messages in `ResolvedUrl.error`.

6. **Worker & Concurrency Layer**:
   - `UrlResolverWorker` implemented as a `QThread` in `src/shopee_image_downloader/workers/url_resolver_worker.py`.
   - Runs resolution sequentially on a background thread to keep the Qt GUI responsive at all times.
   - Emits signals:
     - `item_started(int, str)`: row index and original URL.
     - `item_resolved(int, object)`: row index and `ResolvedUrl`.
     - `progress_updated(int, int)`: completed count and total count.
     - `finished(list)`: list of all `ResolvedUrl` results.

7. **UI Results Table Integration & Status Transitions**:
   - Initial validation phase:
     - Valid URLs receive status `"Đang chờ"`.
     - Invalid URLs receive status `"Link không hợp lệ"`.
   - Resolution phase (for `"Đang chờ"` items):
     - When processing starts for a row: status updates to `"Đang xử lý link"`.
     - On successful resolution: status updates to `"Đã resolve link"`, and the `Sản phẩm / Link` column updates to `final_url`.
     - On resolution failure: status updates to `"Không thể xử lý link"`.
   - Start button is disabled during processing and re-enabled upon batch completion.
   - Progress bar and status label update dynamically during processing.

### Out of Scope (Deferred to Future Tasks)

- Product name extraction from HTML/API (Task 006+).
- Product image extraction from media gallery (Task 006+).
- Image file downloading and disk streaming (Task 006+).
- Product folder creation on the filesystem (Task 006+).
- Playwright / Headless browser fallback.

## Data Structures

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ResolvedUrl:
    original_url: str
    final_url: str | None = None
    shop_id: str | None = None
    item_id: str | None = None
    error: str | None = None
```

## Status Flow

```
[User Input]
     │
     ▼
[Validation] ── (Invalid) ──► "Link không hợp lệ"
     │
 (Valid)
     │
     ▼
"Đang chờ"
     │
     ▼ (Worker Starts Item)
"Đang xử lý link"
     │
     ├─── (HTTP Resolution Succeeded) ──► "Đã resolve link"
     │
     └─── (HTTP Resolution Failed)    ──► "Không thể xử lý link"
```

## Acceptance Criteria

1. Normal `shopee.vn` URLs are resolved and stripped of tracking parameters.
2. Shortened `s.shopee.vn` URLs are resolved via HTTP redirects to their destination URLs.
3. `shop_id` and `item_id` are extracted accurately from supported URL patterns.
4. HTTP / network failures (404, 500, timeout, DNS error) set `error` without crashing or stopping the batch.
5. UI table status transitions adhere strictly to `"Đang chờ"` → `"Đang xử lý link"` → `"Đã resolve link"` / `"Không thể xử lý link"`.
6. UI remains responsive with non-blocking background worker thread.
7. All automated unit and integration tests pass offline.
