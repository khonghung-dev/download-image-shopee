# Testing

The suite is offline and protects the current architecture rather than deleted implementation generations.

## Test modules

| Module | Coverage |
|---|---|
| `test_app.py` | QApplication and desktop bootstrap |
| `test_url_validator.py` | Multiline parsing, accepted Shopee domains, invalid input, exact deduplication |
| `test_settings.py` | Output-folder persistence and restoration |
| `test_batch_queue.py` | FIFO order, one in-flight product, correlation, failure continuation, timeout, pause/verification, cancellation |
| `test_bridge_protocol.py` | Directional active protocol, validation, size/version checks, product integrity |
| `test_bridge_server.py` | Loopback Qt WebSocket handshake, product receipt, disconnect/reconnect |
| `test_native_messaging.py` | Four-byte framing, host manifest, offline/online relay, payload preservation |
| `test_extension_extractor.py` | Real JavaScript extractor behavior, service-worker state, worker tab, canonical sender, architecture boundaries |
| `test_ui.py` | Current widgets, start guard, queue/bridge integration, single row updates, manual deduplication |
| `test_product_folder.py` | Unicode/Windows sanitization, device names, fallback and length policy, containment, output-root failures, and identity-suffixed collisions |
| `test_image_downloader.py` | Ordered filenames/results, MIME extensions, bounded retries/timeouts and image concurrency, invalid responses, atomic cleanup, existing-file skip, nine-image model integration, cancellation, and QThread execution |
| `test_task_010_batch_reliability.py` | 10-item FIFO execution, middle-stage failure continuation, stale extraction/worker events, double start, cancellation terminalization, product isolation, GUI responsiveness, worker cleanup, and close-during-download |
| `test_task_011_error_retry.py` | Canonical classification, product retry/exhaustion, verification, stale attempt generations, 429/4xx/5xx policy, permission/disk full, cancellation/close backoff safety, multi-product totals, and nine-image preservation |
| `test_task_012_duplicate_handling.py` | Canonical product keys, atomic markers, cross-run reuse/collisions, duplicate claims, same-batch skip, failure/retry distinctions, partial/complete reuse, zero-byte replacement, and image preservation |
| `test_task_013_product_metadata.py` | Schema/identity/source fields, readable UTF-8, image order/filenames/statuses, partial/skipped summaries, atomic replacement/failure, marker independence, automatic/manual lifecycles, duplicate no-rewrite, and nine-image preservation |
| `test_task_014_ui_polish.py` | Initial/running/paused/finished/cancelled UI states, parser-derived URL count, retry/duplicate/partial displays, per-image and metadata progress, long content, row stability, and second-batch reuse |
| `test_task_015_reliability.py` | 100-product all-success/mixed stress, repeated batches, stale/duplicate signals, staged cancellation, cancel-to-new-batch, bridge reconnect, verification, network/temp-file matrix, metadata recovery, 5/9 partial recovery, reprocessing, title/path stress, progress flood, ownership audit, and nine-image end-to-end metadata |
| `test_task_015b_pre_release.py` | 30-second product timeout budget, desktop/extension alignment, cooperative pause boundaries, verification generation safety, optional sidecar matrix/registry recovery, URL grid editing/paste/copy, progress placement, bounded image concurrency/order/pause/cancel/failure |
| `test_task_015c_theme.py` | Dark/light defaults and `QSettings` persistence, transparent-label selector regression, complete theme surfaces, remembered window theme, and live running/paused state preservation |
| `test_task_016a_release.py` | Public-key-derived stable Extension ID, path independence, historical runtime-ID absence, self-locating HKCU-only release scripts, ONEDIR spec, exact Vietnamese README identity, and Native Host build failure propagation |

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
- With marker export enabled, a newly managed folder receives an atomic `.shopee-product-id` containing only `shop_id:item_id`; with it disabled, an atomic app-local registry records the folder instead.
- A unique marker-owned folder is reused even when the incoming title changes; it is not renamed.
- An unmarked, corrupt-marker, or mismatched-marker title collision is preserved and uses `<name> [<shop_id>-<item_id>]` rather than being adopted.
- Equal titles with different product keys remain separate, while multiple valid folders claiming one key fail without modification.
- Discovery is limited to immediate output-root children and unsafe symlink/reparse containment is never used as a managed product folder.
- Storage tests create only managed directories and explicitly selected sidecars. Task 007B integration tests write controlled image files only inside those directories.

## Task 007B downloader regressions

- Tests use scripted/local HTTP responses only; they never access Shopee or its CDN.
- Input order is authoritative: index 0 maps to `01`, index 1 to `02`, and so on regardless of response characteristics.
- At most four image transfers are active for one product; completion order cannot change final result order, filename/index mapping, or progress totals.
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
- `VERIFICATION_REQUIRED` pauses both transport timers; manual resume preserves the attempt count, creates one fresh request generation, and uses no automatic retry timer.
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
- Cross-run marker or validated app-local-registry reuse always invokes the current Task 007B downloader. Complete existing files are preserved/skipped, partial folders complete missing files, zero-byte targets are replaced, and `.part` cleanup remains centralized.
- A unique exact `.shopee-product-id` claim has precedence. Otherwise a registry mapping is accepted only for one existing, contained, non-reparse immediate child with no marker or an agreeing marker. Titles, input URLs, image URLs, image counts, and filenames are never identity evidence.
- The nine-image authoritative list remains nine entries after same-batch resolution, marker reuse, and download completion.
- Manual Extension → Desktop sends still update by product key and reuse the marker-owned folder without changing automatic queue state.

`.shopee-product-id` and the small app-local registry are the two identity mechanisms; Task 013's `product.json` does not participate in folder discovery or adoption.

## Task 013 metadata regressions

- `schema_version` is integer `1`; identity fields use the existing canonical `shop_id:item_id` property, and automatic metadata uses the logical queue item's original input URL.
- `image_count` and the ordered `images` array come only from authoritative `product.images`; the known nine-image-plus-one-video model remains nine entries and is not mutated.
- Per-image metadata preserves exact downloader filenames (`.jpg`, `.webp`, `.png`) as portable relative paths and maps current statuses to `success`, `failed`, and `skipped_existing`.
- Failed authoritative images remain represented. `download.total/successful/failed/skipped` retain the final current-run downloader counters, and product status is `partial` when any image failed.
- Vietnamese product names are emitted directly as valid UTF-8 rather than escaped `\\uXXXX` sequences.
- Reprocessing atomically replaces one `product.json` through `product.json.tmp`; no numbered metadata or temporary file remains after success.
- Simulated atomic-replace failure preserves completed image bytes and the prior valid metadata, produces controlled `METADATA_WRITE_ERROR` at `ErrorStage.METADATA`, and leaves no corrupted final JSON.
- A title change reuses the marker-owned folder but refreshes `product_name`; missing metadata does not weaken marker reuse, and metadata alone never claims an unmarked folder.
- When selected, automatic and manual Extension → Desktop managed workers share the one metadata writer after their final download result; when off, they leave existing metadata untouched.
- A same-batch `SKIPPED_DUPLICATE` performs no second download, folder creation, or metadata rewrite.

Task 013 tests use local synthetic models and downloader doubles only. They do not access Shopee, store sensitive values or absolute local paths, alter extraction code, delete stale images, rename folders, or add a catalog/database.

## Task 014 UI regressions

- Initial state keeps URL/output/optional-export controls available, Start reusable under the existing validation behavior, Pause/Cancel disabled, and overall progress at zero.
- Running state disables Start and input/output editing, enables Pause and one Cancel action, shows `Sản phẩm finished/total`, and keeps image progress separate.
- User pause reaches a cooperative extraction/download/between-product boundary, exposes `Tiếp tục`, and neither starts the next product nor duplicates the worker pipeline.
- Verification pauses the queue with Start disabled, Cancel available, the same button reading `Tiếp tục sau xác minh`, concise Chrome instructions, and no automatic retry timer.
- Retry presentation shows `Đang thử lại 2/3...` on the same queue item and table row across the new transport request ID.
- Success, partial, failure, duplicate, and cancellation text comes from authoritative `ItemState`/download results. `SKIPPED_DUPLICATE` is handled rather than red failure, and `SKIPPED_EXISTING` contributes to available images.
- A nine-image result renders `9/9` after success without mutating the nine-entry authoritative model. A partial eight-of-nine result renders `8/9` and never claims `9/9` success.
- Final summaries count terminal item states rather than table strings, controls are restored after every terminal batch, and a second batch starts without application restart.
- Long output paths remain intact in the read-only flexible field and tooltip; long product names remain intact in the item/model while the table elides their display.
- Default, minimum-size, and expanded layouts use Qt layouts/header policies instead of absolute positioning, keeping primary controls visible under common Windows display scaling.

Task 014 tests use the offscreen Qt platform, synthetic bridge products, and deterministic controller doubles. They do not access Shopee, Chrome, or the network.

## Task 015 Reliability Gate

Task 015 automated acceptance is offline and deterministic. The unchanged Tasks 001–014 baseline completed with 233 passed in 49.11 seconds. After the Task 015 tests and the one evidence-backed storage fix, the full suite completed with 280 passed, 0 failed, and 0 skipped in 57.19 seconds.

Automated acceptance includes:

- 100 unique successful products in FIFO order with exactly 100 terminal items, final progress 100/100, unique dispatch IDs, and maximum one active logical product.
- A deterministic mixed 100-product batch covering permanent failure, transient retry then success, duplicate products, partial image results, and skipped existing files, with exact terminal accounting and product-key isolation.
- Three sequential batches in one `MainWindow` lifetime, stale prior-batch callback rejection, row-map reset, reusable controls, inactive timers, and no duplicate controller start.
- Repeated stale request generations and rapid duplicate extraction/progress/metadata/terminal/error events without double start, double terminal transition, or double advance.
- Cancellation during opening, extraction, retry, folder creation, downloading, and metadata presentation; cancel-to-new-batch isolation; cancellation/close-safe retry timers; cooperative active-worker close.
- Application-owned QThread cleanup, controller `_thread`/`_worker`/`_context` release, no growing worker collection, and no Qt thread-destroyed failure.
- Timeout, reset, 429, 500, 502, 503, 504, 404, HTML, JSON, empty-body, mid-transfer, permission, and disk-full handling with bounded attempts and no handled orphan `.part`.
- Atomic `product.json` failure/recovery, prior valid JSON preservation, temp cleanup, marker conflict preservation, 5-of-9 partial recovery, complete cross-run reprocessing, and correct current-run metadata.
- Forty same-title products with distinct markers, Unicode/emoji/combining/reserved/path-like title containment, malicious-title output-root containment, and marker/image/metadata destination ownership.
- A 5,000-event worker progress flood while the Qt event loop continues to deliver a timer and cancellation without calling `QApplication.processEvents()`.
- Known nine-image authoritative data through the real desktop worker, nine final images, and `product.json` `image_count == 9` with nine image entries.

The Task 015 failure evidence was a 273-UTF-16-unit atomic marker temp path created from a 96-unit output root, a 120-unit product component, two separators, and a 55-unit marker temp filename. Windows created the product directory but failed the marker temp open with `FileNotFoundError`. The Product Folder Manager now retains the 120-unit ceiling while reducing the component for the resolved root depth and reserves the exact marker temp budget. The regression covers long Vietnamese, emoji, and combining-Unicode names under deep temporary roots; existing marker/collision/reuse tests remain green.

The ownership audit treats `BatchQueueManager._known_request_ids` as deliberate session-lifetime tombstones: old automatic request IDs must remain recognizable so a late result can never be reinterpreted as a manual Extension send while the window is idle. The repeated audit recorded exactly one tombstone per issued generation (100 IDs), while live queue items/reusable products are replaced per batch, UI row maps are cleared per batch, both timers are inactive at terminal state, and controller worker/thread/context references are released. This safety history is intentional rather than a worker/timer leak.

The executed evidence ledger is `docs/TASK_015_RELIABILITY_MATRIX.md`. Live Shopee remains manual-only; use `docs/TASK_015_MANUAL_SOAK.md` for the 30+ URL sequential soak, known 9-image automatic/manual check, 20+ URL cancellation and second batch, network interruption, and normal close/reopen recovery. Do not modify extraction code based only on live variability; capture product identity, runtime/debug logs, and current DOM evidence first.

## Task 015B pre-release gate

The untouched Task 015 baseline completed with 280 passed, 0 failed, and 0 skipped in 49.39 seconds. After Task 015B, the final full suite completed with 307 passed, 0 failed, and 0 skipped in 32.59 seconds. Task 015B adds offline, deterministic regressions for:

- one canonical 9,000 ms product-attempt timeout in Python and the extension, three total attempts, one/two-second non-blocking backoff, and an exact modeled maximum of 30 seconds;
- one state-aware Pause/Resume/verification button, safe extraction/retry/download/between-product boundaries, cancellation while paused, reusable new batches, and fresh verification request correlation;
- four independent `product.json`/`.shopee-product-id` option combinations, both off by default, no deletion when off, marker precedence, durable marker-free registry reuse, corrupt/stale/conflicting registry recovery, and atomic registry failure safety;
- the model-backed URL grid's structural trailing row, single-click selection, double-click/F2 editing, Delete, multiline paste, exact multiline copy, keyboard navigation, and unchanged canonical URL parsing/deduplication;
- right-side `0%`/`40%`/`100%` progress text and resize-safe splitter/card layout;
- at most four concurrent images within one product, strictly sequential products, authoritative filename/result order, cooperative pause drain, cancellation cleanup, and isolation of one failed image;
- frozen extraction/native boundaries, JavaScript syntax, and the unchanged single canonical extractor/result builder.

Live Chrome/Shopee acceptance is intentionally manual because automated tests must not access a personal Chrome profile or depend on live Shopee state. Before packaging, a developer must still verify the known nine-image product end to end, measure an actual repeatedly failing product, and perform the 30-product mixed-output soak including pause, cancel, verification, and a second batch. Task 015B does not build an executable.

## Task 015C theme gate

The untouched Task 015B baseline completed with 307 passed, 0 failed, and 0 skipped in 24.96 seconds. After Task 015C, the final clean full-suite rerun completed with 312 passed, 0 failed, and 0 skipped in 38.49 seconds. Task 015C adds offline deterministic regressions for:

- missing/invalid theme settings defaulting to dark, explicit light/dark persistence, and reconstruction of a window with the remembered theme;
- normal/section label selectors remaining transparent while the connection frame retains a semantic badge surface;
- complete dark/light URL table, result table, inputs, buttons, checkboxes, progress, scrollbar, selection, disabled, tooltip, and status-tone styling;
- live toggles during `RUNNING` and `PAUSED_USER` without changing the queue/current item, pause label, URL model, result rows, progress, checkbox values, or connection-state property.

Chrome/Shopee acceptance remains manual, including the known nine-image automatic/downloaded/manual counts, foreground worker-tab behavior, verification, and actual failing-product wall time. Automated tests do not access a live page, Chrome profile, cookies, passwords, tokens, OTP data, or personal browser state. Task 015C does not build an executable.

## Task 016A identity and Windows release gate

The untouched Task 016A baseline completed with 311 passed, 0 failed, and 0 skipped. The final source suite completed with 316 passed, 0 failed, and 0 skipped in 65.81 seconds. Automated release evidence additionally verifies:

- the manifest contains one public SPKI key and independently derives stable ID `bhbnfalghoklngoohdpnjedcdcplbjhm` by Chromium's SHA-256/first-128-bit/nibble mapping;
- relocating the manifest does not change the ID, and the generated development Native Messaging manifest allows only `chrome-extension://bhbnfalghoklngoohdpnjedcdcplbjhm/`;
- production runtime/configuration contains no historical path-derived ID, wildcard origin, private Extension key, Chrome profile operation, Chrome termination, or machine-wide registry target;
- the Desktop spec uses PyInstaller `COLLECT`/ONEDIR, while the fresh Native Host has a different hash/timestamp from the preserved in-use development executable;
- the packaged Desktop launches offscreen and the packaged Native Host completes a real `desktop_connected=true` bridge handshake;
- the release installer derives the ID from the bundled manifest key, generates an absolute host path from its own directory, and registers only `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.shopee_image_downloader.bridge`.

Live Chrome extension loading is deliberately not automated. The user must reload/load unpacked once, verify Chrome displays the exact stable ID, and then execute the packaged known-product, theme, pause/resume, verification, timeout-continuation, duplicate, and second-batch checklist.

## Task 017 final Windows installer gate

The clean pre-change source baseline completed with 316 passed, 0 failed, and 0 skipped in 67.29 seconds after test-only `TEMP`, `APPDATA`, and `LOCALAPPDATA` paths were isolated inside the writable workspace. This redirection avoided accessing or changing the developer's real QSettings and product-folder identity registry.

Static installer gates verify the fixed AppId, canonical `0.1.0` version, `PrivilegesRequired=lowest`, per-user default directory, dedicated versioned Setup output, optional Desktop shortcut, Start Menu entries, installer-specific guide, Task 016 ONEDIR payload routing, install/uninstall script execution with nonzero-exit handling, exact stable Extension/Native Host identities, and the absence of historical IDs, machine-wide access, Chrome policies/profile operations, developer paths, and private Extension key files.

Inno Setup 6.7.3 compiled `ShopeeImageDownloader-Setup-0.1.0.exe` at 42,076,348 bytes with SHA-256 `D9425B4D864FF0F83E3C92172B73B17D8A3FFA12D8F7D014AC5747AE5C955747`. The portable ZIP remains the approved release baseline and was not overwritten.

Automated installer validation passed for a fresh default install, installed GUI launch/clean close, same-version upgrade, exact fixed-AppId uninstall entry, one Start Menu application shortcut, one guide shortcut, optional Desktop shortcut, exact HKCU Native Host registration, generated absolute host path, exact stable origin, full payload hash equivalence, clean uninstall, preserved QSettings/identity-registry hashes, custom user-writable install path, custom uninstall, and final reinstall to the default path. Installed Dark/Light toggling and persistence were exercised through the real GUI accessibility control and the original `light` preference was restored byte-for-byte.

The installed app reported `Chưa kết nối` because no Chrome Extension was loaded or changed during automated validation. Extension reconnect and the installed live 9/9/9/product/pause/verification/timeout/metadata/second-batch matrix remain user-run final acceptance. Their Task 016 portable baseline is still approved, and all 237 payload files carried into the installed program matched that baseline byte-for-byte.

After installer source and its five static gates were added, the final full source suite completed with 321 passed, 0 failed, and 0 skipped in 69.94 seconds.

After compiler discovery/identity-gate integration and the Inno application-close directive correction, the affected Task 017 static suite was rerun separately: 5 passed, 0 failed, and 0 skipped in 0.03 seconds. Unaffected business-core tests were not redundantly rerun.

Do not weaken extraction tests to make a failing implementation appear green. Record pre-existing failures separately from cleanup-introduced failures.
