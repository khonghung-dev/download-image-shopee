# Architecture Overview: Shopee Image Downloader

## Design Goals

- **Separation of Concerns**: Clean isolation between UI presentation, background tasks, network data extraction, and disk storage.
- **Robust Asynchrony**: Offload all I/O and CPU-bound work to background workers (`QThread` / `QThreadPool`) to guarantee the GUI never freezes.
- **Testability**: Independent core modules capable of being tested using unit tests without launching a GUI loop.
- **Maintainability & Extensibility**: Modular design allowing support for new Shopee domains or alternative e-commerce platforms in the future.

## Layered Architecture

```mermaid
graph TD
    subgraph UI ["UI Layer (PySide6)"]
        MW[MainWindow]
        URLInput[URL List Input]
        DirPicker[Directory Picker]
        ProgressBar[Progress & Status Bar]
        LogView[Activity Log Viewer]
    end

    subgraph Service ["Worker & Concurrency Layer"]
        Worker[BatchDownloadWorker (QThread/QRunnable)]
        Signals[Qt Signals (progress, log, finished)]
    end

    subgraph Core ["Core Business Logic"]
        Parser[ShopeeUrlParser]
        Extractor[ShopeeImageExtractor]
        Sanitizer[PathSanitizer]
    end

    subgraph Storage ["Storage & Network Layer"]
        Downloader[ImageDownloader (HTTP Client)]
        FileManager[LocalFileManager]
    end

    subgraph ExtBridge ["Extension & Desktop Native Messaging Bridge"]
        ChromeExt[Shopee Chrome Extension (MV3)]
        ExtBG[Background SW (connectNative)]
        NativeHost[Native Host EXE (shopee_native_host.exe)]
        BridgeServer[ExtensionBridgeServer (ws://127.0.0.1:8765)]
        Proto[Bridge Protocol Validator]
    end

    ChromeExt --> ExtBG
    ExtBG <-->|Chrome Native Messaging (stdio)| NativeHost
    NativeHost <-->|Local WebSocket 127.0.0.1:8765| BridgeServer
    BridgeServer --> Proto
    BridgeServer --> Signals
    Signals --> MW
    MW --> Worker
    Worker --> Signals
    Signals --> MW
    Worker --> Parser
    Worker --> Extractor
    Worker --> Sanitizer
    Worker --> Downloader
    Downloader --> FileManager
```

## Component Descriptions

1. **UI Layer (`src/shopee_image_downloader/ui/`)**:
   - `MainWindow`: Main Qt container hosting the input fields, folder selector, execution controls, progress views, and extension bridge status indicator.
   - Responsible strictly for rendering, capturing user input, and forwarding user actions to worker triggers.

2. **Extension Bridge Layer (`native_host/`, `src/shopee_image_downloader/workers/bridge_worker.py` & `core/bridge_protocol.py`)**:
   - `chrome_extension/`: Manifest V3 Chrome Extension operating in normal browser sessions, extracting main product image galleries via `ShopeeExtractorCore` and communicating via Chrome Native Messaging (`com.shopee_image_downloader.bridge`).
   - `native_host/`: Standalone native host executable (`shopee_native_host.exe`) implementing standard stdio framing, converting Native Messaging frames to localhost WebSocket connections to isolate Chrome from desktop offline states.
   - `ExtensionBridgeServer`: Qt-integrated event-driven WebSocket server binding strictly to `127.0.0.1:8765`.
   - Manages connection lifecycle (`hello` -> `hello_ack`), bidirectional message routing (`open_product`, `process_url`, `process_progress`, `product_result`, `process_error`, `cancel_processing`), and emits Qt signals.
   - `bridge_protocol.py`: Enforces versioned JSON schemas, message size limits, and sanitization for incoming and outgoing extension messages.

3. **Batch Queue & Worker Layer (`src/shopee_image_downloader/core/batch_queue.py` & `workers/`)**:
   - `BatchQueueManager`: Desktop-side orchestrator managing sequential FIFO item processing, per-item timeouts, `request_id` correlation, verification pause/resume, and cancellation. Sends `open_product` commands for one URL at a time.
   - `chrome_extension/background.js`: Manages dedicated worker tab lifecycle, navigates to target URLs, enforces bounded timeouts (`PRODUCT_TIMEOUT_MS = 35000`), receives `AUTHORITATIVE_PRODUCT_COMPLETE` events from the content script, and dispatches product results via a single canonical builder/sender `sendCompleteProductToDesktop()`.
   - `AuthLoginWorker`: Handles headed manual login in a background `QThread` without freezing the Qt main loop.
   - `MetadataExtractorWorker`: Legacy worker for standalone extraction (kept for rollback).
   - `UrlResolverWorker`: Resolves shortened and canonical URLs.
   - Emits granular Qt signals (`item_started`, `item_progress`, `item_completed`, `item_failed`, `verification_required`, `progress_updated`, `batch_finished`).

4. **Core Extraction Layer (`src/shopee_image_downloader/core/`)**:
   - URL parsing and validation (`ShopeeUrlParser`, `url_validator.py`, `url_resolver.py`).
   - Batch queue state machine (`batch_queue.py`).
   - Metadata extraction (`metadata_extractor.py`).
   - Path sanitization to guarantee Windows filesystem safety (stripping illegal characters `: * ? " < > | / \`).

5. **Storage & Download Layer (`src/shopee_image_downloader/storage/` & `services/`)**:
   - Manages directory creation and file stream writing.
   - Settings persistence with JSON storage (`settings.py`).
   - Implements download retries and timeouts.

