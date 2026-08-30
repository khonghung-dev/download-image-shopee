# Task 002 Specification: Main UI

## Objective

Design and implement the main PySide6 desktop interface for **Shopee Image Downloader** with all required input controls, file destination picker field, execution triggers, progress displays, and batch results table.

## Scope & Constraints

### In Scope
- PySide6 `MainWindow` structure with proper Qt layout managers (`QVBoxLayout`, `QHBoxLayout`, `QSplitter`, `QHeaderView`).
- Window title: `"Shopee Image Downloader"`.
- Large multiline URL text input with label `"Link sản phẩm Shopee"` and placeholder `"Dán mỗi link Shopee trên một dòng..."`.
- Output folder row with read-only text field and `"Chọn thư mục"` button.
- Action row with main execution button `"Bắt đầu tải ảnh"`.
- Progress bar and status indicator initialized with `"Sẵn sàng"`.
- Results table with 4 columns: `["STT", "Sản phẩm / Link", "Trạng thái", "Số ảnh"]`.
- Clean responsive layout that resizes properly on Windows desktop.
- Comprehensive UI component unit tests.

### Out of Scope (Explicitly Deferred to Subsequent Tasks)
- URL format validation or sanitization (Task 003).
- Shopee HTTP/API extraction and parsing (Task 003).
- Native folder selection dialog binding and folder validation (Task 004).
- Image download operations and file writing (Task 004/005).
- Background worker threading and asynchronous signal dispatching (Task 005).

## UI Specifications

1. **Window Title**: `Shopee Image Downloader`
2. **URL Input Section**:
   - Label: `Link sản phẩm Shopee`
   - Multiline input (`QPlainTextEdit`) taking primary vertical space
   - Placeholder: `Dán mỗi link Shopee trên một dòng...`
3. **Folder Destination Row**:
   - Read-only text box (`QLineEdit.isReadOnly() == True`)
   - Button: `Chọn thư mục`
4. **Execution & Progress**:
   - Primary action button: `Bắt đầu tải ảnh`
   - Progress bar (`QProgressBar`)
   - Status text label: `Sẵn sàng`
5. **Results Table (`QTableWidget`)**:
   - 4 Columns:
     1. `STT`
     2. `Sản phẩm / Link`
     3. `Trạng thái`
     4. `Số ảnh`
   - Automatic column stretching for product title/link column.

## Acceptance Criteria

1. Running the application presents the complete UI matching all requirements.
2. All labels, placeholders, buttons, and table headers strictly match the specified strings.
3. Resizing the window adjusts widgets smoothly without clipping or distortion.
4. UI widgets are cleanly exposed for future worker integration.
5. All automated unit tests in `tests/test_ui.py` pass without errors.
