# Shopee Product Extractor

This Manifest V3 extension is the browser-side extractor and orchestrator for Shopee Image Downloader.

## Responsibilities

- `extractor_core.js` is the only Shopee product/gallery extraction implementation.
- `content.js` owns page lifecycle and the `EXTRACT_PRODUCT_DATA` / `GET_COMPLETE_SNAPSHOT` RPC boundary.
- `background.js` owns Native Messaging, the automatic worker tab, request correlation, timeouts, and the sole `product_result` builder `sendCompleteProductToDesktop()`.
- `popup.js` displays content-script results and triggers connect, rescan, copy, and manual send actions.

The extension does not use a direct WebSocket. `chrome.runtime.connectNative()` connects it to `com.shopee_image_downloader.bridge`; the Native Host then relays to the desktop WebSocket on `127.0.0.1:8765`.

## Permissions

- `activeTab`: interact with the current tab after the user opens the popup.
- `tabs`: manage the dedicated automatic-processing worker tab.
- `nativeMessaging`: connect to the repository's Native Messaging Host.
- Host permissions are restricted to the configured Shopee domains.

The extension does not request cookies, history, debugger, or broad all-site access.

## Load unpacked

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose **Load unpacked**.
4. Select `D:\download-picture-shopee\chrome_extension`.

The checked-in Native Messaging manifests allow only extension ID `kjkgdknadhnpigglcpjbgkkbcngclhgf`. Follow [../native_host/README.md](../native_host/README.md) to install the host for that extension.

## Manual flow

1. Open a Shopee product in Chrome.
2. Open the extension popup; it asks `content.js` to extract via `extractor_core.js`.
3. Click **Kết nối Desktop** if needed.
4. Click **Gửi sang ứng dụng**. The background service worker fetches the current complete snapshot from `content.js` and sends it through the canonical result builder.

No popup-supplied product payload is authoritative, and the popup does not execute a separate extraction function.

## Automatic flow

The desktop sends one `open_product` command at a time. `background.js` creates or reuses one worker tab, waits for `AUTHORITATIVE_PRODUCT_COMPLETE` from `content.js`, then calls `sendCompleteProductToDesktop()` exactly once for the correlated request.

The known automatic four-image/manual nine-image regression is intentionally not fixed by the architecture cleanup.
