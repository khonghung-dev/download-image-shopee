# Task 004 Specification: Output Folder Selector & Persistence

## Objective

Implement the output folder selection mechanism using the native Windows folder picker dialog, persist the user's selected directory to local storage, restore it upon subsequent launches if the directory still exists, and validate that a valid directory is chosen before initiating URL batch processing.

## Requirements & Scope

### In Scope
1. **Folder Selection Dialog**:
   - Clicking the "Chọn thư mục" (`select_folder_button`) button triggers the native directory selection dialog (`QFileDialog.getExistingDirectory`).
   - The dialog initializes with the currently configured output directory or the user's home directory if unset.
   - Upon selecting a directory:
     - The absolute path is displayed in the read-only `output_folder_input` line edit.
     - The path is persisted locally via `SettingsManager`.
2. **Settings Persistence**:
   - Settings management logic is decoupled from UI widgets into `src/shopee_image_downloader/storage/settings.py`.
   - Settings are stored in a cross-platform, user-local JSON file (under user app data directory, e.g. `~/.shopee_image_downloader/settings.json` or `%LOCALAPPDATA%/ShopeeImageDownloader/settings.json`).
   - Supports dependency injection / custom file paths to allow isolated unit testing with pytest fixtures (`tmp_path`).
3. **Application Startup & Restoration**:
   - When `MainWindow` initializes, it loads the saved output directory from `SettingsManager`.
   - If the saved path exists on the filesystem and is a directory (`is_dir()`), `output_folder_input` is populated with the path.
   - If the path does not exist or is invalid, the field remains empty (displaying placeholder text).
4. **Validation on Action Trigger ("Bắt đầu tải ảnh")**:
   - When the user clicks "Bắt đầu tải ảnh" (`start_button`), check whether a valid output folder is selected:
     - If the field is empty or points to a non-existent folder, halt processing, do not populate or modify the results table, and display the status message:
       `Vui lòng chọn thư mục lưu ảnh.`
     - If a valid output folder is present, proceed with URL parsing and table population as implemented in Task 003.
5. **Separation of Concerns**:
   - UI layer (`MainWindow`) interacts with `SettingsManager` for loading and storing configurations.
   - No filesystem modification or network calls are triggered during this task.

### Out of Scope (Deferred to Future Tasks)
- Automatic subfolder creation for individual products (Task 005).
- Image file streaming and atomic writes (Task 005).
- Shopee metadata / image extraction (Task 005).

## Acceptance Criteria

1. Clicking "Chọn thư mục" opens the native folder dialog, and selecting a valid folder updates the UI text field and saves the setting.
2. Cancelling the folder dialog preserves the existing folder path.
3. Relaunching the application restores the previously selected folder if it exists.
4. If the saved folder was deleted or moved, relaunching leaves the folder field empty.
5. Clicking "Bắt đầu tải ảnh" without a valid output folder halts execution and displays `"Vui lòng chọn thư mục lưu ảnh."`.
6. Clicking "Bắt đầu tải ảnh" with a valid output folder executes URL validation as expected.
7. All unit and UI tests pass offline.
