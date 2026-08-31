/**
 * Shopee Product Extractor - Content Script
 * Executes in the context of the Shopee webpage.
 */

(function () {
  'use strict';

  // Listen for extraction requests from the popup
  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request && request.action === 'EXTRACT_PRODUCT_DATA') {
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
            const extractedData = await core.extractProductData(document, currentUrl);

            sendResponse({
              success: true,
              data: extractedData
            });
          } catch (err) {
            sendResponse({
              success: false,
              error: err.message || String(err)
            });
          }
        })();
        return true; // Keep message channel open for async response
      }
    });
  }
})();
