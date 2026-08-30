# Tasks & Project Roadmap

This document tracks development milestones, specifications, and execution status for **Shopee Image Downloader**.

## Task Overview

| Task ID | Title | Status | Specification |
|---------|-------|--------|---------------|
| **001** | Project Bootstrap & PySide6 Baseline | [x] Complete | [001-project-bootstrap.md](file:///d:/download-picture-shopee/docs/specs/001-project-bootstrap.md) |
| **002** | Main GUI Layout & User Controls | [x] Complete | [002-main-ui.md](file:///d:/download-picture-shopee/docs/specs/002-main-ui.md) |
| **003** | Multiline URL Input & Validation | [x] Complete | [003-url-input-validation.md](file:///d:/download-picture-shopee/docs/specs/003-url-input-validation.md) |
| **004** | Output Folder Selector & Persistence | [x] Complete | [004-output-folder-selector.md](file:///d:/download-picture-shopee/docs/specs/004-output-folder-selector.md) |
| **005** | Shopee URL Resolver | [x] Complete | [005-shopee-url-resolver.md](file:///d:/download-picture-shopee/docs/specs/005-shopee-url-resolver.md) |
| **006** | Product Metadata Extractor | [x] Complete | [006-product-metadata-extractor.md](file:///d:/download-picture-shopee/docs/specs/006-product-metadata-extractor.md) |
| **006A**| Shopee Authentication & Persistent Session | [x] Complete | [006a-shopee-auth-session.md](file:///d:/download-picture-shopee/docs/specs/006a-shopee-auth-session.md) |
| **007** | Image Download Engine & Extraction | [ ] Planned | - |
| **008** | Progress Feedback & Batch Reporting | [ ] Planned | - |
| **009** | Packaging & Windows Executable Distribution | [ ] Planned | - |

---

## Detailed Task Log

### Task 001: Project Bootstrap & PySide6 Baseline
- **Goal**: Establish the repository layout, documentation, build metadata, test runner, Git repository, and verify clean startup of a blank PySide6 main window.
- **Deliverables**:
  - [x] Python `src/` layout configuration in `pyproject.toml`.
  - [x] Documentation suite in `docs/` (`PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `TASKS.md`, `TESTING.md`, `specs/`, `adr/`).
  - [x] PySide6 `MainWindow` titled "Shopee Image Downloader".
  - [x] Initial automated test suite in `tests/`.
  - [x] Local Git initialization.
  - [x] Execution verification and error-free launch.

### Task 002: Main GUI Layout & User Controls
- **Goal**: Implement the primary desktop layout with all specified input fields, action buttons, progress indicators, and results table.
- **Deliverables**:
  - [x] Specification document in `docs/specs/002-main-ui.md`.
  - [x] Large multiline URL input labeled "Link sản phẩm Shopee" with placeholder.
  - [x] Read-only output folder text field and "Chọn thư mục" button.
  - [x] Main action button "Bắt đầu tải ảnh".
  - [x] Progress bar and status label initialized to "Sẵn sàng".
  - [x] Results table with columns: `STT`, `Sản phẩm / Link`, `Trạng thái`, `Số ảnh`.
  - [x] Automated UI unit tests in `tests/test_ui.py`.
  - [x] Application execution and resize verification.

### Task 003: Multiline URL Input & Validation
- **Goal**: Implement multiline URL parsing, whitespace trimming, empty line filtering, exact deduplication, Shopee Vietnam URL validation (`shopee.vn`, `s.shopee.vn`), and UI results table population without performing network calls or background downloads.
- **Deliverables**:
  - [x] Specification document in `docs/specs/003-url-input-validation.md`.
  - [x] Core URL validator and parsing logic in `src/shopee_image_downloader/core/url_validator.py`.
  - [x] Validation and parsing decoupled from UI layer.
  - [x] Execution trigger on "Bắt đầu tải ảnh" populating the results table with statuses (`Đang chờ` / `Link không hợp lệ`).
  - [x] Status label showing accepted unique Shopee URL count.
  - [x] Unit test suite in `tests/test_url_validator.py` covering normal URLs, shortlinks, non-Shopee URLs, whitespace, blank lines, and duplicate handling.
  - [x] UI tests in `tests/test_ui.py` validating UI workflow and table population.

### Task 004: Output Folder Selector & Persistence
- **Goal**: Implement native directory picker dialog for output folder selection, decouple settings persistence to a JSON-backed settings manager, restore previously selected folder on startup if still present on disk, and guard against starting batch processing when no valid output folder is selected.
- **Deliverables**:
  - [x] Specification document in [004-output-folder-selector.md](file:///d:/download-picture-shopee/docs/specs/004-output-folder-selector.md).
  - [x] `SettingsManager` in [src/shopee_image_downloader/storage/settings.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/storage/settings.py).
  - [x] Folder picker integration with `QFileDialog.getExistingDirectory`.
  - [x] Persistent folder loading on application startup with disk existence verification.
  - [x] Action button guard displaying `"Vui lòng chọn thư mục lưu ảnh."` when output folder is unset or invalid.
  - [x] Preserved URL validation behavior from Task 003 when a valid folder is selected.
  - [x] Unit test suite in [tests/test_settings.py](file:///d:/download-picture-shopee/tests/test_settings.py) and UI tests in [tests/test_ui.py](file:///d:/download-picture-shopee/tests/test_ui.py).

### Task 005: Shopee URL Resolver
- **Goal**: Resolve each accepted Shopee URL into its final normalized product URL, extract `shop_id` and `item_id`, strip unnecessary tracking parameters, handle network/redirect errors gracefully on a per-URL basis without halting batch execution, and integrate status flow with the PySide6 UI results table.
- **Deliverables**:
  - [x] Specification document in [005-shopee-url-resolver.md](file:///d:/download-picture-shopee/docs/specs/005-shopee-url-resolver.md).
  - [x] Core URL resolver and ID extraction in [src/shopee_image_downloader/core/url_resolver.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/core/url_resolver.py).
  - [x] Concurrency worker `UrlResolverWorker` (`QThread`) in [src/shopee_image_downloader/workers/url_resolver_worker.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/workers/url_resolver_worker.py).
  - [x] UI status transition: `"Đang chờ"` → `"Đang xử lý link"` → `"Đã resolve link"` / `"Không thể xử lý link"`.
  - [x] Unit test suite in [tests/test_url_resolver.py](file:///d:/download-picture-shopee/tests/test_url_resolver.py) covering normal URLs, shortlinks (`s.shopee.vn`), tracking parameters, malformed URLs, timeouts, network failures, batch resilience, and worker lifecycle.
  - [x] UI integration tests in [tests/test_ui.py](file:///d:/download-picture-shopee/tests/test_ui.py).

### Task 006: Product Metadata Extractor
- **Goal**: Given a successfully resolved Shopee product URL, obtain real product metadata (`product_name`, `shop_id`, `item_id`, `final_url`, `error`), verify product existence, clean product names, prioritize structured JSON-LD/meta tags over CSS selectors, use normal HTTP first with Playwright fallback when needed, handle verification and non-existent products gracefully, and replace the raw URL in the UI table with the actual product name.
- **Deliverables**:
  - [x] Specification document in [006-product-metadata-extractor.md](file:///d:/download-picture-shopee/docs/specs/006-product-metadata-extractor.md).
  - [x] Core metadata extractor `ShopeeMetadataExtractor` and sanitization in [src/shopee_image_downloader/core/metadata_extractor.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/core/metadata_extractor.py).
  - [x] Background worker `MetadataExtractorWorker` (`QThread`) in [src/shopee_image_downloader/workers/metadata_worker.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/workers/metadata_worker.py).
  - [x] UI status transition and product name replacement: `"Đang lấy thông tin"` → replaces raw URL in `Sản phẩm / Link` column with real `product_name` → `"Đã lấy thông tin"`.
  - [x] Regression safety for fake/deleted items returning `"Không tìm thấy sản phẩm"`, and human verification challenges returning `"Shopee yêu cầu xác minh"`.
  - [x] Unit test suite in [tests/test_metadata_extractor.py](file:///d:/download-picture-shopee/tests/test_metadata_extractor.py).
  - [x] UI integration tests in [tests/test_ui.py](file:///d:/download-picture-shopee/tests/test_ui.py).

### Task 006A: Shopee Authentication & Persistent Session
- **Goal**: Add a dedicated Shopee account/session management layer before product processing. Provide an interactive manual login flow using installed Google Chrome launched as a normal external process (`C:\Program Files\Google\Chrome\Application\chrome.exe`), persist the authenticated profile outside Git in `%LOCALAPPDATA%\ShopeeImageDownloader\ChromeUserData`, enforce strict filesystem safety guards protecting personal Chrome profiles, retain the browser open without auto-closing during verification challenges, provide explicit `"Hoàn tất đăng nhập"` user confirmation, restore active sessions across application launches upon genuine auth cookie validation, provide safe logout functionality, and enforce an authentication guard on the "Bắt đầu tải ảnh" button.
- **Deliverables**:
  - [x] Specification document in [006a-shopee-auth-session.md](file:///d:/download-picture-shopee/docs/specs/006a-shopee-auth-session.md).
  - [x] Filesystem safety guard `path_safety.py` in [src/shopee_image_downloader/core/path_safety.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/core/path_safety.py).
  - [x] Session and auth manager `ShopeeSessionManager` in [src/shopee_image_downloader/core/browser_session.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/core/browser_session.py) with external process management and post-login CDP attachment.
  - [x] Background worker `AuthLoginWorker` (`QThread`) in [src/shopee_image_downloader/workers/auth_worker.py](file:///d:/download-picture-shopee/src/shopee_image_downloader/workers/auth_worker.py).
  - [x] Shopee Account UI section in `MainWindow` with account status label, `Đăng nhập Shopee`, `Hoàn tất đăng nhập`, and `Đăng xuất` buttons.
  - [x] Interactive normal Google Chrome login detecting account username and cookies without automating credentials, OTPs, or CAPTCHAs.
  - [x] Verification retention keeping Chrome open without auto-closing or refresh loops on `/verify/captcha` or rate block challenges.
  - [x] Explicit user confirmation via `"Hoàn tất đăng nhập"` button to validate and finalize sessions cleanly.
  - [x] Safe logout clearing the dedicated `ChromeUserData` profile safely without touching user personal browser profiles.
  - [x] Action button guard displaying `"Vui lòng đăng nhập Shopee trước."` when unauthenticated.
  - [x] Unit test suite in [tests/test_auth_session.py](file:///d:/download-picture-shopee/tests/test_auth_session.py) and UI tests in [tests/test_ui.py](file:///d:/download-picture-shopee/tests/test_ui.py).
