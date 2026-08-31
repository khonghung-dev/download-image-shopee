# Shopee Image Downloader

Shopee Image Downloader is a Windows PySide6 desktop application paired with a Manifest V3 Chrome extension. The desktop accepts multiple Shopee URLs and runs them sequentially through the extension in the user's normal Chrome session.

The current milestone extracts product metadata and gallery URLs into the desktop results table. Despite the existing button label, image-file downloading and per-product folder writing are not implemented yet.

## Active architecture

```text
PySide6 desktop
  ↕ localhost WebSocket (127.0.0.1:8765)
Native Messaging Host
  ↕ Chrome Native Messaging
Extension service worker
  ↕ Chrome tab messaging
Shopee content script
  → extractor_core.js
```

The extension never opens a direct WebSocket. The WebSocket is deliberately retained between the Native Host and the PySide6 desktop.

## Requirements

- Windows 10/11
- Python 3.12+
- Google Chrome
- Node.js only for the JavaScript regression tests

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Run the desktop with either:

```powershell
shopee-image-downloader
```

```powershell
python -m shopee_image_downloader.main
```

See [chrome_extension/README.md](chrome_extension/README.md) for loading the extension and [native_host/README.md](native_host/README.md) for building or installing the Native Messaging Host.

## Runtime entry points

- Desktop: `shopee_image_downloader.main:main`
- Desktop WebSocket bridge: `src/shopee_image_downloader/workers/bridge_worker.py`
- Extension service worker: `chrome_extension/background.js`
- Content script: `chrome_extension/content.js`
- Canonical extraction engine: `chrome_extension/extractor_core.js`
- Native Host: `native_host/host.py` or `native_host/dist/shopee_native_host.exe`

Architecture and protocol details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The cleanup audit is in [docs/CLEANUP_REPORT.md](docs/CLEANUP_REPORT.md).

## Known regression

For the known regression case, automatic batch processing currently returns four images while manual extension extraction can return nine. This behavior is intentionally preserved for the next debugging task.

## License

MIT.
