# Shopee Image Downloader

Shopee Image Downloader is a Windows PySide6 desktop application paired with a Manifest V3 Chrome extension. The desktop accepts multiple Shopee URLs and runs them sequentially through the extension in the user's normal Chrome session.

The current milestone extracts authoritative product metadata/gallery URLs, downloads product images into Windows-safe per-product folders, and supports optional portable product metadata and identity files.

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

The packaged Windows ONEDIR release does not require source Python, Node.js, the repository, or a virtual environment.

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

The public key in the MV3 manifest gives the unpacked Extension stable ID `bhbnfalghoklngoohdpnjedcdcplbjhm`. After loading it, verify that exact ID at `chrome://extensions` before registering the Native Host.

## Runtime entry points

- Desktop: `shopee_image_downloader.main:main`
- Desktop WebSocket bridge: `src/shopee_image_downloader/workers/bridge_worker.py`
- Extension service worker: `chrome_extension/background.js`
- Content script: `chrome_extension/content.js`
- Canonical extraction engine: `chrome_extension/extractor_core.js`
- Native Host: `native_host/host.py` or `native_host/dist/shopee_native_host.exe`

Architecture and protocol details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The cleanup audit is in [docs/CLEANUP_REPORT.md](docs/CLEANUP_REPORT.md).

## Release packaging

`packaging/ShopeeImageDownloader.spec` is the canonical Desktop ONEDIR definition. `packaging/build_windows_release.ps1` assembles the Desktop, a fresh Native Host, unchanged keyed Extension source, current-user registration scripts, and the Vietnamese first-run guide.

## License

MIT.
