# Tasks & Project Roadmap

This document tracks development milestones, specifications, and execution status for **Shopee Image Downloader**.

## Task Overview

| Task ID | Title | Status | Specification |
|---------|-------|--------|---------------|
| **001** | Project Bootstrap & PySide6 Baseline | [x] Complete | [001-project-bootstrap.md](file:///d:/download-picture-shopee/docs/specs/001-project-bootstrap.md) |
| **002** | Main GUI Layout & User Controls | [ ] Planned | - |
| **003** | Shopee URL Parsing & Metadata Extraction | [ ] Planned | - |
| **004** | File Storage & Path Sanitization | [ ] Planned | - |
| **005** | Image Download Engine & Fault-Tolerant Worker | [ ] Planned | - |
| **006** | Progress Feedback & Batch Reporting | [ ] Planned | - |
| **007** | Packaging & Windows Executable Distribution | [ ] Planned | - |

---

## Detailed Task Log

### Task 001: Project Bootstrap & PySide6 Baseline
- **Goal**: Establish the repository layout, documentation, build metadata, test runner, Git repository, and verify clean startup of a blank PySide6 main window.
- **Deliverables**:
  - [x] Python `src/` layout configuration in `pyproject.toml`.
  - [x] Documentation suite in `docs/` (`PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `TASKS.md`, `TESTING.md`, `specs/`, `adr/`).
  - [x] PySide6 `MainWindow` titled "Shopee Image Downloader".
  - [x] Initial automated test suite in `tests/`.
  - [x] Local Git initialization.
  - [x] Execution verification and error-free launch.
