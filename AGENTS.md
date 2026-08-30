# Agent Guidelines - Shopee Image Downloader

This repository contains the codebase and documentation for **Shopee Image Downloader**, a Windows desktop application built with Python 3.12+ and PySide6 (Qt).

## Architectural Principles

1. **Layer Separation**:
   - **UI Layer (`src/shopee_image_downloader/ui/`)**: Pure PySide6 UI widgets, layouts, signals/slots, dialogs, styling. No blocking network or disk I/O in the main Qt thread.
   - **Worker / Concurrency Layer (`src/shopee_image_downloader/workers/` or `services/`)**: Qt `QThread` / `QRunnable` / `QThreadPool` or asynchronous workers that emit signals (`progress`, `item_completed`, `item_failed`, `finished`) back to the UI.
   - **Business Logic / Extraction Layer (`src/shopee_image_downloader/core/` / `extractor/`)**: URL parsing, Shopee API/HTML data extraction, sanitization, image resolution, and download logic. Must be decoupled from Qt UI components to allow standalone unit testing.
   - **Storage / File System Layer (`src/shopee_image_downloader/storage/`)**: Folder creation, path sanitization (Windows-safe filenames), and atomic file writing.

2. **Fault Tolerance & Resilience**:
   - Batch operations must process all input links resiliently.
   - An individual invalid or failed URL must never crash or interrupt the entire batch.
   - Log errors clearly with actionable diagnostics.

3. **Concurrency and UI Responsiveness**:
   - All network extraction and image downloading operations MUST run on worker threads.
   - The Qt GUI thread must never be blocked by synchronous sleep or network requests.

4. **Testing Standards**:
   - Keep business logic easily mockable and testable without requiring a live GUI display.
   - For UI tests involving Qt widgets, use `pytest-qt` or offscreen rendering (`QT_QPA_PLATFORM=offscreen`).

## Coding Standards

- **Python Version**: Python 3.12+.
- **Type Hints**: Use strict Python type annotations across public functions and methods.
- **Code Style**: Follow PEP 8 conventions.
- **Documentation**: Keep `docs/TASKS.md` updated as tasks progress, and update `CHANGELOG.md` for major milestone increments.
