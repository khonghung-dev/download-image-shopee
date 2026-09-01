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
- [x] Task 011: canonical `AppError` taxonomy and one error-code classification policy for extraction, protocol, folder, download, cancellation, and internal failures.
- [x] Task 011: three-attempt product opening/extraction retry with non-blocking one/two-second backoff on the same queue item and row.
- [x] Task 011: per-attempt request generation rejects stale results/errors; verification pause/resume consumes no automatic retry attempt.
- [x] Task 011: downloader 429 bounded `Retry-After`, bounded 5xx retries, permanent 4xx handling, and no product-level double retry after image failures.
- [x] Task 011: permanent output/permission/disk-full handling, controlled unexpected worker failure, and cancellation/close-safe retry timers.
- [x] Task 011: transient/permanent/verification/stale/HTTP/storage/cancellation/multi-product/nine-image regressions.
- [x] Task 012: canonical `shop_id:item_id` identity shared by the desktop product model, queue, and Product Folder Manager.
- [x] Task 012: atomic `.shopee-product-id` ownership marker, immediate-child cross-run discovery, changed-title reuse, and conservative symlink/reparse containment.
- [x] Task 012: safe legacy/corrupt/mismatched marker collisions, same-title/different-product separation, and permanent multiple-claim failure.
- [x] Task 012: batch-local successful-product registry with terminal `SKIPPED_DUPLICATE`, stable input accounting, and no duplicate download.
- [x] Task 012: failed/partial results remain retryable by later items; Task 011 transport retries are not duplicates.
- [x] Task 012: marker-owned complete/partial folders reuse the existing Task 007B downloader and preserve authoritative image lists.
- [x] Task 013: canonical schema-versioned `product.json` builder/writer using authoritative product and final downloader results.
- [x] Task 013: readable UTF-8 JSON, portable exact local filenames, ordered per-image statuses, current-run download summary, and atomic replacement.
- [x] Task 013: automatic and manual managed lifecycles write metadata after downloads; metadata failures use the Task 011 `METADATA` stage without deleting images.
- [x] Task 013: cross-run metadata refresh, marker independence, same-batch duplicate no-rewrite, partial/skipped-existing, and nine-image regressions.
- [x] Task 014: production-ready visual hierarchy for URL input, output folder, primary/secondary actions, batch progress, product results, and final summary.
- [x] Task 014: separate Start/Cancel/verification Continue controls with active-batch input locking, single-shot cancellation, and reusable second-batch state.
- [x] Task 014: canonical Vietnamese `ItemState` presentation mapping, restrained centralized status tones, normalized error display, and handled duplicate styling.
- [x] Task 014: terminal-item overall progress, current-product/image/metadata progress, partial download counts, parser-based valid-link count, and model-derived final summaries.
- [x] Task 014: long product/path handling, retry row stability, cancellation/verification UX, partial/duplicate/nine-image regressions, and Windows resize/DPI-safe layouts.
- [x] Task 015: offline 100-product all-success and deterministic mixed stress, three repeated window batches, stale/duplicate callback floods, staged cancellation, cancel-to-new-batch, bridge reconnect, verification, accounting, and single-active-product regressions.
- [x] Task 015: worker/retry cleanup, cooperative close, high-frequency progress responsiveness, network/error matrix, atomic image/metadata cleanup, marker conflict, partial/complete cross-run recovery, destination/isolation, and known nine-image regressions.
- [x] Task 015: reproduced and fixed the one release defect found—long Unicode product folders under a deep output root could exceed the Windows atomic-marker path budget after directory creation. Folder components now use UTF-16 path units and reserve room for controlled atomic files.
- [x] Task 015: final automated suite is 280 passed, 0 failed, 0 skipped in 57.19 seconds; the live 30-product/cancel/network/close soak checklist is prepared for developer execution.

## Frozen extraction regression

- [x] Known nine-image-plus-one-video product produces nine authoritative images in the automatic flow.
- [x] The manual extension send uses the same authoritative nine-image result path.

Tasks 007A/007B/012/013/014/015 do not modify the extension, Native Host, gallery traversal, video filtering, or authoritative cache. Task 013 is Python desktop metadata serialization and worker-lifecycle integration only; Task 014 is desktop presentation and existing-progress signal exposure only. Task 015 changes only desktop folder path hardening demonstrated by a Windows stress failure, plus tests and reliability documentation.

## Planned product work

- [ ] Package and verify the full desktop application distribution.

Task 007A's Product Folder Manager remains the sole owner of directory creation and now implements Task 012 marker ownership/reuse. Task 007B writes only controlled sequential image files inside that validated directory; it remains the sole existing-file/partial-download policy.

Task 010 does not change the Chrome Extension, Native Host, extraction protocol, gallery traversal, authoritative cache, Task 007B retry limits, or Task 012 duplicate-product policy.

Task 011 adds automatic retries only for transient product opening/extraction failures. It does not add a manual retry button, rerun completed failed batches, change duplicate-product semantics, modify the extension/native architecture, or retry a whole product after Task 007B returns partial image failures.

Task 012's `.shopee-product-id` remains the only persistent folder ownership marker. Task 013's `product.json` is portable product/output metadata and is never used to adopt an unmarked folder.

Task 013 does not add folder auto-renaming, stale-image deletion, content hashing, exports, a database/global index, a metadata migration framework, or packaging changes.

Task 014 does not add a theme system, localization framework, preferences, previews, notifications, packaging, or UI-owned business state. The queue/item enums and structured download results remain authoritative; table text is presentation only.

Task 015 adds no features and performs no packaging. Its evidence matrix is `docs/TASK_015_RELIABILITY_MATRIX.md`; its developer-run live checklist is `docs/TASK_015_MANUAL_SOAK.md`.
