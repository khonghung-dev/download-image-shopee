/**
 * Shopee Product Extractor - Popup Controller
 */

(function () {
  'use strict';

  // DOM Elements
  const stateLoading = document.getElementById('state-loading');
  const stateNotShopee = document.getElementById('state-not-shopee');
  const stateError = document.getElementById('state-error');
  const errorMessage = document.getElementById('error-message');
  const stateSuccess = document.getElementById('state-success');

  const resProductName = document.getElementById('res-product-name');
  const resShopId = document.getElementById('res-shop-id');
  const resItemId = document.getElementById('res-item-id');
  const resImageCount = document.getElementById('res-image-count');
  const resGalleryGrid = document.getElementById('res-gallery-grid');
  const resUrlsList = document.getElementById('res-urls-list');

  const debugProductKey = document.getElementById('debug-product-key');
  const debugTriggerReason = document.getElementById('debug-trigger-reason');
  const debugPrevComplete = document.getElementById('debug-prev-complete');
  const debugCanonicalFound = document.getElementById('debug-canonical-found');
  const debugLeftmostReached = document.getElementById('debug-leftmost-reached');
  const debugRightmostReached = document.getElementById('debug-rightmost-reached');
  const debugLeftAdvances = document.getElementById('debug-left-advances');
  const debugRightAdvances = document.getElementById('debug-right-advances');
  const debugTotalDiscovered = document.getElementById('debug-total-discovered');
  const debugTempStatus = document.getElementById('debug-temp-status');
  const debugCacheReplaced = document.getElementById('debug-cache-replaced');
  const debugSourceLabel = document.getElementById('debug-source-label');
  const debugFinalCount = document.getElementById('debug-final-count');
  const galleryEmptyWarning = document.getElementById('gallery-empty-warning');

  const btnCopy = document.getElementById('btn-copy');
  const btnCopyText = document.getElementById('btn-copy-text');
  const btnCopyIcon = document.getElementById('btn-copy-icon');
  const btnRescan = document.getElementById('btn-rescan');

  const btnToggleGallery = document.getElementById('btn-toggle-gallery');
  const galleryDrawer = document.getElementById('gallery-drawer');
  const galleryToggleIcon = document.getElementById('gallery-toggle-icon');

  let currentExtractedData = null;
  let activeTabId = null;
  let activeTabUrl = null;

  function showView(viewName) {
    stateLoading.classList.add('hidden');
    stateNotShopee.classList.add('hidden');
    stateError.classList.add('hidden');
    stateSuccess.classList.add('hidden');

    if (viewName === 'loading') {
      stateLoading.classList.remove('hidden');
    } else if (viewName === 'not_shopee') {
      stateNotShopee.classList.remove('hidden');
    } else if (viewName === 'error') {
      stateError.classList.remove('hidden');
    } else if (viewName === 'success') {
      stateSuccess.classList.remove('hidden');
    }
  }

  function renderProductData(data, tabUrl) {
    const images = Array.isArray(data.images) ? data.images : [];
    const debug = data.debug || {};
    const imageSource = data.image_source || debug.selected_source || 'none';
    const sourceLabel = debug.selected_source_label ||
      (imageSource === 'gallery_carousel' ? 'Main Gallery Carousel' :
       imageSource === 'structured_data' ? 'Structured Product Data' :
       imageSource === 'structured_single_fallback' ? 'Structured Single-Image Fallback' : 'None');

    const productKey = data.product_key || debug.product_key || `${data.shop_id || ''}:${data.item_id || ''}`;
    const triggerReason = debug.trigger_reason || 'initial';
    const prevComplete = debug.previous_complete_images !== undefined ? debug.previous_complete_images : 0;
    const canonicalFound = debug.canonical_gallery_found !== undefined ? (debug.canonical_gallery_found ? 'yes' : 'no') : 'yes';
    const leftmostReached = debug.leftmost_reached !== undefined ? (debug.leftmost_reached ? 'yes' : 'no') : 'yes';
    const rightmostReached = debug.rightmost_reached !== undefined ? (debug.rightmost_reached ? 'yes' : 'no') : 'yes';
    const leftAdvances = debug.carousel_left_advances !== undefined ? debug.carousel_left_advances : 0;
    const rightAdvances = debug.carousel_right_advances !== undefined ? debug.carousel_right_advances : 0;
    const totalDiscovered = debug.total_unique_media !== undefined ? debug.total_unique_media : images.length;
    const tempStatus = debug.temporary_scan_status || data.extraction_status || 'COMPLETE';
    const cacheReplaced = debug.cache_replaced !== undefined ? (debug.cache_replaced ? 'yes' : 'no') : 'yes';
    const finalAuthoritative = debug.final_authoritative_images !== undefined ? debug.final_authoritative_images : images.length;

    currentExtractedData = {
      url: data.url || tabUrl,
      product_name: data.product_name || 'Không xác định',
      shop_id: data.shop_id || 'N/A',
      item_id: data.item_id || 'N/A',
      product_key: productKey,
      images: images,
      image_source: imageSource,
      extraction_status: tempStatus,
      debug: {
        trigger_reason: triggerReason,
        previous_complete_images: prevComplete,
        canonical_gallery_found: canonicalFound,
        leftmost_reached: leftmostReached,
        rightmost_reached: rightmostReached,
        carousel_left_advances: leftAdvances,
        carousel_right_advances: rightAdvances,
        total_unique_media: totalDiscovered,
        temporary_scan_status: tempStatus,
        cache_replaced: cacheReplaced,
        selected_source: imageSource,
        selected_source_label: sourceLabel,
        final_authoritative_images: finalAuthoritative
      }
    };

    resProductName.textContent = currentExtractedData.product_name;
    resShopId.textContent = currentExtractedData.shop_id;
    resItemId.textContent = currentExtractedData.item_id;
    resImageCount.textContent = currentExtractedData.images.length;

    // Debug metadata display
    if (debugProductKey) debugProductKey.textContent = productKey || '--';
    if (debugTriggerReason) debugTriggerReason.textContent = triggerReason;
    if (debugPrevComplete) debugPrevComplete.textContent = String(prevComplete);
    if (debugCanonicalFound) debugCanonicalFound.textContent = canonicalFound;
    if (debugLeftmostReached) debugLeftmostReached.textContent = leftmostReached;
    if (debugRightmostReached) debugRightmostReached.textContent = rightmostReached;
    if (debugLeftAdvances) debugLeftAdvances.textContent = String(leftAdvances);
    if (debugRightAdvances) debugRightAdvances.textContent = String(rightAdvances);
    if (debugTotalDiscovered) debugTotalDiscovered.textContent = String(totalDiscovered);
    if (debugTempStatus) debugTempStatus.textContent = tempStatus;
    if (debugCacheReplaced) debugCacheReplaced.textContent = cacheReplaced;
    if (debugSourceLabel) debugSourceLabel.textContent = sourceLabel;
    if (debugFinalCount) debugFinalCount.textContent = String(finalAuthoritative);

    // Empty gallery warning handling
    if (images.length === 0) {
      galleryEmptyWarning.classList.remove('hidden');
    } else {
      galleryEmptyWarning.classList.add('hidden');
    }

    // Render Gallery Thumbnails
    resGalleryGrid.innerHTML = '';
    if (images.length > 0) {
      images.forEach((imgUrl, idx) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'gallery-item';

        const img = document.createElement('img');
        img.src = imgUrl;
        img.alt = `Ảnh ${idx + 1}`;
        img.loading = 'lazy';
        img.onerror = () => {
          itemDiv.style.display = 'none';
        };

        const badge = document.createElement('span');
        badge.className = 'item-num';
        badge.textContent = `${idx + 1}`;

        itemDiv.appendChild(img);
        itemDiv.appendChild(badge);
        resGalleryGrid.appendChild(itemDiv);
      });

      // Render URLs List
      resUrlsList.textContent = images.join('\n');
    } else {
      resGalleryGrid.innerHTML = '<p style="grid-column: span 4; font-size: 11px; color: var(--text-muted); text-align: center; padding: 10px;">Không tìm thấy ảnh bộ sưu tập chính xác</p>';
      resUrlsList.textContent = 'Không có URL ảnh hợp lệ.';
    }

    showView('success');
  }

  async function performExtraction(forceRescan = false) {
    showView('loading');

    if (!activeTabId || !activeTabUrl) {
      showView('not_shopee');
      return;
    }

    try {
      chrome.tabs.sendMessage(activeTabId, { action: 'EXTRACT_PRODUCT_DATA', forceRescan }, async (response) => {
        if (!chrome.runtime.lastError && response && response.success && response.data) {
          renderProductData(response.data, activeTabUrl);
        } else {
          // Fallback: Inject extractor script directly via chrome.scripting API if content script wasn't active
          try {
            if (chrome.scripting) {
              const injectionResults = await chrome.scripting.executeScript({
                target: { tabId: activeTabId },
                func: async (rescanFlag) => {
                  if (typeof ShopeeExtractorCore !== 'undefined') {
                    return await ShopeeExtractorCore.extractProductData(document, window.location.href, { forceRescan: rescanFlag });
                  }
                  return null;
                },
                args: [forceRescan]
              });

              if (injectionResults && injectionResults[0] && injectionResults[0].result) {
                renderProductData(injectionResults[0].result, activeTabUrl);
                return;
              }
            }

            errorMessage.textContent = 'Vui lòng tải lại trang sản phẩm Shopee và thử lại.';
            showView('error');
          } catch (injectErr) {
            console.error('Fallback injection failed:', injectErr);
            errorMessage.textContent = 'Không thể kết nối với tab Shopee hiện tại.';
            showView('error');
          }
        }
      });
    } catch (err) {
      console.error('Extraction dispatch failed:', err);
      errorMessage.textContent = err.message || String(err);
      showView('error');
    }
  }

  // Copy to clipboard handler
  btnCopy.addEventListener('click', async () => {
    if (!currentExtractedData) return;

    const payload = JSON.stringify(currentExtractedData, null, 2);

    try {
      await navigator.clipboard.writeText(payload);
      const originalText = btnCopyText.textContent;
      const originalIcon = btnCopyIcon.textContent;

      btnCopy.classList.add('copied');
      btnCopyText.textContent = 'Đã sao chép!';
      btnCopyIcon.textContent = '✓';

      setTimeout(() => {
        btnCopy.classList.remove('copied');
        btnCopyText.textContent = originalText;
        btnCopyIcon.textContent = originalIcon;
      }, 2000);
    } catch (err) {
      console.error('Clipboard copy failed:', err);
      const textArea = document.createElement('textarea');
      textArea.value = payload;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);

      btnCopyText.textContent = 'Đã sao chép!';
      setTimeout(() => {
        btnCopyText.textContent = 'Sao chép kết quả (JSON)';
      }, 2000);
    }
  });

  // Manual Rescan button handler
  if (btnRescan) {
    btnRescan.addEventListener('click', () => {
      performExtraction(true);
    });
  }

  // Toggle gallery accordion
  let isGalleryOpen = true;
  btnToggleGallery.addEventListener('click', () => {
    isGalleryOpen = !isGalleryOpen;
    galleryDrawer.style.display = isGalleryOpen ? 'block' : 'none';
    galleryToggleIcon.textContent = isGalleryOpen ? '▼' : '▶';
  });

  /**
   * Main popup initialization.
   */
  async function init() {
    showView('loading');

    try {
      if (typeof chrome === 'undefined' || !chrome.tabs) {
        showView('not_shopee');
        return;
      }

      const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!activeTab || !activeTab.url) {
        showView('not_shopee');
        return;
      }

      activeTabId = activeTab.id;
      activeTabUrl = activeTab.url;
      const core = typeof ShopeeExtractorCore !== 'undefined' ? ShopeeExtractorCore : null;

      // Check if domain is Shopee
      if (core && !core.isShopeeDomain(activeTabUrl)) {
        showView('not_shopee');
        return;
      }

      performExtraction(false);
    } catch (err) {
      console.error('Popup init failed:', err);
      errorMessage.textContent = err.message || String(err);
      showView('error');
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
