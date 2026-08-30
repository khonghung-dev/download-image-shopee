# Testing Strategy: Shopee Image Downloader

This document outlines the testing guidelines, test categories, and verification commands for the project.

## Test Categories

1. **Unit Tests (`tests/`)**:
   - Validate standalone business logic, URL parsers, metadata extractors, path sanitization, filesystem safety guards, and session data structures.
   - Run completely offline without real HTTP requests or GUI windows.

2. **Authentication & Session Tests (`tests/test_auth_session.py`)**:
   - Validate installed Google Chrome selection (`channel="chrome"` and path discovery).
   - Validate dedicated application-owned profile directory (`%LOCALAPPDATA%\ShopeeImageDownloader\ChromeUserData`).
   - Validate path safety guards rejecting personal Chrome User Data, Profile 10, and system roots.
   - Validate authentication cookie extraction, startup session verification, grace periods, verification challenges, timeout handling, and safe logout.

3. **UI & Window Initialization Tests (`tests/test_ui.py`)**:
   - Verify that Qt widgets, window title, Shopee Account section, URL inputs, table rows, and signal bindings initialize without uncaught exceptions.
   - Run in offscreen mode (`QT_QPA_PLATFORM=offscreen`) so they execute seamlessly in headless environments and CI/CD pipelines.

4. **Integration / Mock Network Tests**:
   - Test downloader and worker pipelines using mock HTTP responses and sample Shopee HTML/JSON payloads.

## Running Tests

### Standard Test Execution

```powershell
.\.venv\Scripts\python.exe -m pytest
```

### Run with Verbose Output

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

### Headless / Offscreen Execution (for CI or automated runs)

```powershell
$env:QT_QPA_PLATFORM="offscreen"; .\.venv\Scripts\python.exe -m pytest -v
```

## Guidelines for Writing Tests

- Never make live network calls inside unit tests.
- Isolate file system tests using `tmp_path` pytest fixture.
- NEVER point tests to personal Chrome User Data or Profile 10.
- Keep tests fast, independent, and idempotent.
