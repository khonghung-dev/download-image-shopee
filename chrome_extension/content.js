/**
 * Shopee Product Extractor - Content Script
 * Executes in the context of the Shopee webpage.
 *
 * Runs the canonical product extraction lifecycle and broadcasts
 * AUTHORITATIVE_PRODUCT_COMPLETE event when product extraction reaches complete state.
 */

(function () {
  'use strict';

  const LIFECYCLE_CHECK_INTERVAL_MS = 500;
  const LIFECYCLE_TIMEOUT_MS = 30000;

  let lastEmittedProductKey = null;
  let isLifecycleRunning = false;

  /**
   * Helper to build an authoritative ProductSnapshotV1 from an extraction result.
   */
  function buildProductSnapshot(result, currentHref) {
    const images = Array.isArray(result.images) ? result.images : [];
    return {
      schema_version: 1,
      scan_state: 'COMPLETE',
      product_key: result.product_key,
      product_name: result.product_name,
      shop_id: String(result.shop_id || ''),
      item_id: String(result.item_id || ''),
      final_url: result.url || currentHref,
      images: images,
      image_count: images.length,
      completeness_reason: result.completeness_reason
    };
  }

  /**
   * Evaluates if extraction result meets authoritative COMPLETE standards.
   */
  function isAuthoritativeComplete(result, core) {
    if (!result || !core) return false;
    const scanState = result.extraction_status || (result.debug && result.debug.temporary_scan_status) || 'UNKNOWN';
    const isGeneric = core.isGenericProductName(result.product_name);
    const proofValid = core.hasValidCompletenessProof(result);
    const images = Array.isArray(result.images) ? result.images : [];

    return (
      scanState === 'COMPLETE' &&
      proofValid &&
      !isGeneric &&
      result.product_name &&
      images.length > 0 &&
      result.shop_id &&
      result.item_id
    );
  }

  /**
   * Runs the canonical product extraction lifecycle.
   * Periodically checks or observes DOM until product achieves authoritative COMPLETE,
   * then emits AUTHORITATIVE_PRODUCT_COMPLETE to background.
   */
  async function runProductExtractionLifecycle() {
    const core = typeof ShopeeExtractorCore !== 'undefined' ? ShopeeExtractorCore : null;
    if (!core) return;

    const currentHref = window.location.href;
    if (!core.isShopeeDomain(currentHref)) return;
    if (currentHref.includes('/verify/captcha') || currentHref.includes('/verify/traffic/error') || currentHref.includes('/verify/')) {
      return;
    }

    const urlInfo = core.parseShopeeUrl(currentHref);
    const targetProductKey = core.createProductKey(urlInfo.shopId, urlInfo.itemId);

    if (isLifecycleRunning) return;
    isLifecycleRunning = true;

    const startTime = Date.now();

    try {
      while (Date.now() - startTime < LIFECYCLE_TIMEOUT_MS) {
        const href = window.location.href;
        if (href.includes('/verify/captcha') || href.includes('/verify/traffic/error') || href.includes('/verify/')) {
          break;
        }

        const currentInfo = core.parseShopeeUrl(href);
        const currentKey = core.createProductKey(currentInfo.shopId, currentInfo.itemId);
        if (targetProductKey && currentKey && currentKey !== targetProductKey) {
          // Page navigated to another product
          break;
        }

        try {
          const result = await core.extractProductData(document, href, { forceRescan: false });
          if (result && isAuthoritativeComplete(result, core)) {
            const productKey = result.product_key || currentKey;

            if (productKey !== lastEmittedProductKey) {
              lastEmittedProductKey = productKey;
              const snapshot = buildProductSnapshot(result, href);

              console.log(`[EXTRACTION COMPLETE]\nproduct_key=${productKey}\nimages=${snapshot.images.length}`);

              // Emit authoritative complete event to background service worker
              if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
                chrome.runtime.sendMessage({
                  type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
                  product_key: productKey,
                  snapshot: snapshot
                }, () => {
                  if (chrome.runtime.lastError) {
                    // Background may not have a listener if batch is not active, ignore
                  }
                });
              }
            }
            break;
          }
        } catch (err) {
          console.debug('[Extraction lifecycle] Attempt error:', err?.message || String(err));
        }

        await new Promise((resolve) => setTimeout(resolve, LIFECYCLE_CHECK_INTERVAL_MS));
      }
    } finally {
      isLifecycleRunning = false;
    }
  }

  /**
   * Retrieves an authoritative COMPLETE snapshot if present in cache, or runs fresh extraction.
   *
   * @param {{ request_id?: string, expected_product_key?: string }} request
   * @returns {Promise<{ ok: boolean, request_id: string|null, snapshot?: object, error_code?: string, message?: string }>}
   */
  async function getCompleteSnapshotRPC(request) {
    const requestId = request.request_id || null;
    const expectedKey = request.expected_product_key || null;
    const core = typeof ShopeeExtractorCore !== 'undefined' ? ShopeeExtractorCore : null;
    if (!core) {
      return {
        ok: false,
        request_id: requestId,
        error_code: 'ENGINE_NOT_INITIALIZED',
        message: 'ShopeeExtractorCore is not initialized in content script.'
      };
    }

    const currentHref = window.location.href;
    const urlInfo = core.parseShopeeUrl(currentHref);
    const key = expectedKey || core.createProductKey(urlInfo.shopId, urlInfo.itemId);

    if (key && core.ProductCache.hasComplete(key)) {
      const cached = core.ProductCache.get(key);
      const snapshot = buildProductSnapshot(cached, currentHref);

      console.log(`[RPC CACHE]\nproduct_key=${snapshot.product_key}\nimages=${snapshot.images.length}`);

      return {
        ok: true,
        request_id: requestId,
        snapshot: snapshot,
        result: cached
      };
    }

    // A missing/invalid authoritative cache entry must be replaced only by a
    // fresh canonical full-gallery traversal. Never promote the visible window.
    try {
      const result = await core.extractProductData(document, currentHref, { forceRescan: true });
      if (result && isAuthoritativeComplete(result, core)) {
        const snapshot = buildProductSnapshot(result, currentHref);
        return {
          ok: true,
          request_id: requestId,
          snapshot: snapshot,
          result: result
        };
      }
      return {
        ok: false,
        request_id: requestId,
        error_code: 'INCOMPLETE',
        message: 'Product gallery has not reached authoritative COMPLETE state.'
      };
    } catch (err) {
      return {
        ok: false,
        request_id: requestId,
        error_code: 'EXTRACT_ERROR',
        message: err.message || String(err)
      };
    }
  }

  // Automatically start normal extraction lifecycle when page loads
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    if (document.readyState === 'complete' || document.readyState === 'interactive' || typeof window.addEventListener !== 'function') {
      setTimeout(runProductExtractionLifecycle, 300);
    } else {
      window.addEventListener('DOMContentLoaded', () => {
        setTimeout(runProductExtractionLifecycle, 300);
      });
    }
  }

  // Register single message listener
  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (!request || typeof request !== 'object') return false;

      if (request.type === 'GET_COMPLETE_SNAPSHOT') {
        getCompleteSnapshotRPC(request)
          .then((res) => sendResponse(res))
          .catch((err) =>
            sendResponse({
              ok: false,
              request_id: request.request_id || null,
              error_code: 'GET_SNAPSHOT_ERROR',
              message: err.message || String(err)
            })
          );
        return true; // Keep message channel open for async response
      }

      if (request.action === 'EXTRACT_PRODUCT_DATA') {
        (async () => {
          try {
            const core = typeof ShopeeExtractorCore !== 'undefined' ? ShopeeExtractorCore : null;
            if (!core) {
              sendResponse({
                success: false,
                error: 'Extraction engine not initialized.'
              });
              return;
            }

            const currentUrl = window.location.href;
            // Popup extraction is an authoritative manual request, not a request
            // for whichever thumbnails are currently rendered. Always bypass a
            // potentially stale result and await the canonical carousel scan.
            const result = await core.extractProductData(
              document,
              currentUrl,
              { forceRescan: true }
            );

            if (result && isAuthoritativeComplete(result, core)) {
              // If complete, broadcast event as well
              const snapshot = buildProductSnapshot(result, currentUrl);
              if (result.product_key !== lastEmittedProductKey) {
                lastEmittedProductKey = result.product_key;
                chrome.runtime.sendMessage({
                  type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
                  product_key: result.product_key,
                  snapshot: snapshot
                }, () => {
                  if (chrome.runtime.lastError) {}
                });
              }
              sendResponse({ success: true, data: result });
            } else {
              sendResponse({
                success: false,
                error: 'Bộ sưu tập ảnh chưa được duyệt đầy đủ; không thể trả về cửa sổ ảnh đang hiển thị.',
                data: result || null
              });
            }
          } catch (err) {
            sendResponse({
              success: false,
              error: err.message || String(err)
            });
          }
        })();
        return true;
      }

      return false;
    });
  }
})();
