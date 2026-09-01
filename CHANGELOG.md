# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added Task 007A's Windows-safe Product Folder Manager and stored `product_folder` on the existing desktop product model.
- Added Task 007B's deterministic standard-library image downloader, MIME-aware sequential filenames, bounded retry/timeout policy, atomic `.part` writes, and structured per-image/product results.
- Added a dedicated Qt worker/controller so image network transfers run outside the GUI thread and the batch queue waits for downloads before advancing.
- Added Task 010's guarded product lifecycle, terminal-state progress, cancellation counts, stale-event regressions, and 10-product reliability coverage.
- Added Task 011's canonical error taxonomy, staged diagnostics, bounded product extraction retry, request-generation correlation, and retry/cancellation regressions.
- Added Task 012's canonical product identity, atomic `.shopee-product-id` ownership marker, cross-run folder reuse, and same-batch `SKIPPED_DUPLICATE` state.
- Added Task 013's schema-versioned UTF-8 `product.json`, pure metadata builder, atomic writer, metadata error stage, and automatic/manual lifecycle coverage.

### Changed
- Consolidated the runtime around PySide6 → localhost WebSocket → Native Host → Chrome Native Messaging → service worker → content script → `extractor_core.js`.
- Made `open_product` the sole automatic batch command and `sendCompleteProductToDesktop()` the sole extension `product_result` builder.
- Made the content script the single extraction RPC boundary for automatic and manual flows.
- Rewrote architecture, testing, task, and extension documentation around the active runtime.
- Moved product-folder creation into the per-product worker thread and delayed terminal callbacks until the QThread is finished and controller ownership is cleared.
- Correlated download callbacks by request ID, product identity, authoritative image list, and product folder before they can update or finalize a queue item.
- Centralized transient/permanent/user-action/cancelled/internal classification; product extraction now uses three attempts with non-blocking one/two-second backoff while image retry remains worker-owned.
- Added bounded HTTP 429 `Retry-After` handling and permanent permission/disk-full write failures without deleting completed images.
- Made marker-owned folders stable across title changes, kept unmarked/corrupt/mismatched folders untouched, and reused Task 007B to complete partial historical downloads.
- Made each completed managed download refresh one portable metadata file from authoritative images and final current-run download results without changing marker ownership.

### Fixed
- Restored manual Chrome Extension full-gallery traversal by waiting for ordered carousel media identities to advance, excluding video media, and refusing to promote a visible-only four-image window to `COMPLETE`.
- Prevented duplicate dispatch/advance, stale callbacks completing the next product, cancellation being counted as failure, pending items remaining non-terminal after cancellation, and application close destroying an active QThread.
- Prevented late results/errors from earlier product attempts, retry timers firing after cancellation/close, and product-level retry multiplying Task 007B image retries.
- Prevented different URLs for one successful product from creating/downloading twice, without treating failed products or Task 011 retry attempts as duplicates.

### Removed
- Removed the unused Python browser-session, authentication, URL-resolver, metadata-extractor, and associated worker implementations.
- Removed legacy browser-automation tests and stale architecture specifications.
- Removed direct-extension WebSocket remnants, duplicate batch protocol aliases, popup extraction fallback, and obsolete message listeners.

## [0.1.0] - 2026-08-30

### Added
- Initial project structure using standard Python `src/` layout.
- `pyproject.toml` configuration targeting Python 3.12+ and PySide6.
- Git repository setup with Python/Qt `.gitignore`.
- Project documentation suite: `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `TASKS.md`, `TESTING.md`, and specification `001-project-bootstrap.md`.
- Architecture Decision Record `0001-record-architecture-decisions.md`.
- Core PySide6 application bootstrapping with minimal `MainWindow` titled "Shopee Image Downloader".
- Basic test suite using `pytest`.
- Main GUI layout with multiline input, folder selector, progress bar, and results table (Task 002).
- URL input parser and Shopee Vietnam domain validator (Task 003).
- Native output folder selector and persistent settings manager (Task 004).
- Shopee URL resolver engine (`ShopeeUrlResolver`), tracking parameter sanitizer, `shop_id`/`item_id` extractor, and asynchronous `UrlResolverWorker` (`QThread`) with table status transitions (Task 005).
