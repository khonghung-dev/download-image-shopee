# Repository Cleanup Report

Cleanup date: 2026-08-31

## Active Runtime

There is one automatic batch flow:

```text
shopee_image_downloader.main:main
→ MainWindow.handle_start_validation
→ parse_url_lines
→ BatchQueueManager.start_batch
→ BatchQueueManager._process_current_item
→ MainWindow._on_queue_send_open_product
→ create_open_product_message
→ ExtensionBridgeServer.send_message
→ localhost WebSocket 127.0.0.1:8765
→ NativeMessagingHost._on_ws_message_received
→ Chrome Native Messaging
→ background.js:handleNativeMessage(open_product)
→ handleOpenProductRequest
→ ensureActiveWorkerTab
→ worker tab loads extractor_core.js then content.js
→ content.js:runProductExtractionLifecycle
→ ShopeeExtractorCore.extractProductData
→ AUTHORITATIVE_PRODUCT_COMPLETE
→ background.js:sendCompleteProductToDesktop
→ Native Messaging Host relay
→ ExtensionBridgeServer._on_text_message
→ parse_bridge_product_data
→ MainWindow._on_bridge_product_received
→ BatchQueueManager.handle_product_result
→ item_completed
→ MainWindow._on_queue_item_completed
```

The queue permits one in-flight `open_product` request. `request_id` owns result/error correlation. The automatic path does not use `process_url`, polling, popup payloads, Python HTTP extraction, or browser automation.

## Manual Extension Flow

```text
popup.js:init
→ performExtraction
→ EXTRACT_PRODUCT_DATA
→ content.js message listener
→ ShopeeExtractorCore.extractProductData
→ popup display
→ user clicks CONNECT_DESKTOP
→ background.js:startUserInitiatedConnection
→ chrome.runtime.connectNative
→ Native Host
→ localhost desktop WebSocket
→ user clicks SEND_PRODUCT_TO_DESKTOP
→ background requests GET_COMPLETE_SNAPSHOT from content.js
→ content.js:getCompleteSnapshotRPC
→ same extractor core / authoritative cache
→ background.js:sendCompleteProductToDesktop
→ Native Host relay
→ desktop bridge
→ MainWindow inserts or updates by shop_id:item_id
```

The popup sends only tab identity for manual send. It does not construct the authoritative product payload.

## Runtime Entry Points

| Role | Entry point |
|---|---|
| Desktop | `src/shopee_image_downloader/main.py:main()` / `shopee-image-downloader` console script |
| Desktop UI | `src/shopee_image_downloader/ui/main_window.py:MainWindow` |
| Desktop bridge | `src/shopee_image_downloader/workers/bridge_worker.py:ExtensionBridgeServer` |
| Batch queue | `src/shopee_image_downloader/core/batch_queue.py:BatchQueueManager` |
| Protocol | `src/shopee_image_downloader/core/bridge_protocol.py` |
| Native Host | `native_host/host.py:main()` or `native_host/dist/shopee_native_host.exe` |
| Extension service worker | `chrome_extension/background.js` |
| Content script | `chrome_extension/content.js` |
| Extractor core | `chrome_extension/extractor_core.js` |
| Manual UI | `chrome_extension/popup.html` + `popup.js` |

## Message Protocol

| Message type | Owner | Consumer |
|---|---|---|
| `GET_BRIDGE_STATUS` | Popup | Background |
| `CONNECT_DESKTOP` | Popup | Background |
| `BRIDGE_STATUS_CHANGED` | Background | Popup |
| `EXTRACT_PRODUCT_DATA` | Popup | Content script |
| `GET_COMPLETE_SNAPSHOT` | Background | Content script |
| `AUTHORITATIVE_PRODUCT_COMPLETE` | Content script | Background |
| `SEND_PRODUCT_TO_DESKTOP` | Popup | Background |
| `connect_desktop` | Background | Native Host |
| `bridge_status` | Native Host | Background |
| `hello` | Native Host | Desktop bridge |
| `hello_ack` | Desktop bridge | Native Host |
| `open_product` | Desktop batch queue | Background |
| `process_progress` | Background | Desktop batch queue |
| `process_error` | Background | Desktop batch queue |
| `product_result` | `sendCompleteProductToDesktop()` | Desktop bridge/UI |
| `product_result_ack` | Desktop bridge | Background |
| `cancel_processing` | Desktop batch queue | Background |
| `batch_finished` | Desktop UI | Background |
| `error` | Transport/validation boundary | Background |

`VERIFICATION_REQUIRED` is an `error_code` within `process_error`, not a second top-level protocol message.

## Classification

| Classification | Result |
|---|---|
| ACTIVE | Current files under `src/`, the six extension runtime files, Native Host source/scripts/manifests/spec/executable, active tests, and current docs |
| ACTIVE-BUT-DUPLICATE | None after cleanup |
| LEGACY | Deleted Python browser session, Python metadata extraction, URL resolution, path safety for the retired browser profile, and their workers/tests |
| DEAD / UNREACHABLE | Deleted protocol aliases, sender aliases, popup extraction fallback, obsolete listeners/signals, and old UI handlers |
| GENERATED | Required `native_host/dist/shopee_native_host.exe` and generated host manifest; executable preserved because the installed manifest points to it |
| DEBUG/TEMP | Python caches, pytest/uv caches, test virtual environment, PyInstaller work trees, egg-info, and temporary rebuild output removed |
| UNKNOWN | None |

## Removed Legacy Components

### Python runtime files

| Removed file | Proof / reason |
|---|---|
| `core/browser_session.py` | Instantiated only by the retired account UI; not in batch/bridge call graph; Chrome extension now supplies authenticated page context |
| `core/metadata_extractor.py` | Called only by retired metadata worker/tests; active extraction occurs only in `extractor_core.js` |
| `core/url_resolver.py` | Called only by retired resolver/metadata generations; active worker tab navigates the submitted URL |
| `core/path_safety.py` | Protected the retired application-owned Chrome profile/session cleanup path; no active runtime consumer |
| `workers/auth_worker.py` | Instantiated only by retired account UI |
| `workers/metadata_worker.py` | No active batch/UI import after Native Messaging migration |
| `workers/url_resolver_worker.py` | No active batch/UI import after `open_product` became canonical |

The associated eager exports/imports were removed from `core/__init__.py`, `workers/__init__.py`, and `MainWindow`. Obsolete account/session controls and their handlers were removed with that architecture.

### Obsolete tests

- `tests/test_auth_session.py`
- `tests/test_metadata_extractor.py`
- `tests/test_url_resolver.py`

These tests protected deleted browser-automation and Python-extraction implementations, not the active extension architecture. Current URL validation, folder behavior, queue, UI, bridge, Native Messaging, and real JavaScript extractor tests remain.

### Stale specifications

The numbered bootstrap/implementation-generation specifications under `docs/specs/` were deleted. Several presented Playwright, direct extension WebSocket, `process_url`, `RUN_FULL_SCAN`, and obsolete permissions as active requirements. Current behavior is documented in `ARCHITECTURE.md`, `TESTING.md`, `TASKS.md`, the component READMEs, and this report.

### Removed functions, branches, and messages

- Desktop `process_url` creator, signal, sender, and protocol validation branch.
- Separate top-level `verification_required` protocol message; verification remains `process_error.error_code`.
- Background `process_url` compatibility dispatch and `sendProductSnapshotToDesktop` alias.
- Background popup action aliases and unused explicit disconnect action.
- Content-script `PING_SCANNER` and `RUN_FULL_SCAN` listeners.
- Popup `chrome.scripting.executeScript()` extraction fallback and popup-built manual product payload.
- Native Host `get_status`, `ping`, and Chrome-side `hello` aliases; only `connect_desktop` owns connection requests.
- Unused bridge client signals, duplicate queue lookup maps, and unused queue status constants.
- Native Host product-field logging/business inspection; payload relay is transport-only.

## Consolidated Components

| Before | Canonical result |
|---|---|
| Python metadata/HTML extraction + content extraction | `chrome_extension/extractor_core.js` only |
| `open_product` + `process_url` automatic commands | `open_product` only |
| Automatic sender + manual sender alias/popup payload fallback | `background.js:sendCompleteProductToDesktop()` only |
| Content automatic/polling handlers | One content listener with `GET_COMPLETE_SNAPSHOT` and `EXTRACT_PRODUCT_DATA` |
| Popup direct script execution + content RPC | Content RPC only |
| UI direct batch update + queue `item_completed` update | Queue owns correlated completion; UI updates once from `item_completed` |
| Duplicate request/product lookup maps | `MainWindow._rows_by_request_id` and `_rows_by_product_key` only |

## Dependency Audit

No runtime dependency was removed because `pyproject.toml` already contained no Playwright, Selenium, CDP, HTTP extractor, or third-party Native Host WebSocket package. Active dependencies remain:

- `PySide6` for the desktop and Qt WebSocket server.
- Python standard library for the Native Host WebSocket client and Native Messaging framing.
- `pytest`, `pytest-qt`, and `pyinstaller` in the development extra.

`uv.lock` was synchronized with the already-declared `pyinstaller` development extra; this does not add an application runtime dependency.

## Test Results

| Run | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Before cleanup | 198 | 0 | 0 |
| After cleanup | 114 | 0 | 0 |

The lower post-cleanup count is from deleting tests whose only subject was removed legacy code. The active-architecture suite was not weakened: it includes protocol ownership, one result builder, no direct Chrome WebSocket, queue/UI behavior, Native Messaging transport, and extractor-core behavior.

## Remaining Known Bug

The known regression remains intentionally unfixed: automatic processing returns four images for the known case while manual Chrome extension extraction can return nine.

No live Chrome profile, cookies, credentials, or user data were inspected to re-diagnose the case. `test_main_window_batch_preserves_received_four_images` verifies that the cleaned desktop path stores and displays the four received images without synthesizing, replacing, or truncating them. No root cause is claimed in this cleanup report.

## Remaining Search Occurrences

- `Playwright` / `Selenium`: only historical removal statements and negative architecture assertions in tests/docs; no imports, dependencies, or runtime calls.
- Direct extension WebSocket terms: only negative documentation/tests. Active WebSocket source is `ExtensionBridgeServer` plus `native_host/ws_client.py`, exclusively for Native Host ↔ desktop.
- `process_url`, `RUN_FULL_SCAN`, `PING_SCANNER`: only negative regression assertions/documentation; no handler or dispatch remains.
- `cache` and `temporary_scan_status`: active transactional `ProductCache` behavior inside `extractor_core.js` and popup debug display/tests. They are part of the canonical extractor, not compatibility routing.
- `structured_data`: active fallback source selection inside `extractor_core.js`; it is not a second extractor and cannot independently claim authoritative completeness.
- `images` / `image_count`: active protocol/model fields with integrity checks.
- `product_result`: multiple transport consumers/tests are expected; there is exactly one extension construction site, inside `sendCompleteProductToDesktop()`.

## Known Technical Debt Remaining

- The four-image automatic/manual nine-image regression must be diagnosed next without introducing another extractor or protocol path.
- Image downloading and output-folder writing are not implemented, although the desktop button still says **Bắt đầu tải ảnh**.
- The generated Native Host executable is required by the current manifest. A cleaned-source rebuild succeeded in a temporary directory, but the installed executable was locked by a running Native Messaging process and was therefore preserved rather than overwritten; no Chrome or Native Host process was terminated.
- Extension state-machine tests evaluate the service worker with mocks and remain implementation-aware, although they protect the current message ownership and correlation rules.

## Final Architecture Counts

```yaml
Number of active Shopee extraction implementations: 1
Number of active automatic batch flows: 1
Number of active extension product_result builders: 1
Direct Chrome WebSocket still active: NO
Legacy Playwright still active: NO
Native Host ↔ desktop WebSocket preserved: YES
Known behavior changes caused by cleanup: NONE
```
