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
- A four-image automatic result is passed through unchanged; the cleanup must not synthesize the missing images.

Do not weaken extraction tests to make a failing implementation appear green. Record pre-existing failures separately from cleanup-introduced failures.
