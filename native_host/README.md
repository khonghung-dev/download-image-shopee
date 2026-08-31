# Chrome Native Messaging Host - Shopee Image Downloader

This directory contains the Chrome Native Messaging host for bridging the Shopee Chrome Extension to the PySide6 desktop application.

## Host Name
`com.shopee_image_downloader.bridge`

## Architecture
```
Chrome Extension
    ↕ Native Messaging (stdin/stdout binary framing)
Native Host (shopee_native_host.exe)
    ↕ Loopback WebSocket (127.0.0.1:8765)
PySide6 Desktop App (ExtensionBridgeServer)
```

## Directory Structure
- `host.py`: Native host implementation (message framing, validation, and relay).
- `ws_client.py`: Standard-library RFC 6455 loopback WebSocket client.
- `com.shopee_image_downloader.bridge.json.template`: Manifest template with allowed extension ID.
- `build_host.ps1`: Builds standalone `dist/shopee_native_host.exe` using PyInstaller and generates `com.shopee_image_downloader.bridge.json`.
- `install_host.ps1`: Registers the host manifest under `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.shopee_image_downloader.bridge`.
- `uninstall_host.ps1`: Removes the HKCU registry key.

## Building the Host Executable
Run the following PowerShell command in the project root:
```powershell
powershell -ExecutionPolicy Bypass -File .\native_host\build_host.ps1
```

## Installing the Native Host (Manual Step)
After building, register the native host in the current user's registry:
```powershell
powershell -ExecutionPolicy Bypass -File .\native_host\install_host.ps1
```

## Uninstalling the Native Host
To remove the registration:
```powershell
powershell -ExecutionPolicy Bypass -File .\native_host\uninstall_host.ps1
```

## Log Files
Logs are written to:
`%LOCALAPPDATA%\ShopeeImageDownloader\logs\native_host.log`
(No sensitive tokens, credentials, or cookies are ever logged).
