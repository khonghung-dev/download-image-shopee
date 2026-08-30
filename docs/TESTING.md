# Testing Strategy: Shopee Image Downloader

This document outlines the testing guidelines, test categories, and verification commands for the project.

## Test Categories

1. **Unit Tests (`tests/`)**:
   - Validate standalone business logic, URL parsers, metadata extractors, path sanitization, and data structures.
   - Run completely offline without real HTTP requests or GUI windows.

2. **UI & Window Initialization Tests**:
   - Verify that Qt widgets, window title, default layouts, and signal bindings initialize without uncaught exceptions.
   - Run in offscreen mode (`QT_QPA_PLATFORM=offscreen`) so they execute seamlessly in headless environments and CI/CD pipelines.

3. **Integration / Mock Network Tests**:
   - Test downloader and worker pipelines using mock HTTP responses and sample Shopee HTML/JSON payloads.

## Running Tests

### Standard Test Execution

```powershell
pytest
```

### Run with Verbose Output

```powershell
pytest -v
```

### Headless / Offscreen Execution (for CI or automated runs)

```powershell
$env:QT_QPA_PLATFORM="offscreen"
pytest
```

## Guidelines for Writing Tests

- Never make live network calls inside unit tests.
- Isolate file system tests using `tmp_path` pytest fixture.
- Keep tests fast, independent, and idempotent.
