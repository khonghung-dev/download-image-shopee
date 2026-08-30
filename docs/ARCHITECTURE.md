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
   - `MainWindow`: Main Qt container hosting the input fields, folder selector, execution controls, and progress views.
   - Responsible strictly for rendering, capturing user input, and forwarding user actions to worker triggers.

2. **Worker Layer (`src/shopee_image_downloader/workers/`)**:
   - Manages queue execution across threads.
   - Emits granular Qt signals (`on_item_started`, `on_item_progress`, `on_item_completed`, `on_item_error`, `on_queue_finished`).

3. **Core Extraction Layer (`src/shopee_image_downloader/core/`)**:
   - URL parsing and validation.
   - API / Web payload parsing to identify image hashes and full URLs.
   - Path sanitization to guarantee Windows filesystem safety (stripping illegal characters `: * ? " < > | / \`).

4. **Storage & Download Layer (`src/shopee_image_downloader/storage/` & `services/`)**:
   - Manages directory creation and file stream writing.
   - Implements download retries and timeouts.
