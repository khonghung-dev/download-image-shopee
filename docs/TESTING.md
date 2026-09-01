# Testing

The suite is offline and protects the current architecture rather than deleted implementation generations.

## Test modules

| Module | Coverage |
|---|---|
| `test_app.py` | QApplication and desktop bootstrap |
| `test_url_validator.py` | Multiline parsing, accepted Shopee domains, invalid input, exact deduplication |
| `test_settings.py` | Output-folder persistence and restoration |
| `test_batch_queue.py` | FIFO order, one in-flight request, correlation, failure continuation, timeout, verification, cancellation |
| `test_bridge_protocol.py` | Directional active protocol, validation, size/version checks, product integrity |
| `test_bridge_server.py` | Loopback Qt WebSocket handshake, product receipt, disconnect/reconnect |
| `test_native_messaging.py` | Four-byte framing, host manifest, offline/online relay, payload preservation |
| `test_extension_extractor.py` | Real JavaScript extractor behavior, service-worker state, worker tab, canonical sender, architecture boundaries |
| `test_ui.py` | Current widgets, start guard, queue/bridge integration, single row updates, manual deduplication |
| `test_product_folder.py` | Unicode/Windows sanitization, device names, fallback and length policy, containment, output-root failures, and identity-suffixed collisions |
| `test_image_downloader.py` | Ordered filenames, MIME extensions, bounded retries/timeouts, invalid responses, atomic cleanup, existing-file skip, nine-image model integration, cancellation, and QThread execution |
| `test_task_010_batch_reliability.py` | 10-item FIFO execution, middle-stage failure continuation, stale extraction/worker events, double start, cancellation terminalization, product isolation, GUI responsiveness, worker cleanup, and close-during-download |
| `test_task_011_error_retry.py` | Canonical classification, product retry/exhaustion, verification, stale attempt generations, 429/4xx/5xx policy, permission/disk full, cancellation/close backoff safety, multi-product totals, and nine-image preservation |
| `test_task_012_duplicate_handling.py` | Canonical product keys, atomic markers, cross-run reuse/collisions, duplicate claims, same-batch skip, failure/retry distinctions, partial/complete reuse, zero-byte replacement, and image preservation |
| `test_task_013_product_metadata.py` | Schema/identity/source fields, readable UTF-8, image order/filenames/statuses, partial/skipped summaries, atomic replacement/failure, marker independence, automatic/manual lifecycles, duplicate no-rewrite, and nine-image preservation |
| `test_task_014_ui_polish.py` | Initial/running/finished/cancelled UI states, parser-derived URL count, retry/duplicate/partial displays, per-image and metadata progress, long content, row stability, and second-batch reuse |

Deleted Playwright authentication, Python metadata-extractor, URL-resolver, and workaround-protocol tests are not part of the active suite.

## Run all tests

With an installed development environment:

```powershell
pytest -ra
```

With uv:

```powershell
uv run --extra dev pytest -ra
```

Run Qt tests headlessly when needed:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
pytest -ra
```

JavaScript syntax checks require Node.js and are invoked by `test_extension_extractor.py`. Tests must not use live Shopee pages, personal Chrome profile data, cookies, passwords, the Windows registry, or user output images.

## Required architecture regressions

- Exactly one `product_result` construction in `background.js`.
- No `new WebSocket` or `ws://127.0.0.1:8765` in extension JavaScript.
- No `process_url`, `RUN_FULL_SCAN`, or `PING_SCANNER` compatibility path.
- No popup `executeScript` extraction or popup-authored product payload.
- No DOM extraction in `background.js`.
- The Native Host/Desktop localhost WebSocket remains operational.
- The known nine-image-plus-one-video product remains nine authoritative images in automatic and manual code paths.
- Task 007A's desktop integration creates and stores the product folder `Path`; Task 007B writes all nine mock images there and preserves all nine authoritative URLs unchanged.

## Task 007A filesystem regressions

- Windows-invalid characters (`< > : " / \\ | ? *`) and ASCII controls become readable `_` separators.
- Whitespace is collapsed while Vietnamese/Unicode text remains unchanged.
- Trailing dots/spaces, reserved device basenames, empty titles, and overlong titles are made safe deterministically.
- Path-like titles remain a single component whose resolved target is a direct child of the selected existing output root.
- Every newly managed folder receives an atomic `.shopee-product-id` marker containing only `shop_id:item_id`.
- A unique marker-owned folder is reused even when the incoming title changes; it is not renamed.
- An unmarked, corrupt-marker, or mismatched-marker title collision is preserved and uses `<name> [<shop_id>-<item_id>]` rather than being adopted.
- Equal titles with different product keys remain separate, while multiple valid folders claiming one key fail without modification.
- Discovery is limited to immediate output-root children and unsafe symlink/reparse containment is never used as a managed product folder.
- Task 007A/012 storage tests create only managed directories and their identity markers. Task 007B integration tests write controlled image files only inside those directories.

## Task 007B downloader regressions

- Tests use scripted/local HTTP responses only; they never access Shopee or its CDN.
- Input order is authoritative: index 0 maps to `01`, index 1 to `02`, and so on regardless of response characteristics.
- Padding is at least two digits and expands to three for a 120-image gallery.
- Valid `image/jpeg`, `image/png`, and `image/webp` responses produce matching extensions and exact response bytes.
- HTTP 500 and timeouts retry within the configured maximum; HTTP 404, HTML/JSON, and empty responses fail without inappropriate retries.
- Failed and cancelled transfers leave no `.part` or corrupted final file, while earlier completed images remain.
- A non-empty exact target is preserved byte-for-byte and reported as `SKIPPED_EXISTING`.
- A nine-URL desktop product produces nine final files, `total=9`, `successful=9`, `failed=0`, and an unchanged nine-entry `images` list.
- Queue tests prove that Product B is not opened when Product A merely receives its extension result; Product A's background image result must arrive first.
- A Qt test records the downloader thread identity and verifies it differs from the GUI/test thread.

## Task 010 batch regressions

- Ten successful mock products retain input order, reach `SUCCESS`, and never exceed one active product.
- Extraction, folder, or downloader failure for the middle product produces `SUCCESS / FAILED / SUCCESS` and reaches full terminal progress.
- Late `product_result`, extraction progress, image progress, and download completion from Product A cannot mutate Product B.
- A repeated `start_batch()` while running returns `False` and emits no second `open_product`.
- Cancelling while Product 3 downloads opens no Product 4, cooperatively stops the worker, marks current/pending items `CANCELLED`, and reaches a complete terminal summary.
- Product models copy mutable image lists at boundaries, preserving per-item data isolation and the authoritative nine-image list.
- A deliberately held background download allows a GUI `QTimer` to fire, proving the Qt event loop is not blocked by product filesystem/network work.
- Sequential controller runs publish terminal outcomes only after QThread exit and cleared worker/thread references.
- Closing a visible window during a cooperative download defers the close until the controller is idle, with no remaining worker/thread references or `.part` files.

Task 010 tests use synthetic models, test doubles, and local filesystem paths only. They do not access Shopee, change the extension/native stack, add generalized retry behavior, or implement Task 012 duplicate semantics.

## Task 011 error/retry regressions

- `PRODUCT_TIMEOUT` followed by success uses the same queue item and row, creates one product folder, and starts one download pipeline.
- Three transient failures produce exactly three total attempts; the failed item then advances to the next product.
- `NOT_FOUND` and output/path/permission errors fail on the first attempt without a backoff timer.
- `VERIFICATION_REQUIRED` pauses the queue; manual resume preserves the attempt count and uses no automatic retry timer.
- A new request ID is generated for each automatic attempt. Late results and errors carrying the prior ID cannot mutate or complete the current attempt.
- Cancelling or closing during `WAITING_RETRY` stops the single-shot timer and cannot emit a later `open_product`.
- HTTP 404 performs one request; HTTP 500 retries only to the configured maximum; HTTP 429 honors a valid `Retry-After` value clamped to the configured bound. Injected sleepers make these tests instantaneous.
- Folder and download-write `PermissionError` plus `ENOSPC`/Windows disk-full classification are permanent. Disk-full performs one write attempt, leaves no `.part`, and preserves prior completed files.
- Mixed `A transient→success / B not found / C success` input remains three products with `SUCCESS / FAILED / SUCCESS` terminal states.
- A nine-image authoritative list remains unchanged through a product retry and entry into the folder/download pipeline.

Task 011 tests are offline and use Qt timers, scripted HTTP responses, injected timing, and temporary local folders. Product-level automatic retry stops before folder creation; image-level retry remains owned solely by Task 007B.

## Task 012 identity/reuse regressions

- Exact duplicate URL lines remain first-seen deduplicated by `parse_url_lines()` before queue creation; Task 012 does not move or change that rule.
- Different accepted URLs resolving to one canonical `shop_id:item_id` retain two queue items: the first fully succeeds and the second reaches terminal `SKIPPED_DUPLICATE` without a second worker/download.
- Terminal duplicate items count toward overall `finished / total`, have no retry policy, and are shown separately in the final summary.
- A failed or partial first item does not make a later same-key item reusable.
- A Task 011 retry changes `request_id` for the same logical item and succeeds normally; it is not `SKIPPED_DUPLICATE`.
- Cross-run marker reuse always invokes the current Task 007B downloader. Complete existing files are preserved/skipped, partial folders complete missing files, zero-byte targets are replaced, and `.part` cleanup remains centralized.
- Folder discovery uses only `.shopee-product-id`; titles, input URLs, image URLs, image counts, filenames, and folder names are never identity evidence.
- The nine-image authoritative list remains nine entries after same-batch resolution, marker reuse, and download completion.
- Manual Extension → Desktop sends still update by product key and reuse the marker-owned folder without changing automatic queue state.

`.shopee-product-id` is the internal identity/ownership marker; Task 013's `product.json` does not participate in folder discovery or adoption.

## Task 013 metadata regressions

- `schema_version` is integer `1`; identity fields use the existing canonical `shop_id:item_id` property, and automatic metadata uses the logical queue item's original input URL.
- `image_count` and the ordered `images` array come only from authoritative `product.images`; the known nine-image-plus-one-video model remains nine entries and is not mutated.
- Per-image metadata preserves exact downloader filenames (`.jpg`, `.webp`, `.png`) as portable relative paths and maps current statuses to `success`, `failed`, and `skipped_existing`.
- Failed authoritative images remain represented. `download.total/successful/failed/skipped` retain the final current-run downloader counters, and product status is `partial` when any image failed.
- Vietnamese product names are emitted directly as valid UTF-8 rather than escaped `\\uXXXX` sequences.
- Reprocessing atomically replaces one `product.json` through `product.json.tmp`; no numbered metadata or temporary file remains after success.
- Simulated atomic-replace failure preserves completed image bytes and the prior valid metadata, produces controlled `METADATA_WRITE_ERROR` at `ErrorStage.METADATA`, and leaves no corrupted final JSON.
- A title change reuses the marker-owned folder but refreshes `product_name`; missing metadata does not weaken marker reuse, and metadata alone never claims an unmarked folder.
- Automatic and manual Extension → Desktop managed workers share the one metadata writer after their final download result.
- A same-batch `SKIPPED_DUPLICATE` performs no second download, folder creation, or metadata rewrite.

Task 013 tests use local synthetic models and downloader doubles only. They do not access Shopee, store sensitive values or absolute local paths, alter extraction code, delete stale images, rename folders, or add a catalog/database.

## Task 014 UI regressions

- Initial state keeps URL/output controls available, Start reusable under the existing validation behavior, Cancel disabled, and overall progress at zero.
- Running state disables Start and input/output editing, enables one Cancel action, shows `Sản phẩm finished/total`, and keeps image progress separate.
- Verification pauses the queue with Start disabled, Cancel available, an explicit `Tiếp tục` action, and concise Chrome instructions; it does not start an automatic retry timer.
- Retry presentation shows `Đang thử lại 2/3...` on the same queue item and table row across the new transport request ID.
- Success, partial, failure, duplicate, and cancellation text comes from authoritative `ItemState`/download results. `SKIPPED_DUPLICATE` is handled rather than red failure, and `SKIPPED_EXISTING` contributes to available images.
- A nine-image result renders `9/9` after success without mutating the nine-entry authoritative model. A partial eight-of-nine result renders `8/9` and never claims `9/9` success.
- Final summaries count terminal item states rather than table strings, controls are restored after every terminal batch, and a second batch starts without application restart.
- Long output paths remain intact in the read-only flexible field and tooltip; long product names remain intact in the item/model while the table elides their display.
- Default, minimum-size, and expanded layouts use Qt layouts/header policies instead of absolute positioning, keeping primary controls visible under common Windows display scaling.

Task 014 tests use the offscreen Qt platform, synthetic bridge products, and deterministic controller doubles. They do not access Shopee, Chrome, or the network.

Do not weaken extraction tests to make a failing implementation appear green. Record pre-existing failures separately from cleanup-introduced failures.
