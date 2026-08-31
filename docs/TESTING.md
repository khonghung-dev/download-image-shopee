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
| `test_product_folder.py` | Unicode/Windows sanitization, device names, fallback and length policy, containment, output-root failures, and provisional collisions |
| `test_image_downloader.py` | Ordered filenames, MIME extensions, bounded retries/timeouts, invalid responses, atomic cleanup, existing-file skip, nine-image model integration, cancellation, and QThread execution |
| `test_task_010_batch_reliability.py` | 10-item FIFO execution, middle-stage failure continuation, stale extraction/worker events, double start, cancellation terminalization, product isolation, GUI responsiveness, worker cleanup, and close-during-download |

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
- A primary-name collision uses `<name> [<shop_id>-<item_id>]` without overwriting the existing directory.
- Task 007A unit tests still create directories only. Task 007B integration tests write controlled image files only inside those directories.

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

Do not weaken extraction tests to make a failing implementation appear green. Record pre-existing failures separately from cleanup-introduced failures.
