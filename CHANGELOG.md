# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

