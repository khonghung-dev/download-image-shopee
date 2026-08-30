# Shopee Image Downloader

A modern Windows desktop application designed to download product images from multiple Shopee product links easily, organized per product subfolder, while maintaining a fluid and responsive UI.

## Features (Roadmap)

- **Multi-link Input**: Paste multiple Shopee product URLs (one per line).
- **Custom Destination**: Select any root output directory for downloads.
- **Product Metadata & Image Extraction**: Automatically retrieves product title, item ID, and all associated product image assets.
- **Folder Organization**: Creates a distinct subfolder per product (named cleanly using product details).
- **Resilient Batch Processing**: Errors or failures on individual links are caught and logged without aborting the rest of the queue.
- **Responsive GUI**: Powered by PySide6 (Qt) with asynchronous worker threads ensuring no UI freezing.

## Current State (Task 001 - Bootstrap)

Task 001 initializes the foundational application architecture:
- Modern Python `src/` layout.
- PySide6 GUI entry point showing a clean initial window titled `"Shopee Image Downloader"`.
- Automated testing configuration with `pytest`.
- Comprehensive architectural and development documentation in `docs/`.

## Prerequisites

- **Python**: 3.12 or newer
- **Operating System**: Windows 10/11 (or compatible desktop environment)

## Quick Start

### 1. Create and Activate a Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install the Package

```powershell
pip install -e ".[dev]"
```

### 3. Run the Application

```powershell
shopee-image-downloader
```
or:
```powershell
python -m shopee_image_downloader.main
```

### 4. Run Tests

```powershell
pytest
```

## Project Structure

```text
download-picture-shopee/
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── pyproject.toml
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PROJECT_CONTEXT.md
│   ├── TASKS.md
│   ├── TESTING.md
│   ├── adr/
│   │   └── 0001-record-architecture-decisions.md
│   └── specs/
│       └── 001-project-bootstrap.md
├── src/
│   └── shopee_image_downloader/
│       ├── __init__.py
│       ├── app.py
│       ├── main.py
│       └── ui/
│           ├── __init__.py
│           └── main_window.py
└── tests/
    ├── __init__.py
    └── test_app.py
```

## License

MIT License.
