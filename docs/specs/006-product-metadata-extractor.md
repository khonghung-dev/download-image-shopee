# Task 006 Specification: Product Metadata Extractor

## Objective

Given a successfully resolved Shopee product URL from Task 005, extract the real product metadata needed by the application:
- `product_name`
- `shop_id`
- `item_id`
- `final_url`
- `error`

Ensure verification that the product exists and can be read, strip unnecessary whitespace from the product name, prioritize structured data (JSON-LD, OpenGraph, embedded state) over brittle CSS selectors, utilize normal HTTP page data first with a dedicated Playwright persistent browser profile as a fallback, support interactive manual user login in headed mode when Shopee requires authentication, handle verification challenges and non-existent products gracefully, and integrate real-time product name replacement and status transitions in the PySide6 UI results table.

---

## Requirements & Scope

### In Scope

1. **Input & Validation**:
   - Takes a resolved product URL (or `ResolvedUrl` instance from Task 005).
   - Confirms that `shop_id` and `item_id` are valid.
   - If the input URL already contains a resolution error, propagates the error immediately without redundant network requests.

2. **Dedicated Persistent Browser Profile**:
   - Stores an application-owned Playwright persistent profile in `%LOCALAPPDATA%\ShopeeImageDownloader\browser_profile` (outside the source repository).
   - Reuses this profile across batch items and future application launches.
   - Strictly does NOT read from user's personal browser profiles (Chrome, Edge, Cốc Cốc) and does NOT inject copied cookies.
   - Strictly does NOT automate credentials or bypass CAPTCHAs.

3. **Manual Authentication Flow (`Cần đăng nhập Shopee`)**:
   - If Shopee redirects to `/verify/traffic/error?is_logged_in=false` or `/buyer/login`:
     - Row status updates to `"Cần đăng nhập Shopee"`.
     - Opens the persistent browser in headed (visible) mode.
     - Allows the user to log in manually (credentials, OTP, or QR code).
     - Detects login completion automatically (via auth cookies or navigation to authenticated pages).
     - Continues processing using the newly authenticated persistent context without prompting login again for subsequent items.
     - If the user closes the window or login times out, records `"Cần đăng nhập Shopee"` without stopping the batch.

4. **Structured Metadata Extraction**:
   - Extracts product metadata in order of priority:
     1. **Schema.org JSON-LD structured data** (`<script type="application/ld+json">`):
        - `BreadcrumbList` (extracting product name from the leaf item).
        - `Product` schema (extracting `name`, `description`, `sku`, etc.).
     2. **OpenGraph & Twitter meta tags**:
        - `<meta property="og:title" content="...">`
        - `<meta name="twitter:title" content="...">`
     3. **DOM elements**:
        - `h1`, `span.x-product-name`, `div._44qnta`, `div.V3eGg6`.
     4. **HTML `<title>` tag**:
        - Extracts and sanitizes the page title.

5. **Product Name Sanitization (`clean_product_name`)**:
   - Unescapes HTML entities (e.g. `&amp;` -> `&`, `&#39;` -> `'`, `&quot;` -> `"`).
   - Strips trailing Shopee brand suffixes (e.g., ` | Shopee Việt Nam`, ` | Shopee VN`, ` - Shopee`, ` | Shopee Singapore`, ` | Shopee Malaysia`, etc.).
   - Trims leading and trailing whitespace.
   - Collapses internal multiple consecutive whitespace and newline characters into a single space.
   - Rejects empty strings and generic non-product titles (e.g., `"Shopee Việt Nam | Mua và Bán Trên Ứng Dụng Di Động Hoặc Website"`, `"Shopping Cart Icon"`, `"Shopee"`).

6. **Error Classification**:
   - **Authentication Required**:
     - Status: `"Cần đăng nhập Shopee"`.
   - **Human Verification Required**:
     - Status / Error: `"Shopee yêu cầu xác minh"`.
   - **Product Not Found / Unavailable**:
     - Status / Error: `"Không tìm thấy sản phẩm"`.
   - **Network & System Errors**:
     - Clear, descriptive error messages.
   - **Batch Fault Tolerance**:
     - One failed product must **never** halt or interrupt processing of subsequent URLs in the queue.

7. **Worker & Concurrency Layer**:
   - `MetadataExtractorWorker` (inheriting `QThread`) in `src/shopee_image_downloader/workers/metadata_worker.py`.
   - Emits signals:
     - `item_started(int, str)`: row index and URL.
     - `item_status_updated(int, str)`: row index and intermediate status string (`"Đang lấy thông tin"`, `"Cần đăng nhập Shopee"`).
     - `item_completed(int, object)`: row index and `ProductMetadata`.
     - `progress_updated(int, int)`: completed count and total count.
     - `batch_finished(list)`: list of all `ProductMetadata` results.

8. **UI Results Table Integration**:
   - When metadata extraction begins: status updates to `"Đang lấy thông tin"`.
   - If login required: status updates to `"Cần đăng nhập Shopee"`, visible window opens, user logs in, resumes to `"Đang lấy thông tin"`.
   - On success:
     - `Sản phẩm / Link` column text is replaced with the extracted `product_name`.
     - Status column updates to `"Đã lấy thông tin"`.
     - Tooltip provides details: `Tên sản phẩm`, `Shop ID`, `Item ID`, `URL`.
   - On failure:
     - Status column displays the failure reason (e.g. `"Không tìm thấy sản phẩm"`, `"Shopee yêu cầu xác minh"`, `"Cần đăng nhập Shopee"`).
     - Tooltip provides error diagnostics.

---

### Out of Scope (Deferred to Future Tasks)

- Product image extraction from gallery/variations (Task 007+).
- Image file downloading and disk streaming (Task 007+).
- Output directory subfolder creation on disk (Task 007+).
- Parallel / multi-threaded worker concurrency changes.

---

## Data Structures

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ProductMetadata:
    """Represents extracted product metadata for a Shopee listing."""
    product_name: str | None = None
    shop_id: str | None = None
    item_id: str | None = None
    final_url: str | None = None
    error: str | None = None
```

---

## Status Flow

```
[Accepted URL]
      │
      ▼
"Đang xử lý link" ── (Resolution Failed) ──► Error Status (e.g. "Không thể xử lý link")
      │
 (Resolved)
      │
      ▼
"Đang lấy thông tin"
      │
      ├─── (Unauthenticated) ──► "Cần đăng nhập Shopee" ──► (User logs in) ──► "Đang lấy thông tin"
      │
      ├─── (Metadata Extracted) ──► Replace URL with `product_name` ──► "Đã lấy thông tin"
      │
      ├─── (Verification Challenge) ──► "Shopee yêu cầu xác minh"
      │
      └─── (Not Found / Deleted)    ──► "Không tìm thấy sản phẩm"
```

---

## Acceptance Criteria

1. Dedicated persistent Playwright profile is stored in application-local AppData and reused across launches.
2. If unauthenticated, UI displays `"Cần đăng nhập Shopee"`, opens headed browser, and resumes automatically upon login.
3. Valid Shopee product URLs return complete `ProductMetadata` with `product_name`, `shop_id`, `item_id`, and `final_url`.
4. Extracted product names have HTML entities unescaped, brand suffixes stripped, and redundant whitespace trimmed.
5. Structurally valid but fake or non-existent URLs return `"Không tìm thấy sản phẩm"`.
6. Verification challenges return `"Shopee yêu cầu xác minh"`.
7. Individual failures do not halt batch execution.
8. The UI results table replaces the raw URL with the actual product name for valid products and sets the status to `"Đã lấy thông tin"`.
9. All automated tests pass offline and with mock fixtures.
