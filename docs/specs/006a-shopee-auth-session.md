# Task 006A Specification: Shopee Authentication & Persistent Session

## Objective

Establish a dedicated, application-owned Shopee authentication and persistent session management layer that runs prior to any product processing or metadata extraction.

Provide a clear Shopee Account UI section in the desktop application displaying the session status, allowing the user to initiate an interactive manual login in a normal installed Google Chrome external process using `%LOCALAPPDATA%\ShopeeImageDownloader\ChromeUserData` with a remote debugging port, keeping Chrome open under full user control during verification / CAPTCHA challenges without automated interference or auto-close, providing an explicit `"Hoàn tất đăng nhập"` button for the user to confirm session finalization, providing a safe logout capability that clears the application's profile, and enforcing an authentication guard on the "Bắt đầu tải ảnh" button so that batch processing cannot proceed without an active Shopee session.

---

## Requirements & Scope

### In Scope

1. **Shopee Account UI Section**:
   - Status indicators:
     - `Chưa đăng nhập` (Default / Not logged in)
     - `Đang mở Chrome...` (Browser process launching)
     - `Đang chờ người dùng đăng nhập...` (Manual login in progress)
     - `Shopee đang yêu cầu xác minh` (Human verification prompt)
     - `Đang kiểm tra phiên Shopee...` (Startup verification)
     - `<Shopee username>` / `Đã đăng nhập` (Active authenticated session)
     - `Phiên không hợp lệ` (Session expired / invalid)
   - Action controls:
     - `Đăng nhập Shopee` button: Launches dedicated Google Chrome process.
     - `Hoàn tất đăng nhập` button: Explicit user-driven session validation and finalization.
     - `Đăng xuất` button: Clears application's Shopee session.

2. **Dedicated Application-Owned Persistent Profile**:
   - Stored strictly in `%LOCALAPPDATA%\ShopeeImageDownloader\ChromeUserData` (on Windows) or `~/.shopeeimagedownloader/ChromeUserData` (on Linux/macOS).
   - Strictly kept outside the Git repository.
   - Strictly isolated from personal browsers (Google Chrome User Data, Profile 10, Microsoft Edge, Cốc Cốc).

3. **Strict Filesystem Safety Guards**:
   - Only permitted persistent writable roots:
     - Repository root (`D:\download-picture-shopee`)
     - Application data root (`%LOCALAPPDATA%\ShopeeImageDownloader`)
     - Temporary testing directories (`tempfile.gettempdir()`)
   - Rejects operations on root system drives (`C:\`, `D:\`), system directories (`C:\Windows`, `C:\Program Files`), or user personal Chrome directories (`Google\Chrome\User Data`, `Profile 10`).

4. **Normal External Google Chrome Process**:
   - Uses installed real Google Chrome (`C:\Program Files\Google\Chrome\Application\chrome.exe` or candidate paths).
   - Does NOT use Playwright's `launch_persistent_context()` as the primary login-browser launcher to prevent automated fingerprint detection during manual login.
   - Spawns Chrome with `--user-data-dir=%LOCALAPPDATA%\ShopeeImageDownloader\ChromeUserData` and `--remote-debugging-port=9222`.
   - No custom anti-detection flags (`--disable-blink-features=AutomationControlled`), stealth plugins, or fingerprint spoofing.

5. **Manual User Authentication Flow**:
   - Triggered by clicking `Đăng nhập Shopee`.
   - Opens the dedicated Google Chrome process at `https://shopee.vn/buyer/login`.
   - The user manually performs login (username/password, QR code scan, OTP, CAPTCHA).
   - The application does NOT automate credentials, OTPs, or CAPTCHA solving.
   - Genuine user authentication cookies (`SPC_EC`, `shopee_token`, or numeric `SPC_U`) are strictly required for positive authentication confirmation; anonymous guest cookies (`SPC_T_ID`, `SPC_T_IV`, `SPC_R_T_ID`, `SPC_F`, `SPC_SI`) are explicitly excluded.
   - Real-time DOM username detection immediately reflects username in the desktop app.

6. **Critical Verification Retention Rule**:
   - If Shopee displays `/verify/captcha`, `/verify/traffic/error`, "Vui lòng thử lại sau", or "Chưa thể hoàn tất xác thực lúc này":
     - The application **NEVER automatically closes Chrome**.
     - The application **NEVER continuously refreshes** or relaunches Chrome.
     - Displays: `"Shopee đang yêu cầu xác minh. Trình duyệt sẽ được giữ mở."`
     - Browser remains completely open and available for user manual action.

7. **Explicit Finalization Flow ("Hoàn tất đăng nhập")**:
   - User confirms session stability and clicks `"Hoàn tất đăng nhập"`.
   - Application connects via CDP or checks persistent cookies to validate authentication.
   - If valid: persists `auth_state.json`, cleanly terminates only the tool's own Chrome child process, and displays the username.
   - If invalid: keeps Chrome open, does not destroy the profile, displays the reason, and allows the user to continue.

8. **Startup Session Verification & Persistence**:
   - On application startup, displays `"Đang kiểm tra phiên Shopee..."` and validates whether genuine authentication cookies exist.
   - A saved username alone is NEVER treated as proof that the session is valid; actual cookie status is checked.
   - If valid, restores `<Shopee username>` without re-login.
   - If invalid/expired, displays `Chưa đăng nhập` or `Phiên không hợp lệ`.

9. **Safe Logout Flow**:
   - Triggered by clicking `Đăng xuất`.
   - Validates canonical path safety before removing profile files.
   - Safely clears cookies and storage files in `%LOCALAPPDATA%\ShopeeImageDownloader\ChromeUserData`.
   - Resets the UI status to `Chưa đăng nhập`.
   - Does not affect personal browser profiles or existing Chrome windows.

10. **Start Button Guard**:
    - When the user clicks `Bắt đầu tải ảnh`:
      1. Validates output folder selection.
      2. Verifies that the Shopee session status is `Đã đăng nhập`. If not authenticated, halts immediately and displays:
         `"Vui lòng đăng nhập Shopee trước."`
      3. Only proceeds to URL validation and metadata extraction if both output folder and Shopee authentication are valid.

---

## Architecture & Component Design

```
┌─────────────────────────────────────────────────────────────┐
│                    MainWindow (PySide6)                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Shopee Account Section:                               │  │
│  │ [Trạng thái: chuasudung4526]                          │  │
│  │ [ Button: Đăng nhập Shopee ]                          │  │
│  │ [ Button: Hoàn tất đăng nhập ] [ Button: Đăng xuất ]  │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Link Input | Folder Selector | [ Bắt đầu tải ảnh ]    │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
       [AuthLoginWorker]             [ShopeeSessionManager]
     (Background QThread)            (Core / External Chrome)
                │                             │
                ▼                             ▼
     External Chrome Process         AppData Dedicated Profile
     (Manual user login & OTP)       (%LOCALAPPDATA%\...\ChromeUserData)
```

---

## Acceptance Criteria

1. Dedicated Shopee Account section exists in `MainWindow` with status label, `Đăng nhập Shopee`, `Hoàn tất đăng nhập`, and `Đăng xuất` buttons.
2. Clicking `Đăng nhập Shopee` launches installed Google Chrome as a normal external process with dedicated `ChromeUserData` profile and remote debugging port.
3. Personal user Chrome profiles (e.g. `Profile 10`, `Google\Chrome\User Data`) and system drives are strictly rejected and protected by canonical path safety guards.
4. If verification or rate blocks occur, Chrome is NEVER auto-closed or refreshed in loops; the status reflects `"Shopee đang yêu cầu xác minh"`.
5. Clicking `"Hoàn tất đăng nhập"` validates genuine auth cookies, persists state, and cleanly closes only the application's Chrome child process.
6. Reopening the application with a valid session restores `<Shopee username>` automatically upon actual cookie verification.
7. Clicking `Đăng xuất` clears the saved application session and changes the status to `Chưa đăng nhập`.
8. Clicking `Bắt đầu tải ảnh` without an active session halts and shows `"Vui lòng đăng nhập Shopee trước."`.
9. All unit and UI tests pass offline and with mock fixtures.
