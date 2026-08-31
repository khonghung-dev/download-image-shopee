/**
 * Shopee Product Extractor - Core Extraction Engine
 * Manifest V3 compatible pure JavaScript engine for Shopee product pages.
 * Features button-driven carousel enumeration, canonical gallery normalization (rewind-to-left),
 * transactional product caching, media item classification (IMAGE vs VIDEO),
 * and dual-source arbitration.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ShopeeExtractorCore = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const SHOPEE_DOMAINS = [
    'shopee.vn',
    'shopee.sg',
    'shopee.co.id',
    'shopee.co.th',
    'shopee.ph',
    'shopee.my',
    'shopee.com.br',
    'shopee.tw',
    'shopee.com',
    's.shopee.vn'
  ];

  const EXCLUDED_URL_PATTERNS = [
    /shopee-logo/i,
    /logo/i,
    /icon/i,
    /ic_/i,
    /avatar/i,
    /seller/i,
    /mall-badge/i,
    /voucher/i,
    /freeship/i,
    /badge/i,
    /rating/i,
    /star/i,
    /arrow/i,
    /loading/i,
    /placeholder/i,
    /empty/i,
    /spx/i,
    /payment/i,
    /banner/i,
    /\.svg($|\?)/i,
    /^data:image/i
  ];

  const GalleryBoundaryState = Object.freeze({
    UNKNOWN: 'UNKNOWN',
    CONFIRMED: 'CONFIRMED'
  });

  const GalleryCompletenessReason = Object.freeze({
    CAROUSEL_BOUNDS_CONFIRMED: 'CAROUSEL_BOUNDS_CONFIRMED',
    STABLE_SINGLE_PAGE: 'STABLE_SINGLE_PAGE',
    NOT_COMPLETE: 'NOT_COMPLETE'
  });

  const GalleryControlState = Object.freeze({
    MISSING: 'MISSING',
    ACTIVE: 'ACTIVE',
    INACTIVE: 'INACTIVE'
  });

  // A no-arrow gallery is authoritative only after this mutation-aware quiet window.
  // This is a stability threshold, not a pre-scan delay: any relevant gallery mutation
  // or ordered-media/control change resets the window immediately.
  const GALLERY_STABILITY_CONFIG = Object.freeze({
    SETTLE_WINDOW_MS: 1000
  });

  /**
   * Check if a given URL belongs to a supported Shopee domain.
   * @param {string} url
   * @returns {boolean}
   */
  function isShopeeDomain(url) {
    if (!url || typeof url !== 'string') return false;
    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname.toLowerCase();
      return SHOPEE_DOMAINS.some(domain => hostname === domain || hostname.endsWith('.' + domain));
    } catch {
      return false;
    }
  }

  /**
   * Parse Shopee URL to extract shop_id, item_id and check if it's a product page.
   * @param {string} url
   * @returns {{isShopee: boolean, isProductUrl: boolean, shopId: string, itemId: string}}
   */
  function parseShopeeUrl(url) {
    const result = {
      isShopee: false,
      isProductUrl: false,
      shopId: '',
      itemId: ''
    };

    if (!url || typeof url !== 'string') return result;

    result.isShopee = isShopeeDomain(url);
    if (!result.isShopee) return result;

    try {
      const parsed = new URL(url);
      const pathname = parsed.pathname;
      const searchParams = parsed.searchParams;

      // Pattern 1: -i.<shop_id>.<item_id> (Standard web listing URL)
      const iMatch = pathname.match(/-i\.(\d+)\.(\d+)/);
      if (iMatch) {
        result.shopId = iMatch[1];
        result.itemId = iMatch[2];
        result.isProductUrl = true;
        return result;
      }

      // Pattern 2: /product/<shop_id>/<item_id>
      const prodMatch = pathname.match(/\/product\/(\d+)\/(\d+)/);
      if (prodMatch) {
        result.shopId = prodMatch[1];
        result.itemId = prodMatch[2];
        result.isProductUrl = true;
        return result;
      }

      // Pattern 3: Query parameters ?shopid=...&itemid=...
      const qShopId = searchParams.get('shopid') || searchParams.get('shop_id');
      const qItemId = searchParams.get('itemid') || searchParams.get('item_id');
      if (qShopId && qItemId && /^\d+$/.test(qShopId) && /^\d+$/.test(qItemId)) {
        result.shopId = qShopId;
        result.itemId = qItemId;
        result.isProductUrl = true;
        return result;
      }

      // Generic product path
      if (pathname.includes('/product/') || pathname.length > 5) {
        result.isProductUrl = true;
      }
    } catch {
      // Ignore URL parsing errors
    }

    return result;
  }

  /**
   * Clean product name by trimming marketplace suffixes and excess spaces.
   * @param {string} rawTitle
   * @returns {string}
   */
  function cleanProductName(rawTitle) {
    if (!rawTitle || typeof rawTitle !== 'string') return '';
    let name = rawTitle.trim();

    // Remove common marketplace suffixes
    const suffixes = [
      /\s*\|\s*Shopee\s+Việt\s+Nam.*$/i,
      /\s*\|\s*Shopee\s+Vietnam.*$/i,
      /\s*\|\s*Shopee\s+Singapore.*$/i,
      /\s*\|\s*Shopee\s+Malaysia.*$/i,
      /\s*\|\s*Shopee\s+Philippines.*$/i,
      /\s*\|\s*Shopee\s+Thailand.*$/i,
      /\s*\|\s*Shopee\s+Indonesia.*$/i,
      /\s*\|\s*Shopee\s+Taiwan.*$/i,
      /\s*\|\s*Shopee\s+Brasil.*$/i,
      /\s*\|\s*Shopee.*$/i,
      /\s*-\s*Shopee\s+Việt\s+Nam.*$/i,
      /\s*-\s*Shopee.*$/i,
      /^Mua\s+/i,
      /^Giá\s+tốt\s+/i
    ];

    suffixes.forEach(suffix => {
      name = name.replace(suffix, '').trim();
    });

    name = name.replace(/\s+/g, ' ').trim();
    return name;
  }

  /**
   * Extract the underlying unique Shopee image hash / asset ID from a URL.
   * Strips resize representations (@resize_w82, @resize_w164, @resize_w900, _tn, _xxhdpi, etc.).
   * Examples:
   *   "vn-11134207-7r98o-lk01xyz_tn" -> "vn-11134207-7r98o-lk01xyz"
   *   "https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-lk01xyz@resize_w450_nl" -> "vn-11134207-7r98o-lk01xyz"
   * @param {string} url
   * @returns {string}
   */
  function extractImageHash(url) {
    if (!url || typeof url !== 'string') return '';
    let clean = url.trim();

    // Handle background-image: url("...")
    const bgMatch = clean.match(/^url\(['"]?(.*?)['"]?\)$/i);
    if (bgMatch) {
      clean = bgMatch[1].trim();
    }

    // Remove query params or trailing format extensions
    clean = clean.split('?')[0];

    const SUFFIX_REGEX = /(@resize_[^/]+|(_tn|_xxhdpi|_xhdpi|_hdpi|_mdpi))(\.[a-zA-Z0-9]+)?$/i;

    // Direct hash string
    if (/^[a-zA-Z0-9_-]{16,64}$/.test(clean)) {
      return clean.replace(SUFFIX_REGEX, '');
    }

    try {
      const fullUrl = clean.startsWith('//') ? 'https:' + clean : clean;
      const parsed = new URL(fullUrl);
      const path = parsed.pathname;

      const fileMatch = path.match(/\/file\/([a-zA-Z0-9_-]{16,64})/);
      if (fileMatch) {
        let hash = fileMatch[1];
        hash = hash.replace(SUFFIX_REGEX, '');
        return hash;
      }
    } catch {
      // Not a standard URL
    }

    return '';
  }

  /**
   * Upgrade thumbnail or resized Shopee image URL to clean original/high-resolution URL.
   * Prefers the original plain URL when already present.
   * @param {string} url
   * @returns {string}
   */
  function normalizeImageUrl(url) {
    if (!url || typeof url !== 'string') return '';
    let clean = url.trim();

    const bgMatch = clean.match(/^url\(['"]?(.*?)['"]?\)$/i);
    if (bgMatch) {
      clean = bgMatch[1].trim();
    }

    const hash = extractImageHash(clean);
    if (hash) {
      let cdnHost = 'down-vn.img.susercontent.com';
      try {
        const fullUrl = clean.startsWith('//') ? 'https:' + clean : clean;
        const parsed = new URL(fullUrl);
        if (parsed.hostname.includes('susercontent.com') || parsed.hostname.includes('shopee.')) {
          cdnHost = parsed.hostname;
        }
      } catch {}
      return `https://${cdnHost}/file/${hash}`;
    }

    if (clean.startsWith('//')) {
      clean = 'https:' + clean;
    }

    try {
      const parsed = new URL(clean);
      const isShopeeCdn =
        parsed.hostname.includes('susercontent.com') ||
        parsed.hostname.includes('shopee.vn') ||
        parsed.hostname.includes('shopeemobile.com');

      if (isShopeeCdn) {
        let path = parsed.pathname;
        path = path.replace(/_tn$/i, '')
                   .replace(/_xxhdpi$/i, '')
                   .replace(/_xhdpi$/i, '')
                   .replace(/_hdpi$/i, '')
                   .replace(/_mdpi$/i, '')
                   .replace(/@resize_.*$/i, '');
        return `${parsed.protocol}//${parsed.hostname}${path}`;
      }
      return clean;
    } catch {
      return clean;
    }
  }

  /**
   * Check if image URL looks like a valid product gallery image candidate.
   * @param {string} url
   * @returns {boolean}
   */
  function isGalleryImageUrl(url) {
    if (!url || typeof url !== 'string') return false;
    const trimmed = url.trim();
    if (trimmed.length < 10) return false;

    for (const pattern of EXCLUDED_URL_PATTERNS) {
      if (pattern.test(trimmed)) {
        return false;
      }
    }

    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://') && !trimmed.startsWith('//')) {
      if (/^[a-zA-Z0-9_-]{16,64}$/.test(trimmed)) return true;
      return false;
    }

    const hasCdn =
      trimmed.includes('susercontent.com') ||
      trimmed.includes('cf.shopee.') ||
      trimmed.includes('shopeemobile.com');

    return hasCdn;
  }

  /**
   * Deduplicate candidate image URLs based on unique image hash while preserving gallery order.
   * @param {string[]} rawCandidates
   * @returns {string[]}
   */
  function deduplicateGalleryImages(rawCandidates) {
    if (!Array.isArray(rawCandidates)) return [];

    const seenHashes = new Set();
    const cleanImages = [];

    rawCandidates.forEach(candidate => {
      if (candidate && isGalleryImageUrl(candidate)) {
        const norm = normalizeImageUrl(candidate);
        const hash = extractImageHash(norm) || norm;
        if (!seenHashes.has(hash)) {
          seenHashes.add(hash);
          cleanImages.push(norm);
        }
      }
    });

    return cleanImages;
  }

  /**
   * Parse JSON-LD structured data elements from DOM into a flattened array of entities.
   * Handles single objects, arrays, and nested @graph structures.
   * @param {Document} doc
   * @returns {Array<object>}
   */
  function parseJsonLd(doc) {
    if (!doc || !doc.querySelectorAll) return [];
    const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
    const entities = [];

    function flattenEntity(item) {
      if (!item) return;
      if (Array.isArray(item)) {
        item.forEach(flattenEntity);
      } else if (typeof item === 'object') {
        if (Array.isArray(item['@graph'])) {
          item['@graph'].forEach(flattenEntity);
        } else {
          entities.push(item);
        }
      }
    }

    scripts.forEach(script => {
      try {
        const text = script.textContent ? script.textContent.trim() : '';
        if (!text) return;
        const data = JSON.parse(text);
        flattenEntity(data);
      } catch {
        // Skip malformed JSON
      }
    });

    return entities;
  }

  /**
   * Find the matching Product entity from JSON-LD entities.
   * @param {Array<object>} entities
   * @param {string} targetShopId
   * @param {string} targetItemId
   * @returns {object|null}
   */
  function findProductEntity(entities, targetShopId, targetItemId) {
    if (!Array.isArray(entities)) return null;

    const productEntities = entities.filter(item => {
      const type = item['@type'];
      return type === 'Product' || (Array.isArray(type) && type.includes('Product'));
    });

    if (productEntities.length === 0) return null;
    if (productEntities.length === 1) return productEntities[0];

    // If multiple product entities, match with item ID or shop ID
    if (targetItemId) {
      for (const prod of productEntities) {
        const prodId = String(prod.productID || prod.sku || prod['@id'] || prod.url || '');
        if (prodId.includes(targetItemId)) {
          return prod;
        }
      }
    }

    for (const prod of productEntities) {
      if (prod.image && (Array.isArray(prod.image) ? prod.image.length > 0 : true)) {
        return prod;
      }
    }

    return productEntities[0];
  }

  /**
   * Extract raw image candidates from a Schema.org Product entity.
   * @param {object} product
   * @returns {string[]}
   */
  function extractImagesFromProductEntity(product) {
    if (!product || !product.image) return [];
    const images = [];

    function addImageCandidate(img) {
      if (!img) return;
      if (typeof img === 'string') {
        images.push(img);
      } else if (typeof img === 'object') {
        const u = img.url || img.contentUrl || img['@id'] || '';
        if (typeof u === 'string' && u) {
          images.push(u);
        }
      }
    }

    if (Array.isArray(product.image)) {
      product.image.forEach(addImageCandidate);
    } else {
      addImageCandidate(product.image);
    }

    return images;
  }

  /**
   * Extract candidate images and metadata from Structured Product Data (JSON-LD).
   * @param {Document} doc
   * @param {{shopId: string, itemId: string}} urlInfo
   * @returns {{found: boolean, productName: string, images: string[], rawCandidateCount: number, shopId: string, itemId: string}}
   */
  function extractStructuredProductImages(doc, urlInfo) {
    const emptyResult = {
      found: false,
      productName: '',
      images: [],
      rawCandidateCount: 0,
      shopId: '',
      itemId: ''
    };

    const entities = parseJsonLd(doc);
    const product = findProductEntity(entities, urlInfo?.shopId, urlInfo?.itemId);
    if (!product) return emptyResult;

    const rawCandidates = extractImagesFromProductEntity(product);
    const cleanImages = deduplicateGalleryImages(rawCandidates);

    return {
      found: cleanImages.length > 0,
      productName: cleanProductName(product.name || ''),
      images: cleanImages,
      rawCandidateCount: rawCandidates.length,
      shopId: urlInfo?.shopId || '',
      itemId: urlInfo?.itemId || String(product.productID || product.sku || '')
    };
  }

  /**
   * Layered locator for the Shopee Canonical Main Product Gallery thumbnail carousel container.
   * Verified structure: <div class="Wi_1Rq"> containing <div class="qIctnQ"> items and arrow buttons.
   * Strictly avoids modals, enlarged-image lightboxes, reviews, and recommendations.
   *
   * @param {Document} doc
   * @returns {Element|null}
   */
  function findMainGalleryContainer(doc) {
    if (!doc || typeof doc.querySelector !== 'function') return null;

    function isUnwantedSection(el) {
      if (!el) return true;
      if (el === doc.body || el === doc.documentElement) return true;
      if (el.classList && el.classList.contains && el.classList.contains('page-product')) return true;
      if (el.closest) {
        if (el.closest('.shopee-product-rating, [class*="rating"], [class*="review"], [class*="recommend"], [class*="similar"], [class*="suggestion"], [class*="shop-info"], [class*="seller-profile"], [class*="product-detail"], [role="dialog"], .shopee-modal, [class*="lightbox"], [class*="modal"], [class*="enlarged-image"], [class*="image-viewer"], footer, header')) {
          return true;
        }
      }
      return false;
    }

    // Layer 0: Canonical container inside top product briefing (Highest Confidence)
    const briefing = doc.querySelector('div[class*="product-briefing"], section[class*="product-briefing"]');
    if (briefing && !isUnwantedSection(briefing)) {
      const canonicalInBriefing = briefing.querySelector('.Wi_1Rq, div[class*="Wi_1Rq"], .image-carousel, div[class*="image-carousel"]');
      if (canonicalInBriefing && !isUnwantedSection(canonicalInBriefing)) {
        return canonicalInBriefing;
      }
      const qInBriefing = briefing.querySelector('.qIctnQ, div[class*="qIctnQ"]');
      if (qInBriefing && qInBriefing.parentElement && !isUnwantedSection(qInBriefing.parentElement)) {
        return qInBriefing.parentElement;
      }
    }

    // Layer 1: Confirmed Shopee Gallery Container class Wi_1Rq not in modal/lightbox
    const confirmedContainer = doc.querySelector('.Wi_1Rq, div[class*="Wi_1Rq"]');
    if (confirmedContainer && !isUnwantedSection(confirmedContainer)) {
      return confirmedContainer;
    }

    // Layer 2: Container holding multiple qIctnQ media items
    const qItem = doc.querySelector('.qIctnQ, div[class*="qIctnQ"]');
    if (qItem && !isUnwantedSection(qItem)) {
      const parentContainer = qItem.parentElement;
      if (parentContainer && !isUnwantedSection(parentContainer)) {
        return parentContainer;
      }
      return qItem;
    }

    // Layer 3: Semantic carousel with left/right arrow buttons near top
    const arrowImg = doc.querySelector('img[alt*="arrow right bold" i], img[alt*="arrow right" i]');
    if (arrowImg && !isUnwantedSection(arrowImg)) {
      const btn = arrowImg.closest ? arrowImg.closest('button') : arrowImg.parentElement;
      if (btn && btn.parentElement && !isUnwantedSection(btn.parentElement)) {
        return btn.parentElement;
      }
    }

    // Layer 4: General image-carousel container in main product briefing
    const carouselEl = doc.querySelector('.image-carousel, div[class*="image-carousel"]');
    if (carouselEl && !isUnwantedSection(carouselEl)) {
      return carouselEl;
    }

    return null;
  }

  /**
   * Classify a gallery thumbnail/media element into IMAGE, VIDEO, or UNKNOWN.
   * Detects confirmed Shopee video indicators: img[alt="icon video play"], emXGWZ, <video>, duration labels.
   *
   * @param {Element} itemEl
   * @returns {'IMAGE'|'VIDEO'|'UNKNOWN'}
   */
  function classifyGalleryMediaItem(itemEl) {
    if (!itemEl) return 'UNKNOWN';

    // 1. Confirmed Shopee video play icon: <img alt="icon video play" class="emXGWZ">
    if (itemEl.querySelector) {
      const videoIcon = itemEl.querySelector('img[alt*="video play" i], img[alt*="play" i], [alt*="video play" i], img.emXGWZ, .emXGWZ');
      if (videoIcon) return 'VIDEO';
    }

    // 2. Video elements or video classes
    if (itemEl.tagName && itemEl.tagName.toLowerCase() === 'video') return 'VIDEO';
    if (itemEl.querySelector && itemEl.querySelector('video')) return 'VIDEO';

    const classStr = (itemEl.className || '') + ' ' + (itemEl.getAttribute ? (itemEl.getAttribute('class') || '') : '');
    if (/\b(emXGWZ|video-thumbnail|icon-play|play-button)\b/i.test(classStr)) return 'VIDEO';

    const dataType = itemEl.getAttribute ? (itemEl.getAttribute('data-type') || itemEl.getAttribute('data-media-type') || '') : '';
    if (/video/i.test(dataType)) return 'VIDEO';

    // 3. SVG play icon or duration badge
    if (itemEl.querySelector) {
      const playSvg = itemEl.querySelector('.shopee-svg-icon, [class*="play"], [class*="video"], svg polygon');
      if (playSvg) {
        const svgClass = (playSvg.className || '') + ' ' + (playSvg.parentElement?.className || '');
        if (/play|video/i.test(svgClass)) return 'VIDEO';
      }

      const text = itemEl.textContent || '';
      if (/\b\d{1,2}:\d{2}\b/.test(text) && !/đ|vnd|\$|%/i.test(text)) {
        return 'VIDEO';
      }
    }

    // 4. Check for genuine image structure (picture -> img.P39yUt / img / background-image)
    const hasImg = itemEl.querySelector ? itemEl.querySelector('img') : (itemEl.tagName?.toLowerCase() === 'img');
    const style = (itemEl.getAttribute ? itemEl.getAttribute('style') : itemEl.style) || '';
    const hasBg = typeof style === 'string' && /background(?:-image)?:\s*url/i.test(style);
    const hasDataSrc = itemEl.getAttribute && (itemEl.getAttribute('data-src') || itemEl.getAttribute('data-background-image'));

    if (hasImg || hasBg || hasDataSrc) {
      return 'IMAGE';
    }

    return 'UNKNOWN';
  }

  /**
   * Extract original Shopee image URL candidate from an IMAGE media item.
   * Prefers original plain img.src over resized srcset variants.
   *
   * @param {Element} itemEl
   * @returns {string}
   */
  function extractImageFromMediaItem(itemEl) {
    if (!itemEl) return '';

    const img = (itemEl.tagName && itemEl.tagName.toLowerCase() === 'img') ? itemEl : (itemEl.querySelector ? itemEl.querySelector('picture img, img') : null);
    if (img) {
      const candidateSources = [
        img.getAttribute ? img.getAttribute('src') : null,
        img.src,
        img.getAttribute ? img.getAttribute('data-src') : null,
        img.getAttribute ? img.getAttribute('data-original') : null,
        img.getAttribute ? img.getAttribute('data-lazy-src') : null,
        img.currentSrc,
        img.getAttribute ? img.getAttribute('srcset') : null
      ];

      for (const src of candidateSources) {
        if (src && isGalleryImageUrl(src)) {
          if (src.includes(' ')) {
            const first = src.split(' ')[0];
            if (isGalleryImageUrl(first)) return normalizeImageUrl(first);
          } else {
            return normalizeImageUrl(src);
          }
        }
      }
    }

    const style = (itemEl.getAttribute ? itemEl.getAttribute('style') : itemEl.style) || '';
    const bgMatch = typeof style === 'string' ? style.match(/background(?:-image)?:\s*url\(['"]?(https?:[^\s'")]+|\/\/[^\s'")]+|[a-zA-Z0-9_-]{16,64})/i) : null;
    if (bgMatch && bgMatch[1] && isGalleryImageUrl(bgMatch[1])) {
      return normalizeImageUrl(bgMatch[1]);
    }

    const dataSrc = itemEl.getAttribute ? (itemEl.getAttribute('data-src') || itemEl.getAttribute('data-background-image')) : null;
    if (dataSrc && isGalleryImageUrl(dataSrc)) {
      return normalizeImageUrl(dataSrc);
    }

    return '';
  }

  /**
   * Returns a unique identity key for a media item (canonical image hash for images, or unique video key).
   * @param {'IMAGE'|'VIDEO'|'UNKNOWN'} type
   * @param {string} rawUrl
   * @param {Element} itemEl
   * @returns {string}
   */
  function getMediaIdentity(type, rawUrl, itemEl) {
    if (type === 'IMAGE' && rawUrl) {
      return extractImageHash(rawUrl) || rawUrl;
    }
    if (type === 'VIDEO') {
      const src = itemEl.querySelector ? (itemEl.querySelector('img')?.getAttribute('src') || '') : '';
      const text = (itemEl.textContent || '').trim();
      return 'video:' + (extractImageHash(src) || src || text || 'video_item');
    }
    return rawUrl || (itemEl ? (itemEl.className || itemEl.id || 'unknown_item') : '');
  }

  /**
   * Collect all currently rendered thumbnail/media elements from the gallery container.
   * Verified items: <div class="qIctnQ">
   *
   * @param {Element} container
   * @returns {Array<{element: Element, type: 'IMAGE'|'VIDEO'|'UNKNOWN', rawUrl: string, identity: string}>}
   */
  function getVisibleGalleryItems(container) {
    if (!container) return [];

    let itemElements = [];

    if (typeof container.querySelectorAll === 'function') {
      // 1. Confirmed Shopee media item class qIctnQ
      const qItems = container.querySelectorAll('.qIctnQ, div[class*="qIctnQ"]');
      if (qItems && qItems.length > 0) {
        itemElements = Array.from(qItems);
      } else {
        // Fallback selectors
        const fallbackSelectors = [
          '.image-carousel__item',
          'div[class*="image-carousel__item"]',
          'div[class*="thumbnail"]',
          'picture',
          'img'
        ];
        for (const sel of fallbackSelectors) {
          const found = container.querySelectorAll(sel);
          if (found && found.length > 0) {
            itemElements = Array.from(found);
            break;
          }
        }
      }
    }

    if (itemElements.length === 0) {
      itemElements = [container];
    }

    const results = [];
    itemElements.forEach(el => {
      const type = classifyGalleryMediaItem(el);
      let rawUrl = '';

      if (type === 'IMAGE') {
        rawUrl = extractImageFromMediaItem(el);
      }

      const identity = getMediaIdentity(type, rawUrl, el);

      results.push({
        element: el,
        type: type,
        rawUrl: rawUrl,
        identity: identity
      });
    });

    return results;
  }

  /**
   * Locates the right arrow button in the gallery carousel.
   * Verified: <button class="shopee-icon-button ... mARMpd"><img alt="icon arrow right bold" ...></button>
   *
   * @param {Element} container
   * @returns {Element|null}
   */
  function getCarouselRightButton(container) {
    if (!container || typeof container.querySelector !== 'function') return null;

    const searchScopes = [container, container.parentElement].filter(Boolean);

    for (const scope of searchScopes) {
      if (typeof scope.querySelector !== 'function') continue;

      // 1. By confirmed image alt text: img[alt*="arrow right bold" i], img[alt*="arrow right" i]
      const arrowImg = scope.querySelector('img[alt*="arrow right bold" i], img[alt*="arrow right" i]');
      if (arrowImg) {
        const btn = arrowImg.closest ? arrowImg.closest('button') : (arrowImg.parentElement?.tagName?.toLowerCase() === 'button' ? arrowImg.parentElement : null);
        if (btn) return btn;
      }

      // 2. By confirmed class mARMpd
      const classBtn = scope.querySelector('button.mARMpd, button[class*="mARMpd"]');
      if (classBtn) return classBtn;

      // 3. By icon button not being left button
      const buttons = scope.querySelectorAll ? scope.querySelectorAll('button.shopee-icon-button, button[class*="shopee-icon-button"]') : [];
      if (buttons.length >= 2) {
        return buttons[buttons.length - 1];
      }
    }

    return null;
  }

  /**
   * Locates the left arrow button in the gallery carousel.
   * Verified: <button class="shopee-icon-button ... UTST3I"><img alt="icon arrow left bold" ...></button>
   *
   * @param {Element} container
   * @returns {Element|null}
   */
  function getCarouselLeftButton(container) {
    if (!container || typeof container.querySelector !== 'function') return null;

    const searchScopes = [container, container.parentElement].filter(Boolean);

    for (const scope of searchScopes) {
      if (typeof scope.querySelector !== 'function') continue;

      // 1. By confirmed image alt text: img[alt*="arrow left bold" i], img[alt*="arrow left" i]
      const arrowImg = scope.querySelector('img[alt*="arrow left bold" i], img[alt*="arrow left" i]');
      if (arrowImg) {
        const btn = arrowImg.closest ? arrowImg.closest('button') : (arrowImg.parentElement?.tagName?.toLowerCase() === 'button' ? arrowImg.parentElement : null);
        if (btn) return btn;
      }

      // 2. By confirmed class UTST3I
      const classBtn = scope.querySelector('button.UTST3I, button[class*="UTST3I"]');
      if (classBtn) return classBtn;

      // 3. By first icon button when multiple present
      const buttons = scope.querySelectorAll ? scope.querySelectorAll('button.shopee-icon-button, button[class*="shopee-icon-button"]') : [];
      if (buttons.length >= 2) {
        return buttons[0];
      }
    }

    return null;
  }

  function getCarouselControlState(button) {
    if (!button) return GalleryControlState.MISSING;
    if (button.disabled) return GalleryControlState.INACTIVE;
    if (button.getAttribute && button.getAttribute('aria-disabled') === 'true') {
      return GalleryControlState.INACTIVE;
    }

    const style = (button.getAttribute ? button.getAttribute('style') : button.style) || '';
    if (typeof style === 'string' && (
      style.includes('display: none') || style.includes('visibility: hidden')
    )) {
      return GalleryControlState.INACTIVE;
    }
    return GalleryControlState.ACTIVE;
  }

  function clickCarouselButton(button) {
    if (getCarouselControlState(button) !== GalleryControlState.ACTIVE) return false;
    try {
      if (typeof button.click === 'function') {
        button.click();
        return true;
      }
      if (typeof button.dispatchEvent === 'function' && typeof MouseEvent !== 'undefined') {
        button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        return true;
      }
    } catch {
      return false;
    }
    return false;
  }

  /**
   * Checks if the right arrow button can advance and triggers a click.
   * A false return means only that no click occurred; it is never boundary proof.
   *
   * @param {Element} container
   * @returns {boolean} True if a click was dispatched successfully
   */
  function advanceCarousel(container) {
    return clickCarouselButton(getCarouselRightButton(container));
  }

  function captureGalleryObservation(container) {
    const mediaItems = getVisibleGalleryItems(container);
    return {
      mediaItems: mediaItems,
      mediaIdentities: mediaItems.map(item => `${item.type}:${item.identity}`),
      leftControl: getCarouselControlState(getCarouselLeftButton(container)),
      rightControl: getCarouselControlState(getCarouselRightButton(container))
    };
  }

  /**
   * Waits until a carousel click produces a different ordered media window.
   * Shopee ignores additional arrow clicks while its transition is in flight, so
   * a fixed delay followed by another click can falsely prove a boundary. Polling
   * the canonical media identities (with MutationObserver wake-ups when available)
   * keeps the wait bounded while ensuring the DOM has actually advanced.
   *
   * @param {Element} container
   * @param {object} beforeObservation
   * @param {{advanceTimeoutMs?: number, advancePollIntervalMs?: number, MutationObserver?: Function}} options
   * @returns {Promise<{mediaChanged: boolean, observation: object}>}
   */
  async function waitForGalleryMediaChange(container, beforeObservation, options = {}) {
    const timeoutMs = Number.isFinite(options.advanceTimeoutMs)
      ? Math.max(0, options.advanceTimeoutMs)
      : 500;
    const pollIntervalMs = Number.isFinite(options.advancePollIntervalMs)
      ? Math.max(5, options.advancePollIntervalMs)
      : 20;
    const ObserverCtor = options.MutationObserver || (
      typeof MutationObserver !== 'undefined' ? MutationObserver : null
    );
    const beforeSignature = JSON.stringify(beforeObservation?.mediaIdentities || []);
    const startedAt = Date.now();
    let latestObservation = captureGalleryObservation(container);
    let mutationWake = null;
    let observer = null;

    if (ObserverCtor) {
      try {
        observer = new ObserverCtor(() => {
          if (mutationWake) mutationWake();
        });
        observer.observe(container, {
          subtree: true,
          childList: true,
          attributes: true,
          attributeFilter: [
            'src', 'srcset', 'data-src', 'data-original', 'data-lazy-src',
            'class', 'style', 'disabled', 'aria-disabled'
          ]
        });
      } catch {
        observer = null;
      }
    }

    function waitForPollOrMutation(ms) {
      return new Promise(resolve => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          clearTimeout(timerId);
          if (mutationWake === finish) mutationWake = null;
          resolve();
        };
        const timerId = setTimeout(finish, ms);
        mutationWake = finish;
      });
    }

    try {
      while (true) {
        latestObservation = captureGalleryObservation(container);
        const currentSignature = JSON.stringify(latestObservation.mediaIdentities);
        if (currentSignature !== beforeSignature) {
          return { mediaChanged: true, observation: latestObservation };
        }

        const elapsedMs = Date.now() - startedAt;
        if (elapsedMs >= timeoutMs) break;
        await waitForPollOrMutation(Math.min(pollIntervalMs, timeoutMs - elapsedMs));
      }
    } finally {
      mutationWake = null;
      if (observer) {
        try {
          observer.disconnect();
        } catch {}
      }
    }

    return { mediaChanged: false, observation: latestObservation };
  }

  function createGalleryStabilitySession(options = {}) {
    const settleWindowMs = Number.isFinite(options.settleWindowMs)
      ? Math.max(0, options.settleWindowMs)
      : GALLERY_STABILITY_CONFIG.SETTLE_WINDOW_MS;
    const now = typeof options.now === 'function' ? options.now : () => Date.now();
    const ObserverCtor = options.MutationObserver || (
      typeof MutationObserver !== 'undefined' ? MutationObserver : null
    );
    const expectedProductKey = options.expectedProductKey || '';

    let documentRef = options.documentRef || null;
    let observedContainer = null;
    let observer = null;
    let closed = false;
    let lastSignature = '';
    let lastObservation = null;
    let stableSince = 0;
    let mutationPending = false;
    const waiters = new Set();

    function wakeWaiters(reason) {
      for (const waiter of Array.from(waiters)) {
        waiters.delete(waiter);
        waiter(reason);
      }
    }

    function disconnectObserver() {
      if (observer) {
        try {
          observer.disconnect();
        } catch {}
      }
      observer = null;
    }

    function resetForContainer(container) {
      disconnectObserver();
      observedContainer = container;
      lastSignature = '';
      lastObservation = null;
      stableSince = now();
      mutationPending = false;

      if (!ObserverCtor || !container) return;
      observer = new ObserverCtor(() => {
        if (closed || observedContainer !== container) return;
        mutationPending = true;
        stableSince = now();

        let currentObservation = null;
        try {
          currentObservation = captureGalleryObservation(container);
        } catch {}
        const arrowsChanged = !!(
          currentObservation && lastObservation && (
            currentObservation.leftControl !== lastObservation.leftControl ||
            currentObservation.rightControl !== lastObservation.rightControl
          )
        );
        const mediaCount = currentObservation ? currentObservation.mediaIdentities.length : 0;
        console.log(
          `[GALLERY]\nmutation detected\nmedia=${mediaCount}\narrowsChanged=${arrowsChanged}\nstability reset`
        );
        wakeWaiters('mutation');
      });
      observer.observe(container, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: [
          'src', 'srcset', 'data-src', 'data-original', 'data-lazy-src',
          'class', 'style', 'disabled', 'aria-disabled'
        ]
      });
    }

    function inspect({ container, doc, productKey }) {
      if (closed) {
        return { stable: false, aborted: true, reason: 'SESSION_CLOSED' };
      }
      if (!documentRef) documentRef = doc;
      if (documentRef && doc !== documentRef) {
        return { stable: false, aborted: true, reason: 'DOCUMENT_CHANGED' };
      }
      if (expectedProductKey && productKey !== expectedProductKey) {
        return { stable: false, aborted: true, reason: 'PRODUCT_CHANGED' };
      }
      if (doc && doc.visibilityState && doc.visibilityState !== 'visible') {
        stableSince = now();
        return { stable: false, aborted: false, reason: 'DOCUMENT_HIDDEN' };
      }
      if (observedContainer !== container) resetForContainer(container);

      const observation = captureGalleryObservation(container);
      const signature = JSON.stringify([
        observation.mediaIdentities,
        observation.leftControl,
        observation.rightControl
      ]);
      const changed = mutationPending || signature !== lastSignature;
      if (changed) {
        lastSignature = signature;
        lastObservation = observation;
        stableSince = now();
        mutationPending = false;
      }

      const noArrows = (
        observation.leftControl === GalleryControlState.MISSING &&
        observation.rightControl === GalleryControlState.MISSING
      );
      const stable = (
        noArrows &&
        observation.mediaIdentities.length > 0 &&
        now() - stableSince >= settleWindowMs
      );

      console.log(
        `[GALLERY]\nmedia=${observation.mediaIdentities.length}` +
        `\nleftBoundary=${stable ? GalleryBoundaryState.CONFIRMED : GalleryBoundaryState.UNKNOWN}` +
        `\nrightBoundary=${stable ? GalleryBoundaryState.CONFIRMED : GalleryBoundaryState.UNKNOWN}` +
        `\nstable=${stable}\nquality=${stable ? 'COMPLETE' : 'PARTIAL'}`
      );

      return {
        stable: stable,
        aborted: false,
        reason: stable ? GalleryCompletenessReason.STABLE_SINGLE_PAGE : GalleryCompletenessReason.NOT_COMPLETE,
        observation: observation,
        stableForMs: Math.max(0, now() - stableSince)
      };
    }

    function waitForRelevantChange(timeoutMs) {
      if (closed) return Promise.resolve('closed');
      return new Promise(resolve => {
        let settled = false;
        const finish = reason => {
          if (settled) return;
          settled = true;
          clearTimeout(timerId);
          waiters.delete(finish);
          resolve(reason);
        };
        const timerId = setTimeout(() => finish('timeout'), Math.max(0, timeoutMs));
        waiters.add(finish);
      });
    }

    function disconnect() {
      if (closed) return;
      closed = true;
      disconnectObserver();
      wakeWaiters('disconnected');
      observedContainer = null;
    }

    return {
      inspect,
      waitForRelevantChange,
      disconnect,
      settleWindowMs
    };
  }

  /**
   * Normalizes the gallery carousel by repeatedly moving LEFT until confirmed at the beginning.
   *
   * @param {Element} container
   * @param {{advanceTimeoutMs?: number, advancePollIntervalMs?: number, maxLeftAdvances?: number}} options
   * @returns {Promise<{leftBoundary: string, leftAdvances: number}>}
   */
  async function rewindCarouselToBeginning(container, options = {}) {
    const maxLeftAdvances = options.maxLeftAdvances || 15;

    let leftAdvances = 0;
    let noShiftStreak = 0;
    let leftBoundary = GalleryBoundaryState.UNKNOWN;
    let leftControlObserved = false;

    function getLeftmostId() {
      const items = getVisibleGalleryItems(container);
      return items.length > 0 ? items[0].identity : '';
    }

    let prevFirstId = getLeftmostId();

    while (leftAdvances < maxLeftAdvances) {
      const leftBtn = getCarouselLeftButton(container);
      const leftControl = getCarouselControlState(leftBtn);
      const rightControl = getCarouselControlState(getCarouselRightButton(container));

      if (leftControl === GalleryControlState.MISSING) {
        // Absence alone is not proof. It becomes proof only when the opposite
        // control is observed or an actual left traversal has already occurred.
        if (
          rightControl !== GalleryControlState.MISSING ||
          leftControlObserved ||
          leftAdvances > 0
        ) {
          leftBoundary = GalleryBoundaryState.CONFIRMED;
        }
        break;
      }
      leftControlObserved = true;
      if (leftControl === GalleryControlState.INACTIVE) {
        leftBoundary = GalleryBoundaryState.CONFIRMED;
        break;
      }

      const beforeObservation = captureGalleryObservation(container);
      if (!clickCarouselButton(leftBtn)) break;

      leftAdvances++;

      await waitForGalleryMediaChange(container, beforeObservation, options);

      const currentFirstId = getLeftmostId();
      if (currentFirstId === prevFirstId) {
        noShiftStreak++;
        if (noShiftStreak >= 2) {
          // Two proven control interactions with an unchanged ordered first item
          // confirm the behavioral left boundary; arrow absence is not involved.
          leftBoundary = GalleryBoundaryState.CONFIRMED;
          break;
        }
      } else {
        noShiftStreak = 0;
        prevFirstId = currentFirstId;
      }
    }

    return {
      leftBoundary: leftBoundary,
      leftAdvances: leftAdvances
    };
  }

  /**
   * Enumerates the complete Shopee product gallery by normalizing to beginning (LEFT)
   * and advancing rightward until the end.
   *
   * @param {Element} galleryContainer
   * @param {{advanceTimeoutMs?: number, advancePollIntervalMs?: number, maxAdvances?: number, galleryStabilitySession?: object, documentRef?: Document, productKey?: string}} options
   * @returns {Promise<object>}
   */
  async function enumerateCompleteGallery(galleryContainer, options = {}) {
    const maxAdvances = options.maxAdvances || 15;

    const emptyResult = {
      initialVisibleCount: 0,
      carouselLeftAdvances: 0,
      carouselRightAdvances: 0,
      leftBoundary: GalleryBoundaryState.UNKNOWN,
      rightBoundary: GalleryBoundaryState.UNKNOWN,
      leftmostReached: false,
      rightmostReached: false,
      totalDiscoveredCount: 0,
      imageMediaCount: 0,
      videoMediaCount: 0,
      unknownMediaCount: 0,
      images: [],
      scanQuality: 'FAILED',
      completenessReason: GalleryCompletenessReason.NOT_COMPLETE,
      navigationChanged: false
    };

    if (!galleryContainer) return emptyResult;

    const firstObservation = captureGalleryObservation(galleryContainer);
    const initiallyNoArrows = (
      firstObservation.leftControl === GalleryControlState.MISSING &&
      firstObservation.rightControl === GalleryControlState.MISSING
    );

    // Missing controls are UNKNOWN until a scoped stability session proves that
    // the canonical gallery is a stable single page.
    if (initiallyNoArrows) {
      const session = options.galleryStabilitySession;
      const stability = session ? session.inspect({
        container: galleryContainer,
        doc: options.documentRef || null,
        productKey: options.productKey || ''
      }) : {
        stable: false,
        aborted: false,
        reason: GalleryCompletenessReason.NOT_COMPLETE,
        observation: firstObservation
      };

      const observedItems = stability.observation?.mediaItems || firstObservation.mediaItems;
      const rawImages = [];
      let imageCount = 0;
      let videoCount = 0;
      let unknownCount = 0;
      observedItems.forEach(item => {
        if (item.type === 'IMAGE') {
          imageCount++;
          if (item.rawUrl) rawImages.push(item.rawUrl);
        } else if (item.type === 'VIDEO') {
          videoCount++;
        } else {
          unknownCount++;
        }
      });
      const images = deduplicateGalleryImages(rawImages);
      const isStableSinglePage = stability.stable && images.length > 0;
      const boundary = isStableSinglePage
        ? GalleryBoundaryState.CONFIRMED
        : GalleryBoundaryState.UNKNOWN;

      return {
        initialVisibleCount: observedItems.length,
        carouselLeftAdvances: 0,
        carouselRightAdvances: 0,
        leftBoundary: boundary,
        rightBoundary: boundary,
        leftmostReached: boundary === GalleryBoundaryState.CONFIRMED,
        rightmostReached: boundary === GalleryBoundaryState.CONFIRMED,
        totalDiscoveredCount: observedItems.length,
        imageMediaCount: imageCount,
        videoMediaCount: videoCount,
        unknownMediaCount: unknownCount,
        images: images,
        scanQuality: isStableSinglePage ? 'COMPLETE' : (images.length > 0 ? 'PARTIAL' : 'FAILED'),
        completenessReason: isStableSinglePage
          ? GalleryCompletenessReason.STABLE_SINGLE_PAGE
          : GalleryCompletenessReason.NOT_COMPLETE,
        navigationChanged: !!stability.aborted
      };
    }

    // Step 1: Normalize carousel to the beginning (rewind left)
    const rewindResult = await rewindCarouselToBeginning(galleryContainer, options);
    const leftAdvances = rewindResult.leftAdvances;
    const leftBoundary = rewindResult.leftBoundary;

    // Step 2: Capture initial visible media items at leftmost position
    const initialItems = getVisibleGalleryItems(galleryContainer);
    const initialVisibleCount = initialItems.length;

    const orderedDiscovered = [];
    const seenIdentities = new Set();

    function recordBatch(items) {
      let newCount = 0;
      items.forEach(item => {
        const id = item.identity;
        if (id && !seenIdentities.has(id)) {
          seenIdentities.add(id);
          orderedDiscovered.push(item);
          newCount++;
        }
      });
      return newCount;
    }

    recordBatch(initialItems);

    // Step 3: Advance carousel rightward until end
    let rightAdvances = 0;
    let noNewStreak = 0;
    let rightBoundary = GalleryBoundaryState.UNKNOWN;
    let rightControlObserved = false;
    let navigationChanged = false;

    while (rightAdvances < maxAdvances) {
      const rightBtn = getCarouselRightButton(galleryContainer);
      const rightControl = getCarouselControlState(rightBtn);
      const leftControl = getCarouselControlState(getCarouselLeftButton(galleryContainer));

      if (rightControl === GalleryControlState.MISSING) {
        // Missing right control is proof only after the control system or an
        // actual traversal has been observed. First-observation absence is UNKNOWN.
        if (
          rightControlObserved ||
          (rightAdvances > 0 && leftControl !== GalleryControlState.MISSING)
        ) {
          rightBoundary = GalleryBoundaryState.CONFIRMED;
        }
        break;
      }
      rightControlObserved = true;
      if (rightControl === GalleryControlState.INACTIVE) {
        rightBoundary = GalleryBoundaryState.CONFIRMED;
        break;
      }

      const beforeObservation = captureGalleryObservation(galleryContainer);
      const advanced = clickCarouselButton(rightBtn);
      if (!advanced) break;

      rightAdvances++;

      const advanceResult = await waitForGalleryMediaChange(
        galleryContainer,
        beforeObservation,
        options
      );
      if (advanceResult.mediaChanged) navigationChanged = true;

      const currentItems = advanceResult.observation.mediaItems;
      const newItems = recordBatch(currentItems);

      if (newItems === 0) {
        noNewStreak++;
        if (noNewStreak >= 2) {
          const finalRightControl = getCarouselControlState(getCarouselRightButton(galleryContainer));
          const finalLeftControl = getCarouselControlState(getCarouselLeftButton(galleryContainer));
          if (
            finalRightControl === GalleryControlState.INACTIVE ||
            (
              finalRightControl === GalleryControlState.MISSING &&
              finalLeftControl !== GalleryControlState.MISSING
            )
          ) {
            rightBoundary = GalleryBoundaryState.CONFIRMED;
          } else if (rightControlObserved && navigationChanged) {
            // Two actual right-control interactions with an unchanged ordered
            // media window prove the boundary only after an earlier interaction
            // actually exposed a different media window.
            rightBoundary = GalleryBoundaryState.CONFIRMED;
          }
          break;
        }
      } else {
        noNewStreak = 0;
      }
    }

    // Step 4: Classify and extract images
    let imageMediaCount = 0;
    let videoMediaCount = 0;
    let unknownMediaCount = 0;
    const rawImageUrls = [];

    orderedDiscovered.forEach(item => {
      if (item.type === 'IMAGE') {
        imageMediaCount++;
        if (item.rawUrl) {
          rawImageUrls.push(item.rawUrl);
        }
      } else if (item.type === 'VIDEO') {
        videoMediaCount++;
      } else {
        unknownMediaCount++;
      }
    });

    const finalImages = deduplicateGalleryImages(rawImageUrls);
    const isComplete = (
      leftBoundary === GalleryBoundaryState.CONFIRMED &&
      rightBoundary === GalleryBoundaryState.CONFIRMED &&
      navigationChanged &&
      finalImages.length > 0
    );
    const scanQuality = isComplete ? 'COMPLETE' : (finalImages.length > 0 ? 'PARTIAL' : 'FAILED');
    const completenessReason = isComplete
      ? GalleryCompletenessReason.CAROUSEL_BOUNDS_CONFIRMED
      : GalleryCompletenessReason.NOT_COMPLETE;

    console.log(
      `[GALLERY]\nmedia=${orderedDiscovered.length}` +
      `\nleftBoundary=${leftBoundary}\nrightBoundary=${rightBoundary}` +
      `\nstable=false\nquality=${scanQuality}\nreason=${completenessReason}`
    );

    return {
      initialVisibleCount: initialVisibleCount,
      carouselLeftAdvances: leftAdvances,
      carouselRightAdvances: rightAdvances,
      leftBoundary: leftBoundary,
      rightBoundary: rightBoundary,
      leftmostReached: leftBoundary === GalleryBoundaryState.CONFIRMED,
      rightmostReached: rightBoundary === GalleryBoundaryState.CONFIRMED,
      totalDiscoveredCount: orderedDiscovered.length,
      imageMediaCount: imageMediaCount,
      videoMediaCount: videoMediaCount,
      unknownMediaCount: unknownMediaCount,
      images: finalImages,
      scanQuality: scanQuality,
      completenessReason: completenessReason,
      navigationChanged: navigationChanged
    };
  }

  /**
   * Main Gallery extraction strategy using the button-driven Shopee carousel.
   *
   * @param {Document} doc
   * @param {{advanceTimeoutMs?: number, advancePollIntervalMs?: number, maxAdvances?: number}} options
   * @returns {Promise<{found: boolean, images: string[], initialVisibleCount: number, carouselLeftAdvances: number, carouselRightAdvances: number, leftmostReached: boolean, rightmostReached: boolean, totalDiscoveredCount: number, imageMediaCount: number, videoMediaCount: number, unknownMediaCount: number, scanQuality: 'COMPLETE'|'PARTIAL'|'FAILED'}>}
   */
  async function extractMainGalleryImages(doc, options = {}) {
    const emptyResult = {
      found: false,
      images: [],
      initialVisibleCount: 0,
      carouselLeftAdvances: 0,
      carouselRightAdvances: 0,
      leftBoundary: GalleryBoundaryState.UNKNOWN,
      rightBoundary: GalleryBoundaryState.UNKNOWN,
      leftmostReached: false,
      rightmostReached: false,
      totalDiscoveredCount: 0,
      imageMediaCount: 0,
      videoMediaCount: 0,
      unknownMediaCount: 0,
      scanQuality: 'FAILED',
      completenessReason: GalleryCompletenessReason.NOT_COMPLETE,
      navigationChanged: false
    };

    const container = findMainGalleryContainer(doc);
    if (!container) return emptyResult;

    const enumResult = await enumerateCompleteGallery(container, options);

    return {
      found: enumResult.images.length > 0,
      images: enumResult.images,
      initialVisibleCount: enumResult.initialVisibleCount,
      carouselLeftAdvances: enumResult.carouselLeftAdvances,
      carouselRightAdvances: enumResult.carouselRightAdvances,
      leftBoundary: enumResult.leftBoundary,
      rightBoundary: enumResult.rightBoundary,
      leftmostReached: enumResult.leftmostReached,
      rightmostReached: enumResult.rightmostReached,
      totalDiscoveredCount: enumResult.totalDiscoveredCount,
      imageMediaCount: enumResult.imageMediaCount,
      videoMediaCount: enumResult.videoMediaCount,
      unknownMediaCount: enumResult.unknownMediaCount,
      scanQuality: enumResult.scanQuality,
      completenessReason: enumResult.completenessReason,
      navigationChanged: enumResult.navigationChanged
    };
  }

  /**
   * Evaluates independently extracted candidates from Structured Data and Main Gallery Carousel,
   * selecting Main Gallery Carousel as the preferred authentic source.
   *
   * @param {{found: boolean, images: string[], rawCandidateCount: number}} structuredResult
   * @param {{found: boolean, images: string[], initialVisibleCount: number, carouselLeftAdvances: number, carouselRightAdvances: number, leftmostReached: boolean, rightmostReached: boolean, totalDiscoveredCount: number, imageMediaCount: number, videoMediaCount: number, unknownMediaCount: number, scanQuality: string}} galleryResult
   * @returns {{selectedSource: string, selectedSourceLabel: string, images: string[], structuredCandidates: number, initialGalleryCount: number, carouselLeftAdvances: number, carouselRightAdvances: number, leftmostReached: boolean, rightmostReached: boolean, totalDiscoveredGalleryCount: number, imageMediaCount: number, videoMediaCount: number, unknownMediaCount: number, finalCount: number, scanQuality: string}}
   */
  function chooseBestImageSource(structuredResult, galleryResult) {
    const structImgs = structuredResult?.images || [];
    const galImgs = galleryResult?.images || [];
    const structCount = structImgs.length;
    const galCount = galImgs.length;

    const initialGallery = galleryResult?.initialVisibleCount || galCount;
    const leftAdvances = galleryResult?.carouselLeftAdvances || 0;
    const rightAdvances = galleryResult?.carouselRightAdvances || 0;
    const leftBoundary = galleryResult?.leftBoundary || GalleryBoundaryState.UNKNOWN;
    const rightBoundary = galleryResult?.rightBoundary || GalleryBoundaryState.UNKNOWN;
    const leftmost = leftBoundary === GalleryBoundaryState.CONFIRMED;
    const rightmost = rightBoundary === GalleryBoundaryState.CONFIRMED;
    const totalDiscovered = galleryResult?.totalDiscoveredCount || galCount;
    const imageMedia = galleryResult?.imageMediaCount || galCount;
    const videoMedia = galleryResult?.videoMediaCount || 0;
    const unknownMedia = galleryResult?.unknownMediaCount || 0;
    const completenessReason = galleryResult?.completenessReason || GalleryCompletenessReason.NOT_COMPLETE;
    const hasBoundaryProof = (
      leftBoundary === GalleryBoundaryState.CONFIRMED &&
      rightBoundary === GalleryBoundaryState.CONFIRMED
    );
    const hasValidGalleryProof = hasBoundaryProof && (
      completenessReason === GalleryCompletenessReason.CAROUSEL_BOUNDS_CONFIRMED ||
      completenessReason === GalleryCompletenessReason.STABLE_SINGLE_PAGE
    );
    const scanQuality = (
      galCount > 0 && galleryResult?.scanQuality === 'COMPLETE' && hasValidGalleryProof
    ) ? 'COMPLETE' : (galCount > 0 ? 'PARTIAL' : 'FAILED');

    // Case 1: Main Gallery Carousel has images -> Preferred source
    if (galCount > 0) {
      return {
        selectedSource: 'gallery_carousel',
        selectedSourceLabel: 'Main Gallery Carousel',
        images: galImgs,
        structuredCandidates: structCount,
        initialGalleryCount: initialGallery,
        carouselLeftAdvances: leftAdvances,
        carouselRightAdvances: rightAdvances,
        leftBoundary: leftBoundary,
        rightBoundary: rightBoundary,
        leftmostReached: leftmost,
        rightmostReached: rightmost,
        totalDiscoveredGalleryCount: totalDiscovered,
        imageMediaCount: imageMedia,
        videoMediaCount: videoMedia,
        unknownMediaCount: unknownMedia,
        finalCount: galCount,
        scanQuality: scanQuality,
        completenessReason: scanQuality === 'COMPLETE'
          ? completenessReason
          : GalleryCompletenessReason.NOT_COMPLETE,
        navigationChanged: !!galleryResult?.navigationChanged
      };
    }

    // Case 2: Structured Product Data has multiple images (>= 2 images)
    if (structCount >= 2) {
      return {
        selectedSource: 'structured_data',
        selectedSourceLabel: 'Structured Product Data',
        images: structImgs,
        structuredCandidates: structCount,
        initialGalleryCount: 0,
        carouselLeftAdvances: 0,
        carouselRightAdvances: 0,
        leftBoundary: GalleryBoundaryState.UNKNOWN,
        rightBoundary: GalleryBoundaryState.UNKNOWN,
        leftmostReached: false,
        rightmostReached: false,
        totalDiscoveredGalleryCount: 0,
        imageMediaCount: 0,
        videoMediaCount: 0,
        unknownMediaCount: 0,
        finalCount: structCount,
        scanQuality: 'PARTIAL',
        completenessReason: GalleryCompletenessReason.NOT_COMPLETE,
        navigationChanged: false
      };
    }

    // Case 3: Structured Product Data has exactly 1 image (fallback cover)
    if (structCount === 1) {
      return {
        selectedSource: 'structured_single_fallback',
        selectedSourceLabel: 'Structured Single-Image Fallback',
        images: structImgs,
        structuredCandidates: 1,
        initialGalleryCount: 0,
        carouselLeftAdvances: 0,
        carouselRightAdvances: 0,
        leftBoundary: GalleryBoundaryState.UNKNOWN,
        rightBoundary: GalleryBoundaryState.UNKNOWN,
        leftmostReached: false,
        rightmostReached: false,
        totalDiscoveredGalleryCount: 0,
        imageMediaCount: 0,
        videoMediaCount: 0,
        unknownMediaCount: 0,
        finalCount: 1,
        scanQuality: 'PARTIAL',
        completenessReason: GalleryCompletenessReason.NOT_COMPLETE,
        navigationChanged: false
      };
    }

    // Case 4: Failure (0 images)
    return {
      selectedSource: 'none',
      selectedSourceLabel: 'None',
      images: [],
      structuredCandidates: 0,
      initialGalleryCount: 0,
      carouselLeftAdvances: 0,
      carouselRightAdvances: 0,
      leftBoundary: GalleryBoundaryState.UNKNOWN,
      rightBoundary: GalleryBoundaryState.UNKNOWN,
      leftmostReached: false,
      rightmostReached: false,
      totalDiscoveredGalleryCount: 0,
      imageMediaCount: 0,
      videoMediaCount: 0,
      unknownMediaCount: 0,
      finalCount: 0,
      scanQuality: 'FAILED',
      completenessReason: GalleryCompletenessReason.NOT_COMPLETE,
      navigationChanged: false
    };
  }

  /**
   * Extract product name from available metadata or DOM headers.
   * @param {Document} doc
   * @param {string} structuredName
   * @returns {string}
  /**
   * Check if a candidate product name is a generic Shopee marketplace header/title.
   * @param {string} name
   * @returns {boolean}
   */
  function isGenericProductName(name) {
    if (!name || typeof name !== 'string') return true;
    const trimmed = name.trim().toLowerCase();
    if (trimmed.length < 2) return true;
    if (trimmed === 'shopee' ||
        trimmed.startsWith('shopee việt nam') ||
        trimmed.startsWith('shopee vietnam') ||
        trimmed.startsWith('shopee singapore') ||
        trimmed.startsWith('shopee malaysia') ||
        trimmed.startsWith('shopee thailand') ||
        trimmed.startsWith('shopee philippines') ||
        trimmed.startsWith('shopee indonesia') ||
        trimmed.startsWith('shopee taiwan') ||
        trimmed.startsWith('shopee brasil') ||
        trimmed.startsWith('shopee |') ||
        trimmed.includes('mua và bán trên ứng dụng') ||
        trimmed.includes('online shopping')) {
      return true;
    }
    return false;
  }

  /**
   * Resolves the product name across meta tags, DOM headings, and JSON-LD candidates.
   * Filters out generic marketplace titles and trims market-specific suffixes.
   * @param {Document} doc
   * @param {string} [structuredName]
   * @returns {string}
   */
  function resolveProductName(doc, structuredName) {
    if (structuredName) {
      const cleaned = cleanProductName(structuredName);
      if (!isGenericProductName(cleaned)) return cleaned;
    }
    if (!doc || !doc.querySelector) return '';

    const ogEl = doc.querySelector('meta[property="og:title"]');
    const ogTitle = (ogEl && typeof ogEl.getAttribute === 'function') ? ogEl.getAttribute('content') : (ogEl?.content || '');
    if (ogTitle) {
      const cleaned = cleanProductName(ogTitle);
      if (!isGenericProductName(cleaned)) return cleaned;
    }

    const twEl = doc.querySelector('meta[name="twitter:title"]');
    const twTitle = (twEl && typeof twEl.getAttribute === 'function') ? twEl.getAttribute('content') : (twEl?.content || '');
    if (twTitle) {
      const cleaned = cleanProductName(twTitle);
      if (!isGenericProductName(cleaned)) return cleaned;
    }

    const titleSelectors = [
      'div[class*="product-briefing"] h1',
      'div[class*="product-briefing"] span',
      'h1._44qnta',
      'div.V3eBke',
      'span.G27qlf',
      'div[class*="attM6q"]',
      'h1'
    ];

    for (const sel of titleSelectors) {
      try {
        const el = doc.querySelector(sel);
        if (el && el.textContent && el.textContent.trim().length > 3) {
          const cleaned = cleanProductName(el.textContent.trim());
          if (!isGenericProductName(cleaned)) return cleaned;
        }
      } catch {}
    }

    if (doc.title) {
      const cleaned = cleanProductName(doc.title);
      if (!isGenericProductName(cleaned)) return cleaned;
    }

    return '';
  }

  /**
   * Generates a stable product key based on shop_id and item_id.
   * @param {string} shopId
   * @param {string} itemId
   * @returns {string}
   */
  function createProductKey(shopId, itemId) {
    if (shopId && itemId) return `${shopId}:${itemId}`;
    if (itemId) return `item:${itemId}`;
    return '';
  }

  function hasValidCompletenessProof(data) {
    if (!data || data.extraction_status !== 'COMPLETE') return false;
    if (data.image_source !== 'gallery_carousel') return false;
    if (!Array.isArray(data.images) || data.images.length === 0) return false;

    const reason = data.completeness_reason || data.completenessReason ||
      data.debug?.completeness_reason || GalleryCompletenessReason.NOT_COMPLETE;
    const leftBoundary = data.left_boundary || data.leftBoundary ||
      data.debug?.left_boundary || GalleryBoundaryState.UNKNOWN;
    const rightBoundary = data.right_boundary || data.rightBoundary ||
      data.debug?.right_boundary || GalleryBoundaryState.UNKNOWN;

    const carouselNavigationValid = (
      reason !== GalleryCompletenessReason.CAROUSEL_BOUNDS_CONFIRMED ||
      data.navigation_changed !== false
    );

    return (
      leftBoundary === GalleryBoundaryState.CONFIRMED &&
      rightBoundary === GalleryBoundaryState.CONFIRMED &&
      carouselNavigationValid &&
      (
        reason === GalleryCompletenessReason.CAROUSEL_BOUNDS_CONFIRMED ||
        reason === GalleryCompletenessReason.STABLE_SINGLE_PAGE
      )
    );
  }

  // In-memory Product Level Cache & In-flight scan promises
  const productCache = new Map();
  const activeScanningPromises = new Map();

  const ProductCache = {
    get(productKey) {
      if (!productKey) return null;
      return productCache.get(productKey) || null;
    },
    set(productKey, data) {
      if (!productKey || !data) return false;
      if (data.extraction_status === 'COMPLETE' && !hasValidCompletenessProof(data)) {
        console.warn(`[GALLERY CACHE] rejected COMPLETE without proof for product=${productKey}`);
        return false;
      }
      productCache.set(productKey, data);
      return true;
    },
    hasComplete(productKey) {
      if (!productKey) return false;
      const entry = productCache.get(productKey);
      return hasValidCompletenessProof(entry);
    },
    invalidate(productKey) {
      if (productKey) {
        productCache.delete(productKey);
        activeScanningPromises.delete(productKey);
      } else {
        productCache.clear();
        activeScanningPromises.clear();
      }
    },
    clear() {
      productCache.clear();
      activeScanningPromises.clear();
    }
  };

  /**
   * Main unified extraction pipeline with button-driven carousel enumeration,
   * canonical rewind-to-beginning normalization, transactional product caching,
   * and complete-vs-partial state protection.
   *
   * @param {Document} doc
   * @param {string} url
   * @param {{advanceTimeoutMs?: number, advancePollIntervalMs?: number, maxAdvances?: number, forceRescan?: boolean}} options
   * @returns {Promise<object>} Structured product result
   */
  async function extractProductData(doc, url, options = {}) {
    const urlInfo = parseShopeeUrl(url);
    const initialKey = createProductKey(urlInfo.shopId, urlInfo.itemId);
    const forceRescan = options.forceRescan === true;
    const previousComplete = initialKey && ProductCache.hasComplete(initialKey)
      ? ProductCache.get(initialKey)
      : null;
    const previousImageCount = previousComplete?.images ? previousComplete.images.length : 0;

    // 1. If not forcing a rescan and we already have an authoritative COMPLETE result, return it immediately
    if (!forceRescan && initialKey && ProductCache.hasComplete(initialKey)) {
      return {
        ...previousComplete,
        debug: {
          ...previousComplete.debug,
          full_scan_triggered: false,
          trigger_reason: 'cached',
          scan_state: 'COMPLETE',
          previous_complete_images: previousImageCount,
          cache_replaced: false,
          final_authoritative_images: previousImageCount
        }
      };
    }

    // 2. Concurrency Guard: If a scan is already running for this productKey, await it
    if (initialKey && activeScanningPromises.has(initialKey)) {
      return await activeScanningPromises.get(initialKey);
    }

    // 3. Transactional Full Scan Promise
    const scanPromise = (async () => {
      // Step A: Extract candidates independently from BOTH sources
      const structuredResult = extractStructuredProductImages(doc, urlInfo);
      const galleryResult = await extractMainGalleryImages(doc, options);

      // Step B: Select the most complete and authentic source
      const bestSource = chooseBestImageSource(structuredResult, galleryResult);

      // Step C: Resolve Product Name and IDs
      const productName = resolveProductName(doc, structuredResult.productName);
      const shopId = urlInfo.shopId || structuredResult.shopId || '';
      const itemId = urlInfo.itemId || structuredResult.itemId || '';
      const resolvedKey = createProductKey(shopId, itemId) || initialKey;

      const isShopeePage = urlInfo.isShopee;
      const isSupportedProduct = isShopeePage && (productName.length > 0 || itemId.length > 0 || bestSource.images.length > 0);

      // COMPLETE is proof-driven. Candidate count never promotes a result.
      const hasValidProof = (
        bestSource.selectedSource === 'gallery_carousel' &&
        bestSource.scanQuality === 'COMPLETE' &&
        bestSource.leftBoundary === GalleryBoundaryState.CONFIRMED &&
        bestSource.rightBoundary === GalleryBoundaryState.CONFIRMED &&
        (
          bestSource.completenessReason === GalleryCompletenessReason.CAROUSEL_BOUNDS_CONFIRMED ||
          bestSource.completenessReason === GalleryCompletenessReason.STABLE_SINGLE_PAGE
        )
      );
      const scanQuality = hasValidProof
        ? 'COMPLETE'
        : (bestSource.images.length > 0 ? 'PARTIAL' : (isSupportedProduct ? 'FAILED' : 'IDLE'));
      const isScanComplete = hasValidProof;

      const temporaryScanResult = {
        success: isSupportedProduct,
        is_shopee: isShopeePage,
        is_product_page: isSupportedProduct,
        url: url,
        product_name: productName,
        shop_id: shopId,
        item_id: itemId,
        product_key: resolvedKey,
        images: bestSource.images,
        image_count: bestSource.images.length,
        image_source: bestSource.selectedSource,
        extraction_status: scanQuality,
        left_boundary: bestSource.leftBoundary,
        right_boundary: bestSource.rightBoundary,
        completeness_reason: isScanComplete
          ? bestSource.completenessReason
          : GalleryCompletenessReason.NOT_COMPLETE,
        navigation_changed: !!bestSource.navigationChanged,
        completed_at: Date.now(),
        debug: {
          trigger_reason: forceRescan ? 'manual_rescan' : (resolvedKey ? 'initial' : 'product_changed'),
          previous_complete_images: previousImageCount,
          canonical_gallery_found: galleryResult.found,
          left_boundary: bestSource.leftBoundary,
          right_boundary: bestSource.rightBoundary,
          leftmost_reached: bestSource.leftmostReached,
          rightmost_reached: bestSource.rightmostReached,
          carousel_left_advances: bestSource.carouselLeftAdvances,
          carousel_right_advances: bestSource.carouselRightAdvances,
          total_unique_media: bestSource.totalDiscoveredGalleryCount,
          temporary_scan_status: scanQuality,
          completeness_reason: isScanComplete
            ? bestSource.completenessReason
            : GalleryCompletenessReason.NOT_COMPLETE,
          cache_replaced: isScanComplete,
          final_authoritative_images: isScanComplete ? bestSource.finalCount : (previousImageCount || bestSource.finalCount),
          product_key: resolvedKey || 'N/A',
          scan_state: scanQuality,
          full_scan_triggered: true,
          structured_candidates: bestSource.structuredCandidates,
          initial_visible_gallery_media: bestSource.initialGalleryCount,
          image_media: bestSource.imageMediaCount,
          video_media: bestSource.videoMediaCount,
          unknown_media: bestSource.unknownMediaCount,
          selected_source: bestSource.selectedSource,
          selected_source_label: bestSource.selectedSourceLabel,
          final_images: bestSource.finalCount
        }
      };

      // Step D: Transactional Cache Resolution
      if (isScanComplete) {
        // Successful COMPLETE scan replaces authoritative cache
        if (resolvedKey) {
          ProductCache.set(resolvedKey, temporaryScanResult);
        }
        return temporaryScanResult;
      } else {
        // Temporary scan was PARTIAL or FAILED:
        // If a previous COMPLETE cache exists for this product, preserve it!
        if (resolvedKey && ProductCache.hasComplete(resolvedKey)) {
          const authoritative = ProductCache.get(resolvedKey);
          return {
            ...authoritative,
            debug: {
              ...authoritative.debug,
              trigger_reason: forceRescan ? 'manual_rescan' : 'partial_fallback_prevented',
              previous_complete_images: previousImageCount,
              canonical_gallery_found: galleryResult.found,
              left_boundary: bestSource.leftBoundary,
              right_boundary: bestSource.rightBoundary,
              leftmost_reached: bestSource.leftmostReached,
              rightmost_reached: bestSource.rightmostReached,
              carousel_left_advances: bestSource.carouselLeftAdvances,
              carousel_right_advances: bestSource.carouselRightAdvances,
              total_unique_media: bestSource.totalDiscoveredGalleryCount,
              temporary_scan_status: scanQuality,
              temporary_completeness_reason: GalleryCompletenessReason.NOT_COMPLETE,
              cache_replaced: false,
              final_authoritative_images: authoritative.images.length
            }
          };
        }
        return temporaryScanResult;
      }
    })();

    if (initialKey) {
      activeScanningPromises.set(initialKey, scanPromise);
    }

    try {
      return await scanPromise;
    } finally {
      if (initialKey) {
        activeScanningPromises.delete(initialKey);
      }
    }
  }

  return {
    GalleryBoundaryState,
    GalleryCompletenessReason,
    GALLERY_STABILITY_CONFIG,
    isShopeeDomain,
    parseShopeeUrl,
    cleanProductName,
    extractImageHash,
    normalizeImageUrl,
    isGalleryImageUrl,
    deduplicateGalleryImages,
    parseJsonLd,
    findProductEntity,
    extractImagesFromProductEntity,
    extractStructuredProductImages,
    findMainGalleryContainer,
    classifyGalleryMediaItem,
    extractImageFromMediaItem,
    getMediaIdentity,
    getVisibleGalleryItems,
    getCarouselRightButton,
    getCarouselLeftButton,
    getCarouselControlState,
    captureGalleryObservation,
    createGalleryStabilitySession,
    advanceCarousel,
    rewindCarouselToBeginning,
    enumerateCompleteGallery,
    extractMainGalleryImages,
    chooseBestImageSource,
    resolveProductName,
    isGenericProductName,
    createProductKey,
    hasValidCompletenessProof,
    ProductCache,
    extractProductData
  };
});
