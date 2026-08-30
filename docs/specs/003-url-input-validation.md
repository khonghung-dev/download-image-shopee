# Task 003 Specification: Multiline URL Input & Validation

## Objective

Implement multiline URL input reading, whitespace trimming, blank line elimination, exact deduplication, Shopee Vietnam URL validation, and UI table population upon clicking "Bắt đầu tải ảnh" without performing network calls or background downloads.

## Requirements & Scope

### In Scope
1. **Multiline Input Parsing**:
   - Read lines from `QPlainTextEdit` (`url_input`).
   - Split by standard newlines (`\n`, `\r\n`).
   - Trim leading and trailing whitespace from each line.
   - Discard empty or whitespace-only lines.
   - Preserve original input ordering.
   - Deduplicate exact URLs: keep the first occurrence and discard subsequent identical URLs.
2. **Shopee Vietnam URL Validation**:
   - Validation must reside in `src/shopee_image_downloader/core/url_validator.py`, completely separated from the UI.
   - Accept URLs targeting Shopee Vietnam:
     - `shopee.vn`
     - `s.shopee.vn`
     - Subdomains like `www.shopee.vn` or `*.shopee.vn`.
     - Supports scheme variations: `https://`, `http://`, or without scheme (e.g., `shopee.vn/product/...`, `s.shopee.vn/...`).
   - Reject obviously non-Shopee URLs (e.g. `lazada.vn`, `tiki.vn`, `google.com`, `shopee.vn.evil.com`, non-URL strings).
3. **Action Trigger ("Bắt đầu tải ảnh")**:
   - Trigger URL parsing upon clicking the button.
   - **No network calls**, **no HTTP requests**, **no redirect resolution**, **no file downloads**.
   - Populate the Results Table:
     - Column `STT`: Row number starting at 1.
     - Column `Sản phẩm / Link`: Parsed URL string.
     - Column `Trạng thái`: `"Đang chờ"` for valid URLs, `"Link không hợp lệ"` for invalid URLs.
     - Column `Số ảnh`: `"-"`.
   - Update UI Status to display the number of accepted unique Shopee URLs (e.g., `Đã nhận X link hợp lệ` or `Đã nhận X link hợp lệ (Y không hợp lệ)`).
4. **Automated Unit & UI Tests**:
   - Normal Shopee Vietnam URLs (`shopee.vn/product...`).
   - Shortened Shopee URLs (`s.shopee.vn/...`).
   - Blank / whitespace lines.
   - Exact duplicate URLs.
   - Surrounding whitespace around URLs.
   - Non-Shopee URLs.
   - UI trigger testing (table population and status label update).

### Out of Scope (Deferred to Future Tasks)
- HTTP extraction / resolving shortlinks (Task 004/005).
- File storage and image downloading (Task 004/005).
- Background worker threads (Task 005).

## Data Structure

```python
from dataclasses import dataclass

STATUS_PENDING: str = "Đang chờ"
STATUS_INVALID: str = "Link không hợp lệ"

@dataclass(frozen=True)
class ParsedUrl:
    raw_url: str
    cleaned_url: str
    is_valid: bool
    status: str
```

## Acceptance Criteria

1. Input with multiple URLs, extra whitespace, blank lines, and duplicates is parsed correctly.
2. Only valid Shopee VN URLs receive status `"Đang chờ"`; invalid URLs receive `"Link không hợp lệ"`.
3. Clicking "Bắt đầu tải ảnh" populates the table accurately and updates the status label.
4. All unit and UI tests pass offline with zero network calls.
