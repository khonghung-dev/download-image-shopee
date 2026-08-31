/**
 * Shopee Product Extractor - Background Service Worker
 * Manages Chrome Native Messaging bridge with the PySide6 desktop application.
 *
 * Task 006N & 006Z: Chrome Native Messaging Bridge & Unified Event-Driven Batch Queue
 *
 * Transport Flow:
 * Desktop App (BatchQueueManager / ExtensionBridgeServer)
 *   ↓ send "open_product"
 * Native Host EXE (com.shopee_image_downloader.bridge)
 *   ↓
 * Chrome Extension Background SW (background.js)
 *   ↓ navigate dedicated worker tab
 * Shopee Product Page (006X content.js + extractor_core.js)
 *   ↓ reaches authoritative COMPLETE
 * content.js emits AUTHORITATIVE_PRODUCT_COMPLETE event
 *   ↓
 * background.js calls canonical sendCompleteProductToDesktop() (SAME as "Gửi sang ứng dụng")
 *   ↓ Native Messaging stdio frame
 * Native Host EXE -> WebSocket -> PySide6 Desktop App
 *
 * Architectural Invariants:
 * 1. ZERO separate batch extractors: Reuses normal 006X content script lifecycle.
 * 2. ONE Dedicated Worker Tab: Reused across all URLs in the batch.
 * 3. ONE Canonical Sender: sendCompleteProductToDesktop() for both manual button & automatic batch.
 * 4. ONE Active Builder: Exactly 1 location building canonical product result payload.
 * 5. Auto-Send Exactly Once: Request state machine guards against duplicate dispatches.
 */

(function () {
  'use strict';

  const NATIVE_HOST_NAME = 'com.shopee_image_downloader.bridge';
  const EXPECTED_EXTENSION_ID = 'kjkgdknadhnpigglcpjbgkkbcngclhgf';
  const PROTOCOL_VERSION = 1;
  const PRODUCT_TIMEOUT_MS = 35000;

  const BridgeState = {
    DISCONNECTED: 'DISCONNECTED',
    CONNECTING: 'CONNECTING',
    CONNECTED: 'CONNECTED'
  };

  const RequestState = {
    IDLE: 'IDLE',
    OPENING: 'OPENING',
    WAITING_COMPLETE: 'WAITING_COMPLETE',
    SENT: 'SENT',
    FAILED: 'FAILED'
  };

  let currentState = BridgeState.DISCONNECTED;
  let nativePort = null;
  let lastErrorMessage = '';
  let wasConnectedBefore = false;
  let isHostInstalled = true;

  // Dedicated worker tab state
  let originalUserTabId = null;
  let originalUserWindowId = null;
  let dedicatedWorkerTabId = null;
  let isBatchRunning = false;

  // Active batch item request state
  let currentRequestId = null;
  let currentInputUrl = null;
  let currentExpectedProductKey = null;
  let currentWorkerTabId = null;
  let currentRequestState = RequestState.IDLE;
  let currentTimeoutTimer = null;
  let activeCancellationRequested = false;

  // Track closed tabs to reset worker tab ID or original tab ID
  if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.onRemoved) {
    chrome.tabs.onRemoved.addListener((tabId) => {
      if (tabId === dedicatedWorkerTabId) {
        console.log(`[BatchWorker] Dedicated worker tab was closed: tabId=${tabId}`);
        dedicatedWorkerTabId = null;
        currentWorkerTabId = null;
      }
      if (tabId === originalUserTabId) {
        originalUserTabId = null;
      }
    });
  }

  // Track tab updates on worker tab to detect verification or 404
  if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.onUpdated) {
    chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
      if (tabId !== dedicatedWorkerTabId) return;

      const updatedUrl = changeInfo.url || tab?.url || '';
      const updatedTitle = changeInfo.title || tab?.title || '';

      // Verification / CAPTCHA detection
      if (
        updatedUrl.includes('/verify/captcha') ||
        updatedUrl.includes('/verify/traffic/error') ||
        updatedUrl.includes('/verify/')
      ) {
        if (currentRequestState === RequestState.WAITING_COMPLETE && currentRequestId) {
          console.warn(`[BatchWorker] Verification required on worker tab: ${updatedUrl}`);
          try {
            chrome.tabs.update(tabId, { active: true });
            if (tab.windowId) {
              chrome.windows.update(tab.windowId, { focused: true });
            }
          } catch {}

          sendToNativeHost({
            protocol_version: PROTOCOL_VERSION,
            type: 'process_error',
            request_id: currentRequestId,
            url: currentInputUrl || updatedUrl,
            error_code: 'VERIFICATION_REQUIRED',
            message: 'Shopee yêu cầu xác minh trên Chrome.'
          });
        }
      }

      // 404 / Not Found detection
      if (
        updatedTitle &&
        (updatedTitle.includes('404') || updatedTitle.includes('Sản phẩm không tồn tại'))
      ) {
        if (currentRequestState === RequestState.WAITING_COMPLETE && currentRequestId) {
          console.warn(`[BatchWorker] Product not found on worker tab: ${updatedTitle}`);
          currentRequestState = RequestState.FAILED;
          if (currentTimeoutTimer) {
            clearTimeout(currentTimeoutTimer);
            currentTimeoutTimer = null;
          }

          sendToNativeHost({
            protocol_version: PROTOCOL_VERSION,
            type: 'process_error',
            request_id: currentRequestId,
            url: currentInputUrl || updatedUrl,
            error_code: 'NOT_FOUND',
            message: 'Không tìm thấy sản phẩm'
          });
        }
      }
    });
  }

  // Validate extension ID
  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id) {
    if (chrome.runtime.id !== EXPECTED_EXTENSION_ID) {
      console.warn(`[Bridge] Runtime Extension ID '${chrome.runtime.id}' differs from expected '${EXPECTED_EXTENSION_ID}'. Native host allowed_origins must match.`);
    }
  }

  function broadcastStatus(state, message = '', hostInstalled = true) {
    currentState = state;
    if (message) {
      lastErrorMessage = message;
    }
    isHostInstalled = hostInstalled;

    try {
      chrome.runtime.sendMessage({
        action: 'BRIDGE_STATUS_CHANGED',
        status: state,
        connected: state === BridgeState.CONNECTED,
        wasConnectedBefore: wasConnectedBefore,
        hostInstalled: isHostInstalled,
        message: message || lastErrorMessage
      }, () => {
        if (chrome.runtime.lastError) {
          // Expected: popup is closed or no listener active
        }
      });
    } catch (e) {
      // Ignore broadcast errors
    }
  }

  function sendToNativeHost(payload) {
    if (nativePort) {
      try {
        nativePort.postMessage(payload);
        return true;
      } catch (err) {
        console.error('[Bridge] Failed to post message to Native Host:', err);
        return false;
      }
    }
    return false;
  }

  async function ensureActiveWorkerTab() {
    // 1. Record user's original tab before batch navigation if not already saved
    if (!isBatchRunning || originalUserTabId === null) {
      try {
        const [currentActive] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        if (currentActive && currentActive.id) {
          originalUserTabId = currentActive.id;
          originalUserWindowId = currentActive.windowId;
          console.log(`[BatchWorker] Original tab saved: ${originalUserTabId}, windowId: ${originalUserWindowId}`);
        }
      } catch (err) {
        console.warn('[BatchWorker] Could not query active tab:', err);
      }
      isBatchRunning = true;
    }

    // 2. Find existing or create exactly ONE worker tab in active foreground state
    let workerTab = null;
    if (dedicatedWorkerTabId !== null) {
      try {
        const existing = await chrome.tabs.get(dedicatedWorkerTabId);
        if (existing && existing.id) {
          workerTab = existing;
        }
      } catch {
        dedicatedWorkerTabId = null;
      }
    }

    if (!workerTab) {
      workerTab = await chrome.tabs.create({ url: 'about:blank', active: true });
      dedicatedWorkerTabId = workerTab.id;
      console.log(`[BatchWorker] Worker tab created: ${dedicatedWorkerTabId}`);
    } else {
      await chrome.tabs.update(workerTab.id, { active: true });
    }

    // 3. Focus worker window
    if (workerTab.windowId) {
      try {
        await chrome.windows.update(workerTab.windowId, { focused: true });
      } catch {}
    }

    currentWorkerTabId = workerTab.id;
    return workerTab;
  }

  async function restoreOriginalUserTab() {
    console.log(`[BatchWorker] Restoring original tab...`);
    if (originalUserTabId !== null) {
      try {
        const orig = await chrome.tabs.get(originalUserTabId);
        if (orig && orig.id) {
          await chrome.tabs.update(originalUserTabId, { active: true });
          if (originalUserWindowId) {
            await chrome.windows.update(originalUserWindowId, { focused: true });
          }
          console.log(`[BatchWorker] Original tab restored: ${originalUserTabId}`);
        }
      } catch (e) {
        console.log(`[BatchWorker] Original tab no longer exists: ${originalUserTabId}`);
      }
    }

    // Close dedicated worker tab
    if (dedicatedWorkerTabId !== null) {
      try {
        await chrome.tabs.remove(dedicatedWorkerTabId);
      } catch {}
      dedicatedWorkerTabId = null;
      currentWorkerTabId = null;
    }

    originalUserTabId = null;
    originalUserWindowId = null;
    isBatchRunning = false;
    currentRequestState = RequestState.IDLE;
    currentRequestId = null;
    if (currentTimeoutTimer) {
      clearTimeout(currentTimeoutTimer);
      currentTimeoutTimer = null;
    }
  }

  function parseExpectedProduct(url) {
    if (!url || typeof url !== 'string') return { shopId: '', itemId: '', productKey: '' };
    try {
      const parsed = new URL(url);
      const pathname = parsed.pathname;
      const searchParams = parsed.searchParams;

      const iMatch = pathname.match(/-i\.(\d+)\.(\d+)/);
      if (iMatch) {
        return { shopId: iMatch[1], itemId: iMatch[2], productKey: `${iMatch[1]}:${iMatch[2]}` };
      }

      const prodMatch = pathname.match(/\/product\/(\d+)\/(\d+)/);
      if (prodMatch) {
        return { shopId: prodMatch[1], itemId: prodMatch[2], productKey: `${prodMatch[1]}:${prodMatch[2]}` };
      }

      const qShopId = searchParams.get('shopid') || searchParams.get('shop_id');
      const qItemId = searchParams.get('itemid') || searchParams.get('item_id');
      if (qShopId && qItemId && /^\d+$/.test(qShopId) && /^\d+$/.test(qItemId)) {
        return { shopId: qShopId, itemId: qItemId, productKey: `${qShopId}:${qItemId}` };
      }
    } catch {}
    return { shopId: '', itemId: '', productKey: '' };
  }

  /**
   * Single Canonical Function to build and send an Authoritative Product Result to Desktop.
   * Both manual user send ("Gửi sang ứng dụng") and Task 006Z batch execution MUST call this function.
   *
   * @param {{
   *   snapshot: {
   *     schema_version?: number,
   *     scan_state?: string,
   *     product_key?: string,
   *     product_name?: string,
   *     shop_id?: string,
   *     item_id?: string,
   *     final_url?: string,
   *     url?: string,
   *     images?: string[],
   *     image_count?: number
   *   },
   *   requestId?: string|null,
   *   inputUrl?: string|null,
   *   source?: 'manual' | 'batch'
   * }} options
   * @returns {boolean} True if sent successfully
   */
  function sendCompleteProductToDesktop({
    snapshot,
    requestId = null,
    inputUrl = null,
    source = 'batch'
  }) {
    if (!snapshot || typeof snapshot !== 'object') {
      console.error('[sendCompleteProductToDesktop] Missing snapshot');
      return false;
    }

    const shopId = String(snapshot.shop_id || '').trim();
    const itemId = String(snapshot.item_id || '').trim();
    const productName = String(snapshot.product_name || '').trim();
    const productKey = snapshot.product_key || (shopId && itemId ? `${shopId}:${itemId}` : '');
    const authoritativeImages = Array.isArray(snapshot.images) ? [...snapshot.images] : [];
    const authoritativeCount = authoritativeImages.length;
    const declaredCount = snapshot.image_count !== undefined ? snapshot.image_count : authoritativeCount;

    if (authoritativeCount === 0 || !productName || !shopId || !itemId) {
      console.error('[sendCompleteProductToDesktop] Incomplete snapshot rejected:', {
        shopId, itemId, productName, authoritativeCount
      });
      return false;
    }

    if (declaredCount !== authoritativeCount) {
      console.error('[sendCompleteProductToDesktop] Protocol integrity assertion failed:', {
        declaredCount, authoritativeCount
      });
      return false;
    }

    const payload = {
      protocol_version: PROTOCOL_VERSION,
      type: 'product_result',
      source: source,
      data: {
        schema_version: snapshot.schema_version || 1,
        scan_state: snapshot.scan_state || 'COMPLETE',
        product_key: productKey,
        input_url: inputUrl || snapshot.final_url || snapshot.url || '',
        final_url: snapshot.final_url || snapshot.url || inputUrl || '',
        product_name: productName,
        shop_id: shopId,
        item_id: itemId,
        images: authoritativeImages,
        image_count: authoritativeCount
      }
    };

    if (requestId) {
      payload.request_id = requestId;
    }

    console.log(
      `[EXT SEND]\nrequest_id=${requestId || 'N/A'}\nsource=${source}\nproduct_key=${productKey}\nimages=${authoritativeCount}`
    );

    return sendToNativeHost(payload);
  }

  // Alias for backward compatibility
  const sendProductSnapshotToDesktop = sendCompleteProductToDesktop;

  /**
   * Handles OPEN_PRODUCT request from PySide6 Desktop.
   * Navigates the dedicated worker tab and arms the bounded timeout timer.
   * Does NOT execute custom RPC polling; waits for normal 006X AUTHORITATIVE_PRODUCT_COMPLETE event.
   */
  async function handleOpenProductRequest(requestId, url) {
    if (currentTimeoutTimer) {
      clearTimeout(currentTimeoutTimer);
      currentTimeoutTimer = null;
    }

    currentRequestId = requestId;
    currentInputUrl = url;
    const expected = parseExpectedProduct(url);
    currentExpectedProductKey = expected.productKey || null;
    currentRequestState = RequestState.OPENING;
    activeCancellationRequested = false;

    console.log(`[BatchWorker] Mở sản phẩm: req=${requestId}, expectedKey=${currentExpectedProductKey || 'unknown_short_url'}, url=${url}`);

    // Stage 1: NAVIGATING
    sendToNativeHost({
      protocol_version: PROTOCOL_VERSION,
      type: 'process_progress',
      request_id: requestId,
      stage: 'navigating'
    });

    try {
      const workerTab = await ensureActiveWorkerTab();
      if (activeCancellationRequested || currentRequestId !== requestId) return;

      currentWorkerTabId = workerTab.id;

      // Navigate worker tab to requested Shopee URL
      await chrome.tabs.update(workerTab.id, { url: url });
      console.log(`[BatchWorker] Worker tab navigating to: ${url}`);

      // Stage 2: WAITING_PAGE
      sendToNativeHost({
        protocol_version: PROTOCOL_VERSION,
        type: 'process_progress',
        request_id: requestId,
        stage: 'waiting_page'
      });

      currentRequestState = RequestState.WAITING_COMPLETE;

      // Arm bounded per-product timeout timer
      currentTimeoutTimer = setTimeout(() => {
        if (currentRequestId === requestId && currentRequestState === RequestState.WAITING_COMPLETE) {
          console.warn(`[BatchWorker] Timeout waiting for COMPLETE on req=${requestId}`);
          currentRequestState = RequestState.FAILED;
          currentTimeoutTimer = null;

          sendToNativeHost({
            protocol_version: PROTOCOL_VERSION,
            type: 'process_error',
            request_id: requestId,
            url: url,
            error_code: 'PRODUCT_TIMEOUT',
            message: 'Hết thời gian chờ dữ liệu ảnh hoàn chỉnh từ sản phẩm.'
          });
        }
      }, PRODUCT_TIMEOUT_MS);

    } catch (err) {
      console.error(`[BatchWorker] Lỗi mở sản phẩm req=${requestId}:`, err);
      currentRequestState = RequestState.FAILED;
      sendToNativeHost({
        protocol_version: PROTOCOL_VERSION,
        type: 'process_error',
        request_id: requestId,
        url: url,
        error_code: 'ERROR',
        message: err.message || 'Lỗi không xác định khi mở tab'
      });
    }
  }

  // Old automatic batch scanner path using RUN_FULL_SCAN RPC is disabled
  const handleProcessUrlRequest = handleOpenProductRequest;

  function cleanupNativePort() {
    if (nativePort) {
      try {
        nativePort.onMessage.removeListener(handleNativeMessage);
        nativePort.onDisconnect.removeListener(handleNativeDisconnect);
        nativePort.disconnect();
      } catch (e) {}
      nativePort = null;
    }
    if (isBatchRunning) {
      restoreOriginalUserTab();
    }
  }

  function handleNativeMessage(msg) {
    if (!msg || typeof msg !== 'object') return;

    if (msg.type === 'bridge_status') {
      const desktopConnected = !!msg.desktop_connected;
      if (desktopConnected) {
        wasConnectedBefore = true;
        broadcastStatus(BridgeState.CONNECTED, msg.message || 'Đã kết nối với Desktop.', true);
      } else {
        const errorMsg = msg.message || (wasConnectedBefore ? 'Mất kết nối với Desktop.' : 'Shopee Image Downloader chưa được mở.');
        broadcastStatus(BridgeState.DISCONNECTED, errorMsg, true);
      }
    } else if (msg.type === 'open_product' || msg.type === 'process_url') {
      const requestId = msg.request_id;
      const url = msg.url;
      if (requestId && url) {
        handleOpenProductRequest(requestId, url);
      }
    } else if (msg.type === 'cancel_processing') {
      const requestId = msg.request_id;
      if (!requestId || requestId === currentRequestId) {
        activeCancellationRequested = true;
        currentRequestId = null;
        currentRequestState = RequestState.IDLE;
        if (currentTimeoutTimer) {
          clearTimeout(currentTimeoutTimer);
          currentTimeoutTimer = null;
        }
      }
      restoreOriginalUserTab();
    } else if (msg.type === 'batch_finished') {
      console.log('[Bridge] Batch finished notification received from Desktop:', msg);
      restoreOriginalUserTab();
    } else if (msg.type === 'product_result_ack') {
      console.log('[Bridge] Product result acknowledged by Desktop app:', msg);
    } else if (msg.type === 'error') {
      console.warn('[Bridge] Native host error:', msg.error);
    }
  }

  function handleNativeDisconnect() {
    const lastErr = chrome.runtime.lastError;
    const hadConnection = (currentState === BridgeState.CONNECTED || wasConnectedBefore);
    nativePort = null;

    if (lastErr && lastErr.message) {
      console.warn('[Bridge] Native port disconnected with error:', lastErr.message);
      if (lastErr.message.toLowerCase().includes('specified native messaging host not found') ||
          lastErr.message.toLowerCase().includes('host not found') ||
          lastErr.message.toLowerCase().includes('access denied')) {
        isHostInstalled = false;
        lastErrorMessage = 'Native Host chưa được cài đặt.';
        broadcastStatus(BridgeState.DISCONNECTED, lastErrorMessage, false);
        return;
      }
    }

    if (hadConnection) {
      lastErrorMessage = 'Mất kết nối với Desktop. Hãy mở ứng dụng rồi nhấn "Kết nối lại".';
    } else {
      lastErrorMessage = 'Không tìm thấy ứng dụng. Hãy mở Shopee Image Downloader trước.';
    }
    broadcastStatus(BridgeState.DISCONNECTED, lastErrorMessage, true);
  }

  function startUserInitiatedConnection() {
    if (nativePort) {
      try {
        broadcastStatus(BridgeState.CONNECTING, 'Đang kiểm tra kết nối Desktop...');
        nativePort.postMessage({ type: 'connect_desktop', protocol_version: PROTOCOL_VERSION });
        return;
      } catch (err) {
        cleanupNativePort();
      }
    }

    broadcastStatus(BridgeState.CONNECTING, 'Đang kết nối Native Host...');

    try {
      nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);
      nativePort.onMessage.addListener(handleNativeMessage);
      nativePort.onDisconnect.addListener(handleNativeDisconnect);

      nativePort.postMessage({
        type: 'connect_desktop',
        protocol_version: PROTOCOL_VERSION
      });
    } catch (err) {
      console.error('[Bridge] Failed to connect to Native Host:', err);
      nativePort = null;
      lastErrorMessage = 'Native Host chưa được cài đặt.';
      broadcastStatus(BridgeState.DISCONNECTED, lastErrorMessage, false);
    }
  }

  // Handle runtime messages from content scripts and popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (!request) return false;

    // 1. Authoritative COMPLETE event from 006X Content Script
    if (request.type === 'AUTHORITATIVE_PRODUCT_COMPLETE') {
      const senderTabId = sender?.tab?.id;
      const snapshot = request.snapshot;
      const prodKey = request.product_key || snapshot?.product_key;

      console.log(`[BatchWorker] Received AUTHORITATIVE_PRODUCT_COMPLETE: key=${prodKey}, senderTab=${senderTabId}`);

      // Validate worker tab context
      if (dedicatedWorkerTabId !== null && senderTabId && senderTabId !== dedicatedWorkerTabId) {
        console.warn(`[BatchWorker] Ignored COMPLETE event from non-worker tab (${senderTabId} !== ${dedicatedWorkerTabId})`);
        return false;
      }

      // Validate request state
      if (currentRequestState !== RequestState.WAITING_COMPLETE || !currentRequestId) {
        console.log(`[BatchWorker] Ignored COMPLETE event: currentRequestState=${currentRequestState}, currentRequestId=${currentRequestId}`);
        return false;
      }

      // Validate expected product key if known
      if (currentExpectedProductKey && prodKey && prodKey !== currentExpectedProductKey) {
        console.warn(`[BatchWorker] Ignored COMPLETE event for mismatched product key: ${prodKey} !== ${currentExpectedProductKey}`);
        return false;
      }

      // Validate snapshot integrity
      const images = Array.isArray(snapshot?.images) ? snapshot.images : [];
      if (!snapshot || snapshot.scan_state !== 'COMPLETE' || images.length === 0) {
        console.warn('[BatchWorker] Ignored incomplete snapshot payload:', snapshot);
        return false;
      }

      // AUTO-SEND EXACTLY ONCE
      currentRequestState = RequestState.SENT;
      if (currentTimeoutTimer) {
        clearTimeout(currentTimeoutTimer);
        currentTimeoutTimer = null;
      }

      const reqId = currentRequestId;
      const inUrl = currentInputUrl;

      // Forward through single canonical sender
      const sent = sendCompleteProductToDesktop({
        snapshot: snapshot,
        requestId: reqId,
        inputUrl: inUrl,
        source: 'batch'
      });

      if (!sent) {
        console.error(`[BatchWorker] Failed to forward automatic product result for req=${reqId}`);
      }

      return false;
    }

    if (!request.action) return false;

    if (request.action === 'GET_BRIDGE_STATUS') {
      sendResponse({
        status: currentState,
        connected: currentState === BridgeState.CONNECTED,
        wasConnectedBefore: wasConnectedBefore,
        hostInstalled: isHostInstalled,
        message: lastErrorMessage,
        hostName: NATIVE_HOST_NAME
      });
      return false; // Synchronous response
    }

    if (request.action === 'CONNECT_DESKTOP' || request.action === 'CONNECT_BRIDGE') {
      startUserInitiatedConnection();
      sendResponse({
        status: currentState,
        connected: currentState === BridgeState.CONNECTED,
        wasConnectedBefore: wasConnectedBefore,
        hostInstalled: isHostInstalled,
        message: lastErrorMessage
      });
      return false; // Synchronous response
    }

    if (request.action === 'DISCONNECT_BRIDGE') {
      if (nativePort) {
        try {
          nativePort.postMessage({ type: 'disconnect_desktop', protocol_version: PROTOCOL_VERSION });
        } catch (e) {}
      }
      cleanupNativePort();
      wasConnectedBefore = false;
      lastErrorMessage = 'Đã ngắt kết nối.';
      broadcastStatus(BridgeState.DISCONNECTED, 'Đã ngắt kết nối.', isHostInstalled);
      sendResponse({
        status: BridgeState.DISCONNECTED,
        connected: false
      });
      return false; // Synchronous response
    }

    // Manual Send ("Gửi sang ứng dụng")
    if (request.action === 'SEND_PRODUCT_TO_DESKTOP' || request.action === 'MANUAL_SEND_CURRENT_PRODUCT') {
      if (currentState !== BridgeState.CONNECTED || !nativePort) {
        sendResponse({
          success: false,
          error: 'Chưa kết nối đến ứng dụng Desktop. Vui lòng kết nối ứng dụng trước.'
        });
        return false;
      }

      (async () => {
        try {
          let tabId = request.tabId;
          let tabUrl = request.url;

          if (!tabId && typeof chrome !== 'undefined' && chrome.tabs && typeof chrome.tabs.query === 'function') {
            const [activeTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
            if (activeTab && activeTab.id) {
              tabId = activeTab.id;
              tabUrl = activeTab.url;
            }
          }

          // Request authoritative snapshot from content script
          let snapRes = null;
          if (tabId) {
            try {
              snapRes = await chrome.tabs.sendMessage(tabId, { type: 'GET_COMPLETE_SNAPSHOT' }, { frameId: 0 });
            } catch (tabErr) {
              console.warn('[Bridge] Content script GET_COMPLETE_SNAPSHOT failed, trying fallback payload:', tabErr);
            }
          }

          if (snapRes && snapRes.ok && snapRes.snapshot) {
            const sent = sendCompleteProductToDesktop({
              snapshot: snapRes.snapshot,
              requestId: null,
              inputUrl: tabUrl || snapRes.snapshot.final_url,
              source: 'manual'
            });
            sendResponse({
              success: sent,
              product_key: snapRes.snapshot.product_key
            });
            return;
          }

          // Fallback if payload provided from popup cache
          if (request.payload) {
            const pImages = Array.isArray(request.payload.images) ? request.payload.images : [];
            const sent = sendCompleteProductToDesktop({
              snapshot: {
                schema_version: 1,
                scan_state: 'COMPLETE',
                product_key: `${request.payload.shop_id}:${request.payload.item_id}`,
                product_name: request.payload.product_name,
                shop_id: request.payload.shop_id,
                item_id: request.payload.item_id,
                final_url: request.payload.url || tabUrl || '',
                images: pImages,
                image_count: pImages.length
              },
              requestId: null,
              inputUrl: request.payload.url || tabUrl,
              source: 'manual'
            });
            sendResponse({
              success: sent,
              product_key: `${request.payload.shop_id}:${request.payload.item_id}`
            });
            return;
          }

          sendResponse({
            success: false,
            error: snapRes?.message || 'Không thể lấy dữ liệu ảnh hoàn chỉnh từ trang sản phẩm.'
          });
        } catch (err) {
          console.error('[Bridge] Error transmitting manual product result:', err);
          sendResponse({
            success: false,
            error: err.message || String(err)
          });
        }
      })();

      return true; // Asynchronous response
    }

    return false;
  });
})();
