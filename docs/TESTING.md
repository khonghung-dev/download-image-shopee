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
- Task 007A's desktop integration creates an empty folder, stores its `Path` on the existing product model, and preserves all nine image URLs unchanged.

## Task 007A filesystem regressions

- Windows-invalid characters (`< > : " / \\ | ? *`) and ASCII controls become readable `_` separators.
- Whitespace is collapsed while Vietnamese/Unicode text remains unchanged.
- Trailing dots/spaces, reserved device basenames, empty titles, and overlong titles are made safe deterministically.
- Path-like titles remain a single component whose resolved target is a direct child of the selected existing output root.
- A primary-name collision uses `<name> [<shop_id>-<item_id>]` without overwriting the existing directory.
- No image bytes or other files are written by Task 007A.

Do not weaken extraction tests to make a failing implementation appear green. Record pre-existing failures separately from cleanup-introduced failures.
