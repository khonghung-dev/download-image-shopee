# Current Tasks

This file tracks the current architecture, not superseded implementation generations.

## Complete

- [x] PySide6 desktop entry point and responsive main window.
- [x] Multiline Shopee URL validation and duplicate filtering.
- [x] Output-folder selection and persistence.
- [x] Sequential batch queue with correlation, timeout, cancellation, and verification pause/resume.
- [x] Loopback-only Qt WebSocket bridge.
- [x] Chrome Native Messaging Host and required build/install assets.
- [x] Manifest V3 extension worker-tab orchestration.
- [x] One content-script RPC boundary.
- [x] One canonical Shopee extractor: `chrome_extension/extractor_core.js`.
- [x] One canonical extension `product_result` builder: `sendCompleteProductToDesktop()`.
- [x] Manual extension extraction and manual send through the same result builder.
- [x] Restore manual full-carousel enumeration for the five-visible-media Shopee gallery (nine images plus one excluded video).
- [x] Architecture cleanup removing browser automation, direct extension WebSockets, duplicate protocols, and obsolete tests.

## Frozen known regression

- [ ] Diagnose why the known automatic flow returns four images while manual extraction can return nine.

Do not address this item as part of architecture cleanup. Its current behavior is protected as a regression baseline for the next debugging task.

## Planned product work

- [ ] Download image bytes outside the Qt GUI thread.
- [ ] Create Windows-safe per-product folders.
- [ ] Write image files atomically with retries and per-item error reporting.
- [ ] Package and verify the full desktop application distribution.
