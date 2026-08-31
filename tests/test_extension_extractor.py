"""
Tests for Chrome Extension Manifest V3 Spike (Task 006X).
Validates manifest structure, permissions, JS syntax, confirmed Shopee DOM structure,
button-driven carousel pagination, media item classification (IMAGE vs VIDEO),
and overlapping window deduplication.
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
    assert "debug-struct-count" in content
    assert "debug-initial-visible" in content
    assert "debug-carousel-advances" in content
    assert "debug-total-discovered" in content
    assert "debug-image-media" in content
    assert "debug-video-media" in content
    assert "debug-source-label" in content
    assert "debug-final-count" in content
    assert "btn-copy" in content
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
        if (sel.includes('video') || sel.includes('play')) return null;
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
    assert res["carouselAdvances"] >= 2
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


def test_acceptance_case_9_images_plus_1_video_button_carousel():
    """
    Verify complete acceptance scenario:
    - 9 actual product images + 1 video in Shopee carousel (Wi_1Rq / qIctnQ)
    - Initially visible: 5 thumbnails (1 video + 4 images)
    - Carousel advances 3 times, discovering remaining 5 images
    - Total discovered: 10
    - Image media: 9, Video media: 1
    - Final images: 9
    - Source: Main Gallery Carousel
    """
    js_code = """
    let step = 0;
    // Step 0: [Video_1, Prod_1, Prod_2, Prod_3, Prod_4]
    // Step 1: [Prod_2, Prod_3, Prod_4, Prod_5, Prod_6]
    // Step 2: [Prod_4, Prod_5, Prod_6, Prod_7, Prod_8]
    // Step 3: [Prod_6, Prod_7, Prod_8, Prod_9, Prod_9]
    const windowFrames = [
      [ { type: 'v', id: 'vid_1' }, { type: 'i', id: 'p1' }, { type: 'i', id: 'p2' }, { type: 'i', id: 'p3' }, { type: 'i', id: 'p4' } ],
      [ { type: 'i', id: 'p2' }, { type: 'i', id: 'p3' }, { type: 'i', id: 'p4' }, { type: 'i', id: 'p5' }, { type: 'i', id: 'p6' } ],
      [ { type: 'i', id: 'p4' }, { type: 'i', id: 'p5' }, { type: 'i', id: 'p6' }, { type: 'i', id: 'p7' }, { type: 'i', id: 'p8' } ],
      [ { type: 'i', id: 'p6' }, { type: 'i', id: 'p7' }, { type: 'i', id: 'p8' }, { type: 'i', id: 'p9' }, { type: 'i', id: 'p9' } ]
    ];

    const mockDoc = {
      querySelectorAll: (sel) => {
        if (sel.includes('application/ld+json')) {
          return [{
            textContent: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Product",
              "name": "Áo Khoác Nam Thể Thao Cao Cấp | Shopee Việt Nam",
              "productID": "123456789",
              "image": "https://down-vn.img.susercontent.com/file/vn-11134207-single-cover"
            })
          }];
        }
        return [];
      },
      querySelector: (sel) => {
        if (sel.includes('Wi_1Rq') || sel.includes('qIctnQ')) {
          return {
            className: 'Wi_1Rq',
            querySelectorAll: (qSel) => {
              if (qSel.includes('qIctnQ')) {
                const currentFrame = windowFrames[Math.min(step, windowFrames.length - 1)];
                return currentFrame.map(item => {
                  if (item.type === 'v') {
                    return {
                      tagName: 'div',
                      className: 'qIctnQ',
                      querySelector: (s) => {
                        if (s.includes('video play') || s.includes('play') || s.includes('emXGWZ')) {
                          return {
                            tagName: 'img',
                            className: 'emXGWZ',
                            getAttribute: (a) => a === 'alt' ? 'icon video play' : null
                          };
                        }
                        return null;
                      },
                      getAttribute: () => null,
                      textContent: '0:30'
                    };
                  } else {
                    return {
                      tagName: 'div',
                      className: 'qIctnQ',
                      querySelector: (s) => {
                        if (s.includes('play')) return null;
                        if (s.includes('img') || s.includes('picture')) {
                          return {
                            getAttribute: (a) => a === 'src' ? `https://down-vn.img.susercontent.com/file/vn-11134207-${item.id}` : null
                          };
                        }
                        return null;
                      },
                      getAttribute: () => null,
                      textContent: ''
                    };
                  }
                });
              }
              return [];
            },
            querySelector: (bSel) => {
              if (bSel.includes('arrow right') || bSel.includes('mARMpd')) {
                return {
                  disabled: false,
                  click: () => { step++; }
                };
              }
              return null;
            }
          };
        }
        if (sel.includes('product-briefing') || sel === 'h1') {
          return { textContent: 'Áo Khoác Nam Thể Thao Cao Cấp - Shopee Việt Nam' };
        }
        return null;
      },
      title: "Shopee"
    };

    const res = await core.extractProductData(mockDoc, 'https://shopee.vn/ao-khoac-i.8888.123456789', { advanceDelayMs: 5 });
    console.log(JSON.stringify(res));
    """
    res = run_node_code(js_code)

    assert res["success"] is True
    assert res["product_name"] == "Áo Khoác Nam Thể Thao Cao Cấp"
    assert res["shop_id"] == "8888"
    assert res["item_id"] == "123456789"
    assert res["image_source"] == "gallery_carousel"
    assert res["image_count"] == 9
    assert len(res["images"]) == 9

    debug = res["debug"]
    assert debug["structured_candidates"] == 1
    assert debug["initial_visible_gallery_media"] == 5
    assert debug["carousel_advances"] >= 3
    assert debug["total_unique_gallery_media"] == 10
    assert debug["image_media"] == 9
    assert debug["video_media"] == 1
    assert debug["selected_source"] == "gallery_carousel"
    assert debug["final_images"] == 9
