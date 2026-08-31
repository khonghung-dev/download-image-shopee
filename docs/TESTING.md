# Testing Strategy: Shopee Image Downloader

This document outlines the testing guidelines, test categories, and verification commands for the project.

## Test Categories

1. **Unit Tests (`tests/`)**:
   - Validate standalone business logic, URL parsers, metadata extractors, path sanitization, filesystem safety guards, and session data structures.
   - Run completely offline without real HTTP requests or GUI windows.

2. **Authentication & Session Tests (`tests/test_auth_session.py`)**:
   - Validate installed Google Chrome selection (`channel="chrome"` and path discovery).
   - Validate dedicated application-owned profile directory (`%LOCALAPPDATA%\ShopeeImageDownloader\ChromeUserData`).
   - Validate path safety guards rejecting personal Chrome User Data, Profile 10, and system roots.
   - Validate authentication cookie extraction, startup session verification, grace periods, verification challenges, timeout handling, and safe logout.

3. **Batch Queue & Orchestration Tests (`tests/test_batch_queue.py`)**:
   - Validate FIFO sequential item execution (exactly 1 URL in flight).
   - Validate individual failure resilience (URL failure does not halt the queue).
   - Validate input URL deduplication and product identity resolution (`shop_id:item_id`).
   - Validate `request_id` correlation and stale result rejection.
   - Validate per-item bounded timeouts and automatic progression.
   - Validate human verification pause (`PAUSED_VERIFICATION`) and resume (`Tiếp tục`) continuing the same item.
   - Validate batch cancellation (`Hủy`) and clean state reset.

4. **Extension & Bridge Tests (`tests/test_bridge_protocol.py`, `tests/test_bridge_server.py`, `tests/test_extension_extractor.py`, `tests/test_native_messaging.py`)**:
   - Validate versioned JSON protocol schemas, message size limits, handshake (`hello` -> `hello_ack`), batch messages (`open_product`, `process_url`, `process_progress`, `process_error`, `cancel_processing`), and product payloads.
   - Validate `image_count` protocol field integrity validation and `PROTOCOL_INTEGRITY_ERROR` rejection upon mismatch.
   - Validate Chrome Native Messaging 4-byte framing, binary mode stdio, partial stream reads, malformed JSON recovery, and oversize rejection.
   - Validate Native Host bidirectional lossless relay (testing 9 images and 30-image large gallery payloads without truncation), offline graceful handling (`desktop_connected: false`), and desktop online connection.
   - Validate single canonical product result builder in background (`sendCompleteProductToDesktop`) and zero active DOM querying in background service worker.
   - Validate event-driven `AUTHORITATIVE_PRODUCT_COMPLETE` emission from content script when gallery hydrations achieve `COMPLETE`.
   - Validate auto-send exactly-once guard in `background.js` request state machine.
   - Validate test cases A, B, C, D, E ensuring complete gallery extraction (9 images, 25 images), manual and batch sender convergence, stale event rejection, and bounded `PRODUCT_TIMEOUT` error emission.
   - Validate `structured_data` (JSON-LD) and `structured_single_fallback` semantics as strictly `PARTIAL` across 1, 4, and 20 candidate counts.
   - Execute the real production core against a mutable canonical gallery: early `A B C D` with no arrows must remain `PARTIAL`, keep both boundaries `UNKNOWN`, and never enter authoritative cache; later hydration and real overlapping carousel clicks must return 9 images with `CAROUSEL_BOUNDS_CONFIRMED`.
   - Validate a genuine four-image/no-arrow gallery remains initially `PARTIAL`, then becomes `COMPLETE` only after the 1000 ms production quiet-window proof (`STABLE_SINGLE_PAGE`).
   - Validate the existing overlapping 9-image plus 1-video carousel still enumerates all images, excludes video, and reports `CAROUSEL_BOUNDS_CONFIRMED`.
   - Validate content script automatic lifecycle runs on load/DOM-idle, and safely disconnects observers on completion or navigation.

5. **UI & Window Initialization Tests (`tests/test_ui.py`)**:
   - Verify that Qt widgets, window title, Shopee Account section, Bridge status indicator, URL inputs, table rows, and signal bindings initialize without uncaught exceptions.
   - Validate batch button state transitions (`Bắt đầu tải ảnh` -> `Hủy` -> `Tiếp tục` -> `Bắt đầu tải ảnh`).
   - Validate bridge connection guard, table row insertion, updating, and deduplication when receiving batch progress and product results.
   - Validate Case D: existing batch row (`request_id=R1`, `product_key=P1`) updated in place when subsequent manual send (`request_id=None`, `product_key=P1`) arrives, with zero duplicate rows.
   - Run in offscreen mode (`QT_QPA_PLATFORM=offscreen`) so they execute seamlessly in headless environments and CI/CD pipelines.

5. **Integration / Mock Network Tests**:
   - Test downloader and worker pipelines using mock HTTP responses and sample Shopee HTML/JSON payloads.

## Running Tests

### Standard Test Execution

```powershell
uv run pytest
```

### Run with Verbose Output

```powershell
uv run pytest -v
```

### Headless / Offscreen Execution (for CI or automated runs)

```powershell
$env:QT_QPA_PLATFORM="offscreen"; uv run pytest -v
```


## Guidelines for Writing Tests

- Never make live network calls inside unit tests.
- Isolate file system tests using `tmp_path` pytest fixture.
- NEVER point tests to personal Chrome User Data or Profile 10.
- Keep tests fast, independent, and idempotent.
