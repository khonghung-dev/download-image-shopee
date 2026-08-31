"""
Tests for Chrome Extension Manifest V3 Spike (Task 006X).
Validates manifest structure, permissions, JS syntax, confirmed Shopee DOM structure,
button-driven carousel pagination, rewind-to-left normalization, media classification (IMAGE vs VIDEO),
and transactional rescan state management.
"""

import json
from pathlib import Path
import re
import subprocess
import pytest

EXTENSION_DIR = Path(__file__).resolve().parent.parent / "chrome_extension"


def run_node_code(js_code: str) -> dict:
    """Helper to run an async Node.js test script importing extractor_core.js and returning parsed JSON."""
    wrapped_code = f"""
    const core = require({json.dumps(str(EXTENSION_DIR / 'extractor_core.js'))});
    (async () => {{
      {js_code}
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """
    result = subprocess.run(
        ["node", "-e", wrapped_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    return json.loads(result.stdout.strip())


def test_manifest_structure_and_mv3_compliance():
    """Verify manifest.json exists, uses MV3, and has correct minimal permissions."""
    manifest_path = EXTENSION_DIR / "manifest.json"
    assert manifest_path.exists(), "manifest.json must exist in chrome_extension/"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # MV3 Checks
    assert manifest.get("manifest_version") == 3
    assert manifest.get("name") == "Shopee Product Extractor"
    assert "version" in manifest
    assert "description" in manifest

    # Action popup check
    action = manifest.get("action", {})
    assert action.get("default_popup") == "popup.html"

    # Permission checks (Must be minimal)
    permissions = manifest.get("permissions", [])
    assert "activeTab" in permissions
    assert "scripting" in permissions

    # Strictly forbidden permissions
    forbidden = ["<all_urls>", "debugger", "cookies", "history", "management", "nativeMessaging"]
    for perm in forbidden:
        assert perm not in permissions, f"Forbidden permission '{perm}' must not be in permissions"

    # Host permissions check
    host_permissions = manifest.get("host_permissions", [])
    assert len(host_permissions) > 0
    for host in host_permissions:
        assert "shopee" in host, f"Host permission '{host}' must be scoped to Shopee"

    # Content scripts check
    content_scripts = manifest.get("content_scripts", [])
    assert len(content_scripts) >= 1
    js_files = content_scripts[0].get("js", [])
    assert "extractor_core.js" in js_files
    assert "content.js" in js_files


def test_extension_files_exist():
    """Ensure all required extension files exist."""
    required_files = [
        "manifest.json",
        "popup.html",
        "popup.js",
        "content.js",
        "extractor_core.js",
        "README.md",
    ]
    for filename in required_files:
        filepath = EXTENSION_DIR / filename
        assert filepath.exists(), f"File {filename} is missing in chrome_extension/"
        assert filepath.stat().st_size > 0, f"File {filename} is empty"


def test_popup_html_contains_required_elements():
    """Ensure popup.html contains the expected user interface elements."""
    popup_path = EXTENSION_DIR / "popup.html"
    content = popup_path.read_text(encoding="utf-8")

    # Header / Title
    assert "Shopee Product Extractor" in content
    # Required Vietnamese error messages
    assert "Đây không phải trang sản phẩm Shopee." in content
    assert "Không thể xác định chính xác bộ ảnh sản phẩm." in content
    # Results fields & debug boxes
    assert "res-product-name" in content
    assert "res-shop-id" in content
    assert "res-item-id" in content
    assert "res-image-count" in content
    assert "debug-product-key" in content
    assert "debug-trigger-reason" in content
    assert "debug-prev-complete" in content
    assert "debug-canonical-found" in content
    assert "debug-leftmost-reached" in content
    assert "debug-rightmost-reached" in content
    assert "debug-left-advances" in content
    assert "debug-right-advances" in content
    assert "debug-total-discovered" in content
    assert "debug-temp-status" in content
    assert "debug-cache-replaced" in content
    assert "debug-source-label" in content
    assert "debug-final-count" in content
    assert "btn-copy" in content
    assert "btn-rescan" in content
    assert "Quét lại" in content
    assert "extractor_core.js" in content
    assert "popup.js" in content


def test_js_syntax_basic_checks():
    """Verify JavaScript files do not contain obvious syntax anomalies or prohibited APIs."""
    js_files = ["extractor_core.js", "content.js", "popup.js"]

    for js_file in js_files:
        path = EXTENSION_DIR / js_file
        code = path.read_text(encoding="utf-8")

        assert "Profile 10" not in code
        assert "playwright" not in code.lower()
        assert "puppeteer" not in code.lower()
        assert "selenium" not in code.lower()

        open_braces = code.count("{")
        close_braces = code.count("}")
        assert open_braces == close_braces, f"Mismatched braces in {js_file}: {open_braces} != {close_braces}"


def test_url_extraction_regex_logic():
    """Test URL parsing regex patterns matching extractor_core.js logic."""
    test_urls = [
        ("https://shopee.vn/Áo-Thun-Nam-Cổ-Tròn-i.12345678.987654321", "12345678", "987654321"),
        ("https://shopee.vn/product/111222333/444555666", "111222333", "444555666"),
        ("https://shopee.vn/product-name-i.55555.66666?sp_atk=123", "55555", "66666"),
        ("https://shopee.vn/sp?shopid=77777&itemid=88888", "77777", "88888"),
    ]

    for url, expected_shop, expected_item in test_urls:
        # Pattern 1: -i.<shop_id>.<item_id>
        i_match = re.search(r"-i\.(\d+)\.(\d+)", url)
        if i_match:
            assert i_match.group(1) == expected_shop
            assert i_match.group(2) == expected_item
            continue

        # Pattern 2: /product/<shop_id>/<item_id>
        prod_match = re.search(r"/product/(\d+)/(\d+)", url)
        if prod_match:
            assert prod_match.group(1) == expected_shop
            assert prod_match.group(2) == expected_item
            continue

        # Pattern 3: query params
        q_shop = re.search(r"[?&]shopid=(\d+)", url)
        q_item = re.search(r"[?&]itemid=(\d+)", url)
        if q_shop and q_item:
            assert q_shop.group(1) == expected_shop
            assert q_item.group(1) == expected_item
            continue

        pytest.fail(f"URL did not match any expected pattern: {url}")


def test_title_cleaning_rules():
    """Verify title cleaning rules strip suffixes properly."""
    raw_titles = [
        ("Áo Thun Nam Cotton Cao Cấp | Shopee Việt Nam", "Áo Thun Nam Cotton Cao Cấp"),
        ("Giày Thể Thao Nữ Chạy Bộ - Shopee Singapore", "Giày Thể Thao Nữ Chạy Bộ"),
        ("Túi Xách Da Thời Trang | Shopee", "Túi Xách Da Thời Trang"),
        ("Mua Balo Học Sinh Giá Tốt", "Balo Học Sinh Giá Tốt"),
    ]
    suffixes = [
        r"\s*\|\s*Shopee\s+Việt\s+Nam.*$",
        r"\s*\|\s*Shopee\s+Singapore.*$",
        r"\s*\|\s*Shopee.*$",
        r"\s*-\s*Shopee\s+Việt\s+Nam.*$",
        r"\s*-\s*Shopee.*$",
        r"^Mua\s+",
    ]
    for raw, expected in raw_titles:
        cleaned = raw.strip()
        for pat in suffixes:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
        assert cleaned == expected


def test_confirmed_shopee_media_item_classification():
    """
    Verify classification on confirmed Shopee DOM structures:
    - Normal image item: <div class="qIctnQ"><div class="mdCA_C"><picture><img src="..."></picture></div></div> -> IMAGE
    - Video item: <div class="qIctnQ"><div class="mdCA_C"><img alt="icon video play" class="emXGWZ">...</div></div> -> VIDEO
    """
    js_code = """
    const normalImageItem = {
      tagName: 'div',
      className: 'qIctnQ',
      querySelector: (sel) => {
        if (sel.includes('video') || sel.includes('play') || sel.includes('emXGWZ')) return null;
        if (sel.includes('img') || sel.includes('picture')) {
          return {
            getAttribute: (a) => a === 'src' ? 'https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-lk01xyz' : null,
            src: 'https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-lk01xyz'
          };
        }
        return null;
      },
      getAttribute: () => null,
      textContent: ''
    };

    const confirmedVideoItem = {
      tagName: 'div',
      className: 'qIctnQ',
      querySelector: (sel) => {
        if (sel.includes('video play') || sel.includes('play') || sel.includes('emXGWZ')) {
          return {
            tagName: 'img',
            className: 'emXGWZ',
            getAttribute: (a) => a === 'alt' ? 'icon video play' : null
          };
        }
        if (sel.includes('img')) {
          return {
            getAttribute: (a) => a === 'src' ? 'https://down-vn.img.susercontent.com/file/vn-11134207-video-poster' : null
          };
        }
        return null;
      },
      getAttribute: () => null,
      textContent: ''
    };

    const c1 = core.classifyGalleryMediaItem(normalImageItem);
    const c2 = core.classifyGalleryMediaItem(confirmedVideoItem);
    const url1 = core.extractImageFromMediaItem(normalImageItem);
    const url2 = core.extractImageFromMediaItem(confirmedVideoItem);

    console.log(JSON.stringify({ c1, c2, url1, url2 }));
    """
    res = run_node_code(js_code)
    assert res["c1"] == "IMAGE"
    assert res["c2"] == "VIDEO"
    assert res["url1"] == "https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-lk01xyz"


def test_resize_variants_collapse_to_same_media_identity():
    """Verify that multiple resize variants (@resize_w82_nl, @resize_w164_nl, @resize_w900_nl, _tn) yield same identity."""
    js_code = """
    const variants = [
      'https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-abc12345@resize_w82_nl.webp',
      'https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-abc12345@resize_w164_nl.webp',
      'https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-abc12345@resize_w900_nl.webp',
      'https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-abc12345_tn',
      'https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-abc12345'
    ];

    const identities = variants.map(v => core.getMediaIdentity('IMAGE', v, null));
    const normalized = variants.map(v => core.normalizeImageUrl(v));
    const deduped = core.deduplicateGalleryImages(variants);

    console.log(JSON.stringify({ identities, normalized, deduped }));
    """
    res = run_node_code(js_code)
    assert all(id_val == "vn-11134207-7r98o-abc12345" for id_val in res["identities"])
    assert len(res["deduped"]) == 1
    assert res["deduped"][0] == "https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-abc12345"


def test_overlapping_windows_carousel_enumeration():
    """
    Simulate Shopee carousel advancing overlapping windows:
    - Step 0: [A, B, C, D, E]
    - Step 1: [B, C, D, E, F]
    - Step 2: [C, D, E, F, G]
    - Step 3: [D, E, F, G, G] (no new items) -> terminates
    Verifies result is ordered: A, B, C, D, E, F, G.
    """
    js_code = """
    let step = 0;
    const windowMap = [
      ['img_A', 'img_B', 'img_C', 'img_D', 'img_E'],
      ['img_B', 'img_C', 'img_D', 'img_E', 'img_F'],
      ['img_C', 'img_D', 'img_E', 'img_F', 'img_G'],
      ['img_D', 'img_E', 'img_F', 'img_G', 'img_G']
    ];

    const container = {
      className: 'Wi_1Rq',
      querySelectorAll: (sel) => {
        if (sel.includes('qIctnQ') || sel.includes('item')) {
          const currentKeys = windowMap[Math.min(step, windowMap.length - 1)];
          return currentKeys.map(k => ({
            tagName: 'div',
            className: 'qIctnQ',
            querySelector: (s) => {
              if (s.includes('play') || s.includes('video') || s.includes('emXGWZ')) return null;
              if (s.includes('img') || s.includes('picture')) {
                return {
                  getAttribute: (a) => a === 'src' ? `https://down-vn.img.susercontent.com/file/vn-11134207-${k}` : null
                };
              }
              return null;
            },
            getAttribute: () => null
          }));
        }
        return [];
      },
      querySelector: (sel) => {
        if (sel.includes('arrow right') || sel.includes('mARMpd')) {
          return {
            disabled: false,
            click: () => { step++; }
          };
        }
        return null;
      }
    };

    const enumResult = await core.enumerateCompleteGallery(container, { advanceDelayMs: 5, maxAdvances: 10 });
    console.log(JSON.stringify(enumResult));
    """
    res = run_node_code(js_code)
    assert res["initialVisibleCount"] == 5
    assert res["carouselRightAdvances"] >= 2
    assert res["totalDiscoveredCount"] == 7
    assert len(res["images"]) == 7
    assert res["images"] == [
        "https://down-vn.img.susercontent.com/file/vn-11134207-img_A",
        "https://down-vn.img.susercontent.com/file/vn-11134207-img_B",
        "https://down-vn.img.susercontent.com/file/vn-11134207-img_C",
        "https://down-vn.img.susercontent.com/file/vn-11134207-img_D",
        "https://down-vn.img.susercontent.com/file/vn-11134207-img_E",
        "https://down-vn.img.susercontent.com/file/vn-11134207-img_F",
        "https://down-vn.img.susercontent.com/file/vn-11134207-img_G"
    ]


def test_transactional_rescan_rewind_normalization_and_failure_protection():
    """
    Regression Tests for Manual Rescan:
    1. Product A has previous COMPLETE result (9 images).
    2. Carousel is currently scrolled to the middle/end (showing only items 5-9 in DOM).
    3. Manual rescan rewinds carousel to the leftmost beginning, traverses full gallery, and successfully updates COMPLETE result (9 images).
    4. Second rescan where carousel fails to traverse or only gets partial 5 images -> temporary scan is PARTIAL -> previous COMPLETE result (9 images) is preserved!
    """
    js_code = """
    core.ProductCache.clear();

    // 1. Setup previous COMPLETE result for Product A (9 images)
    const productA_initial = {
      product_name: "Áo Thun Nam Cao Cấp",
      shop_id: "100",
      item_id: "200",
      product_key: "100:200",
      images: [1, 2, 3, 4, 5, 6, 7, 8, 9].map(i => `https://down-vn.img.susercontent.com/file/vn-prod-${i}`),
      image_count: 9,
      image_source: "gallery_carousel",
      extraction_status: "COMPLETE",
      completed_at: Date.now() - 1000,
      debug: {
        product_key: "100:200",
        scan_state: "COMPLETE",
        final_images: 9
      }
    };
    core.ProductCache.set("100:200", productA_initial);

    // 2. Mock Shopee DOM currently positioned at index 2 (showing items 5, 6, 7, 8, 9)
    let carouselPos = 2;
    const allFrames = [
      [1, 2, 3, 4, 5],
      [3, 4, 5, 6, 7],
      [5, 6, 7, 8, 9]
    ];

    const mockDoc = {
      querySelectorAll: () => [],
      querySelector: (sel) => {
        if (sel.includes('product-briefing') || sel.includes('Wi_1Rq') || sel.includes('qIctnQ')) {
          return {
            className: 'Wi_1Rq',
            querySelectorAll: (qSel) => {
              const currentFrame = allFrames[carouselPos];
              return currentFrame.map(idx => ({
                tagName: 'div',
                className: 'qIctnQ',
                querySelector: (s) => {
                  if (s.includes('play') || s.includes('video') || s.includes('emXGWZ')) return null;
                  if (s.includes('img') || s.includes('picture')) {
                    return { getAttribute: (a) => a === 'src' ? `https://down-vn.img.susercontent.com/file/vn-prod-${idx}` : null };
                  }
                  return null;
                },
                getAttribute: () => null
              }));
            },
            querySelector: (bSel) => {
              if (bSel.includes('arrow left') || bSel.includes('UTST3I')) {
                return {
                  disabled: carouselPos === 0,
                  click: () => { if (carouselPos > 0) carouselPos--; }
                };
              }
              if (bSel.includes('arrow right') || bSel.includes('mARMpd')) {
                return {
                  disabled: carouselPos >= allFrames.length - 1,
                  click: () => { if (carouselPos < allFrames.length - 1) carouselPos++; }
                };
              }
              return null;
            }
          };
        }
        if (sel === 'h1' || sel.includes('title')) {
          return { textContent: 'Áo Thun Nam Cao Cấp - Shopee' };
        }
        return null;
      },
      title: "Shopee"
    };

    // Scenario A: Manual rescan from position 2 -> rewinds to 0 -> enumerates all 9 -> COMPLETE (cache replaced)
    const resA_successfulRescan = await core.extractProductData(mockDoc, 'https://shopee.vn/ao-thun-i.100.200', { forceRescan: true, advanceDelayMs: 5 });

    // Scenario B: Broken / Partial Rescan simulation (gallery arrow is blocked, only discovers 5 items)
    const mockDocBroken = {
      querySelectorAll: () => [],
      querySelector: (sel) => {
        if (sel.includes('Wi_1Rq')) {
          return {
            className: 'Wi_1Rq',
            querySelectorAll: () => [1, 2, 3, 4, 5].map(idx => ({
              tagName: 'div',
              className: 'qIctnQ',
              querySelector: (s) => {
                if (s.includes('play')) return null;
                return { getAttribute: (a) => a === 'src' ? `https://down-vn.img.susercontent.com/file/vn-prod-${idx}` : null };
              },
              getAttribute: () => null
            })),
            querySelector: (bSel) => null // No advance arrows found -> scan will only see 5
          };
        }
        return null;
      },
      title: "Shopee"
    };

    // Scenario B should NOT replace the authoritative 9-image cache!
    const resB_partialRescan = await core.extractProductData(mockDocBroken, 'https://shopee.vn/ao-thun-i.100.200', { forceRescan: true, advanceDelayMs: 5 });

    console.log(JSON.stringify({
      resA_successfulRescan,
      resB_partialRescan
    }));
    """
    res = run_node_code(js_code)

    # Verify Scenario A (Full Rescan with Rewind)
    res_a = res["resA_successfulRescan"]
    assert res_a["image_count"] == 9
    assert res_a["debug"]["trigger_reason"] == "manual_rescan"
    assert res_a["debug"]["leftmost_reached"] is True
    assert res_a["debug"]["rightmost_reached"] is True
    assert res_a["debug"]["carousel_left_advances"] >= 2
    assert res_a["debug"]["carousel_right_advances"] >= 2
    assert res_a["debug"]["temporary_scan_status"] == "COMPLETE"
    assert res_a["debug"]["cache_replaced"] is True
    assert res_a["debug"]["final_authoritative_images"] == 9

    # Verify Scenario B (Partial Rescan protected)
    res_b = res["resB_partialRescan"]
    assert res_b["image_count"] == 9  # Previous complete result preserved!
    assert res_b["debug"]["cache_replaced"] is False
    assert res_b["debug"]["final_authoritative_images"] == 9


def test_enlarged_image_modal_does_not_intercept_canonical_gallery():
    """
    Verify that if an enlarged image viewer / modal is present in DOM,
    the canonical product briefing gallery container is still preferred.
    """
    js_code = """
    const docWithModal = {
      querySelectorAll: () => [],
      querySelector: (sel) => {
        // Briefing contains the canonical gallery
        if (sel.includes('product-briefing')) {
          return {
            querySelector: (cSel) => {
              if (cSel.includes('Wi_1Rq')) {
                return {
                  className: 'Wi_1Rq',
                  closest: (cls) => cls.includes('modal') || cls.includes('dialog') ? null : null,
                  querySelectorAll: () => [1, 2, 3, 4, 5, 6, 7, 8, 9].map(i => ({
                    tagName: 'div',
                    className: 'qIctnQ',
                    querySelector: (s) => s.includes('img') ? { getAttribute: (a) => a === 'src' ? `https://down-vn.img.susercontent.com/file/vn-canonical-${i}` : null } : null,
                    getAttribute: () => null
                  })),
                  querySelector: () => null
                };
              }
              return null;
            }
          };
        }
        return null;
      },
      title: "Shopee Product"
    };

    const container = core.findMainGalleryContainer(docWithModal);
    const items = core.getVisibleGalleryItems(container);
    console.log(JSON.stringify({ found: !!container, itemCount: items.length }));
    """
    res = run_node_code(js_code)
    assert res["found"] is True
    assert res["itemCount"] == 9
