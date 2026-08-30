# Task 001 Specification: Project Bootstrap

## Objective

Initialize the project repository structure, build configuration, development documentation, and minimal PySide6 desktop application window for **Shopee Image Downloader**.

## Scope & Constraints

### In Scope
- Setup of a standard Python `src/` layout under `src/shopee_image_downloader/`.
- Project configuration using `pyproject.toml` with support for Python 3.12+ and PySide6.
- Comprehensive project documentation (`PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `TASKS.md`, `TESTING.md`, `AGENTS.md`, `README.md`, `CHANGELOG.md`, `adr/`).
- Minimal PySide6 application startup displaying a blank main window titled `"Shopee Image Downloader"`.
- Unit test setup in `tests/` to verify packaging and window initialization.
- Local Git repository initialization.

### Out of Scope (Explicitly Deferred)
- Shopee URL parsing and extraction.
- HTTP requests and downloading logic.
- File system download directories and file writing.
- Multithreading / concurrency workers.

## Acceptance Criteria

1. Python `src/` layout exists and is importable.
2. `pyproject.toml` defines valid metadata, dependencies, and entry point `shopee-image-downloader`.
3. Running the entrypoint launches a blank PySide6 window titled `"Shopee Image Downloader"` without errors.
4. `pytest` executes and passes all initial tests.
5. All specified documentation files are present.
6. Local Git repository is initialized.
