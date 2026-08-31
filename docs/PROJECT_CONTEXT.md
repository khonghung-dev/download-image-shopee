# Project Context

Shopee Image Downloader currently coordinates product extraction between a PySide6 desktop application and a Chrome extension.

## Implemented

- Multiline Shopee URL parsing, validation, and exact-input deduplication.
- Persistent output-folder selection and validation.
- Sequential, resilient batch orchestration with one request in flight.
- Verification pause/resume, timeout handling, cancellation, and per-item failure continuation.
- Chrome worker-tab orchestration through Native Messaging.
- Product name, shop/item identity, and gallery URL extraction through `chrome_extension/extractor_core.js`.
- Manual extension extraction and manual send to the desktop.
- Desktop result-table correlation and product-key deduplication.

## Not implemented

- Downloading image bytes.
- Creating per-product output folders.
- Atomic image-file writes, naming, or retry policy.

The selected output folder is therefore a validated, persisted prerequisite for the planned download stage; current processing stops after receiving extraction results.

## Frozen known regression

The automatic flow returns four images for the known regression case while manual extension extraction can return nine. Architecture cleanup deliberately preserves that behavior for a separate debugging task.
