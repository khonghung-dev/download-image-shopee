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
- [x] Task 014/015B: Start, Cancel, and one state-aware Pause/Resume/verification-Continue control with active-batch input locking, single-shot cancellation, and reusable second-batch state.
- [x] Task 014: canonical Vietnamese `ItemState` presentation mapping, restrained centralized status tones, normalized error display, and handled duplicate styling.
- [x] Task 014: terminal-item overall progress, current-product/image/metadata progress, partial download counts, parser-based valid-link count, and model-derived final summaries.
- [x] Task 014: long product/path handling, retry row stability, cancellation/verification UX, partial/duplicate/nine-image regressions, and Windows resize/DPI-safe layouts.
- [x] Task 015: offline 100-product all-success and deterministic mixed stress, three repeated window batches, stale/duplicate callback floods, staged cancellation, cancel-to-new-batch, bridge reconnect, verification, accounting, and single-active-product regressions.
- [x] Task 015: worker/retry cleanup, cooperative close, high-frequency progress responsiveness, network/error matrix, atomic image/metadata cleanup, marker conflict, partial/complete cross-run recovery, destination/isolation, and known nine-image regressions.
- [x] Task 015: reproduced and fixed the one release defect found—long Unicode product folders under a deep output root could exceed the Windows atomic-marker path budget after directory creation. Folder components now use UTF-16 path units and reserve room for controlled atomic files.
- [x] Task 015: final automated suite is 280 passed, 0 failed, 0 skipped in 57.19 seconds; the live 30-product/cancel/network/close soak checklist is prepared for developer execution.
- [x] Task 015B: reduced the aligned desktop/extension extraction attempt timeout from 35,000 ms to 9,000 ms, preserving three attempts and non-blocking one/two-second retry backoff for an exact 30-second modeled maximum.
- [x] Task 015B: cooperative user pause/resume across extraction, retry, image download, and between-product boundaries; cancellation remains available, and verification resumes with a fresh transport generation while preserving the logical attempt.
- [x] Task 015B: independent optional `product.json` and `.shopee-product-id` exports, both off by default, with no deletion when off and a safe atomic app-local registry for marker-free cross-run folder identity.
- [x] Task 015B: model-backed spreadsheet-style URL grid, draggable vertical input/results split, separate right-side progress percentage, and coordinated neon dark desktop/extension presentation.
- [x] Task 015B: bounded four-way image concurrency inside one product while products remain strictly sequential; authoritative index/filename/result order, pause drain, cancellation cleanup, and per-image fault isolation are preserved.
- [x] Task 015B: no headless/zero-tab rewrite, no extractor/content/popup-controller/native-host/manifest behavior change, no new automation dependencies, and no executable build.
- [x] Task 015B: untouched baseline 280 passed, 0 failed, 0 skipped in 49.39 seconds; final offline suite 307 passed, 0 failed, 0 skipped in 32.59 seconds. Live acceptance remains manual.
- [x] Task 015C: replace the monolithic hard-coded desktop stylesheet with one semantic `DARK`/`LIGHT` theme module, transparent normal labels, complete widget/table/scrollbar states, and theme-aware status tones.
- [x] Task 015C: add a compact live header toggle and persist only `appearance/theme` through `QSettings`, defaulting invalid/missing values to `DARK` without changing active batch state or UI data.
- [x] Task 015C: no extension, extractor-core, content extraction, popup, Native Host, downloader, retry, folder-identity, metadata-schema, URL-editor behavior, or executable-build change. Live Chrome/Shopee acceptance remains manual.
- [x] Task 015C: untouched baseline 307 passed, 0 failed, 0 skipped in 24.96 seconds; final clean offline suite 312 passed, 0 failed, 0 skipped in 38.49 seconds.
- [x] Task 016A: add one public MV3 manifest key and derive stable Extension ID `bhbnfalghoklngoohdpnjedcdcplbjhm` independently of the unpacked folder path.
- [x] Task 016A: derive/validate the one exact Native Messaging origin, remove the historical runtime ID, and fail tests/builds on key/allowlist drift without bundling a private key.
- [x] Task 016: build the Desktop as PyInstaller ONEDIR plus a fresh Native Host EXE; assemble self-locating current-user install/uninstall scripts, keyed Extension source, Vietnamese README, security/portability audits, and `ShopeeImageDownloader-Windows.zip`.
- [x] Task 016A/016 automated gates: untouched baseline 311 passed; final source suite 316 passed, 0 failed, 0 skipped; packaged Desktop launch and packaged Native Host handshake pass; exact HKCU registration passes.

## Frozen extraction regression

- [x] Known nine-image-plus-one-video product produces nine authoritative images in the automatic flow.
- [x] The manual extension send uses the same authoritative nine-image result path.

Tasks 007A/007B/012/013/014/015 do not modify the extension, Native Host, gallery traversal, video filtering, or authoritative cache. Task 013 is Python desktop metadata serialization and worker-lifecycle integration only; Task 014 is desktop presentation and existing-progress signal exposure only. Task 015 changes only desktop folder path hardening demonstrated by a Windows stress failure, plus tests and reliability documentation. Task 015B changes `background.js` only for the aligned timeout and verification timer/state handling, and changes `popup.html` only for presentation; `extractor_core.js`, `content.js`, `popup.js`, `manifest.json`, and the Native Host remain frozen. Task 015C changes only desktop presentation and theme persistence.

## Planned product work

- [ ] TASK 017 — Final Windows Installer: canonical Inno Setup 6 source, final Setup artifact, static gates, and automated default/custom install-uninstall-reinstall matrix are complete; live installed-version Chrome/9-9-9 acceptance remains for the user.

Task 007A's Product Folder Manager remains the sole owner of directory creation and now implements Task 012 marker ownership/reuse. Task 007B writes only controlled sequential image files inside that validated directory; it remains the sole existing-file/partial-download policy.

Task 010 does not change the Chrome Extension, Native Host, extraction protocol, gallery traversal, authoritative cache, Task 007B retry limits, or Task 012 duplicate-product policy.

Task 011 adds automatic retries only for transient product opening/extraction failures. It does not add a manual retry button, rerun completed failed batches, change duplicate-product semantics, modify the extension/native architecture, or retry a whole product after Task 007B returns partial image failures.

Task 015B makes Task 012's `.shopee-product-id` optional and adds a small app-local registry as the marker-free ownership mechanism. Exact marker evidence remains authoritative. Task 013's `product.json` is optional portable product/output metadata and is never used to adopt an unmarked folder.

Task 013/015B does not add folder auto-renaming, stale-image deletion, content hashing, a content catalog, metadata migration framework, or packaging changes. The Task 015B registry stores only normalized output-root/product-key-to-relative-folder mappings.

Task 014 did not add a theme system. Task 015C adds only the presentation-owned dark/light theme preference; it does not add localization, previews, notifications, packaging, or UI-owned business state. The queue/item enums and structured download results remain authoritative; table text is presentation only.

Task 015 adds no features and performs no packaging. Its evidence matrix is `docs/TASK_015_RELIABILITY_MATRIX.md`; its developer-run live checklist is `docs/TASK_015_MANUAL_SOAK.md`.

Task 015B's live nine-image flow, actual failing-product timing, and 30-product soak remain developer-run manual acceptance gates. Automated tests do not access Shopee or personal Chrome profiles.

Task 015C's live Light/Dark theme checks remain developer-run manual acceptance gates. Automated tests mock Qt state and never inspect personal browser data.

Task 016's final Chrome/Shopee acceptance remains manual: reload the unpacked keyed Extension once, verify the displayed ID, connect it to the registered release Native Host, and run the known 9-image, pause/resume, verification, failing-product continuation, duplicate/cross-run, and second-batch checks from the packaged Desktop.

Task 017 keeps the approved Task 016 ONEDIR payload as its installer source. It uses one fixed AppId, installs per user under `%LOCALAPPDATA%`, registers/unregisters only the current-user Native Host through the proven packaged scripts, and never silently installs the Extension. Inno Setup 6.7.3 compiled the final Setup, and automated default install, same-version upgrade, uninstall, custom-directory install, custom uninstall, and default reinstall checks passed. Chrome Extension reconnect and the installed 9/9/9/live-runtime matrix remain explicit manual acceptance because the installer does not access or alter the Chrome profile.
