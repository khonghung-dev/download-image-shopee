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
- [x] Task 007A: Windows-safe Product Folder Manager, desktop success-flow integration, and `product_folder` storage on the existing product model.
- [x] Task 007B: authoritative `product.images` downloader using the Task 007A `product_folder`.
- [x] Sequential MIME-aware filenames, bounded timeout/retry, atomic `.part` commits, and existing-file preservation.
- [x] Background `QThread` download integration; queue completion now waits for the current product's image result.
- [x] Ordered per-image results and product totals stored on the existing desktop product model.
- [x] Task 010: deterministic product lifecycle (`PENDING` → extraction → folder → download → terminal), with guarded transitions.
- [x] Task 010: exactly one active product; the next URL starts only after the previous download worker exits and is cleaned.
- [x] Task 010: strict request/product/folder correlation for extraction and download callbacks, including stale-event rejection.
- [x] Task 010: terminal-item batch progress, separate per-image progress, and state-derived final summaries.
- [x] Task 010: cooperative cancellation of current/pending items and deferred safe application close during active downloads.
- [x] Task 010: worker-owned folder creation and network/file work, leaving the Qt GUI thread responsive.
- [x] Task 010: 10-product, middle-failure, stale-result, double-start, cancellation, responsiveness, cleanup, shutdown, and isolation regressions.

## Frozen extraction regression

- [x] Known nine-image-plus-one-video product produces nine authoritative images in the automatic flow.
- [x] The manual extension send uses the same authoritative nine-image result path.

Tasks 007A/007B do not modify the extension, Native Host, gallery traversal, video filtering, or authoritative cache. Task 007B only adds a desktop-only result field to the parsed desktop model.

## Planned product work

- [ ] Task 011: generalized product retry/error UX and retrying failed batch items.
- [ ] Task 012: replace the provisional folder collision suffix with full duplicate-product handling.
- [ ] Package and verify the full desktop application distribution.

Task 007A remains the sole owner of directory creation. Task 007B writes only controlled sequential image files inside that validated directory and does not implement broader duplicate-product policy.

Task 010 does not change the Chrome Extension, Native Host, extraction protocol, gallery traversal, authoritative cache, Task 007B retry limits, or Task 012 duplicate-product policy.
