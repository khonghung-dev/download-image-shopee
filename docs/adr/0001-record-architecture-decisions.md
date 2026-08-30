# ADR 0001: Technology Stack & Project Structure

## Status
Accepted

## Context
We are starting a new desktop application for Windows, "Shopee Image Downloader", aimed at providing a high-performance, robust, and clean desktop utility for batch-downloading images from Shopee product links.

## Decisions

1. **Python 3.12+ as Base Runtime**:
   - Offers modern typing features, improved runtime performance, enhanced error tracebacks, and broad library support.

2. **PySide6 (Qt for Python) for the Desktop GUI**:
   - Provides native look-and-feel on Windows.
   - Robust event loop, signaling system (`Signal` / `Slot`), and built-in thread management (`QThread`, `QThreadPool`) to guarantee a non-blocking, responsive GUI during intensive batch operations.

3. **Modern `src/` Layout**:
   - Ensures clean packaging boundaries and prevents accidental testing against in-tree source code instead of installed packages.
   - Standardized via `pyproject.toml` using `setuptools`.

4. **Pytest for Test Automation**:
   - Standard, lightweight test runner supporting fixtures and headless Qt testing.

## Consequences

- Requires PySide6 dependencies installed in the virtual environment.
- Developers must use `pip install -e .` or set `PYTHONPATH=src` during development.
