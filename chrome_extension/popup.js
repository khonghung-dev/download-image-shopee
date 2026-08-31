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

  const debugStructCount = document.getElementById('debug-struct-count');
  const debugInitialVisible = document.getElementById('debug-initial-visible');
  const debugCarouselAdvances = document.getElementById('debug-carousel-advances');
  const debugTotalDiscovered = document.getElementById('debug-total-discovered');
  const debugImageMedia = document.getElementById('debug-image-media');
  const debugVideoMedia = document.getElementById('debug-video-media');
  const debugUnknownMedia = document.getElementById('debug-unknown-media');
  const debugSourceLabel = document.getElementById('debug-source-label');
  const debugFinalCount = document.getElementById('debug-final-count');
  const galleryEmptyWarning = document.getElementById('gallery-empty-warning');

  const btnCopy = document.getElementById('btn-copy');
  const btnCopyText = document.getElementById('btn-copy-text');
  const btnCopyIcon = document.getElementById('btn-copy-icon');

  const btnToggleGallery = document.getElementById('btn-toggle-gallery');
  const galleryDrawer = document.getElementById('gallery-drawer');
  const galleryToggleIcon = document.getElementById('gallery-toggle-icon');

  let currentExtractedData = null;

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

    const structCandidates = debug.structured_candidates !== undefined ? debug.structured_candidates : 0;
    const initialVisible = debug.initial_visible_gallery_media !== undefined ? debug.initial_visible_gallery_media : 0;
    const advances = debug.carousel_advances !== undefined ? debug.carousel_advances : 0;
    const totalDiscovered = debug.total_unique_gallery_media !== undefined ? debug.total_unique_gallery_media : images.length;
    const imageMedia = debug.image_media !== undefined ? debug.image_media : images.length;
    const videoMedia = debug.video_media !== undefined ? debug.video_media : 0;
    const unknownMedia = debug.unknown_media !== undefined ? debug.unknown_media : 0;

    currentExtractedData = {
      url: data.url || tabUrl,
      product_name: data.product_name || 'Không xác định',
      shop_id: data.shop_id || 'N/A',
      item_id: data.item_id || 'N/A',
      images: images,
      image_source: imageSource,
      debug: {
        structured_candidates: structCandidates,
        initial_visible_gallery_media: initialVisible,
        carousel_advances: advances,
        total_unique_gallery_media: totalDiscovered,
        image_media: imageMedia,
        video_media: videoMedia,
        unknown_media: unknownMedia,
        selected_source: imageSource,
        selected_source_label: sourceLabel,
        final_images: images.length
      }
    };

    resProductName.textContent = currentExtractedData.product_name;
    resShopId.textContent = currentExtractedData.shop_id;
    resItemId.textContent = currentExtractedData.item_id;
    resImageCount.textContent = currentExtractedData.images.length;

    // Debug metadata display
    debugStructCount.textContent = String(structCandidates);
    debugInitialVisible.textContent = String(initialVisible);
    debugCarouselAdvances.textContent = String(advances);
    debugTotalDiscovered.textContent = String(totalDiscovered);
    debugImageMedia.textContent = String(imageMedia);
    debugVideoMedia.textContent = String(videoMedia);
    debugUnknownMedia.textContent = String(unknownMedia);
    debugSourceLabel.textContent = sourceLabel;
    debugFinalCount.textContent = String(images.length);

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

      const tabUrl = activeTab.url;
      const core = typeof ShopeeExtractorCore !== 'undefined' ? ShopeeExtractorCore : null;

      // Check if domain is Shopee
      if (core && !core.isShopeeDomain(tabUrl)) {
        showView('not_shopee');
        return;
      }

      // Try communicating with content script
      chrome.tabs.sendMessage(activeTab.id, { action: 'EXTRACT_PRODUCT_DATA' }, async (response) => {
        if (!chrome.runtime.lastError && response && response.success && response.data) {
          renderProductData(response.data, tabUrl);
        } else {
          // Fallback: Inject extractor script directly via chrome.scripting API if content script wasn't active
          try {
            if (chrome.scripting) {
              const injectionResults = await chrome.scripting.executeScript({
                target: { tabId: activeTab.id },
                func: async () => {
                  if (typeof ShopeeExtractorCore !== 'undefined') {
                    return await ShopeeExtractorCore.extractProductData(document, window.location.href);
                  }
                  return null;
                }
              });

              if (injectionResults && injectionResults[0] && injectionResults[0].result) {
                renderProductData(injectionResults[0].result, tabUrl);
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
      console.error('Popup init failed:', err);
      errorMessage.textContent = err.message || String(err);
      showView('error');
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
