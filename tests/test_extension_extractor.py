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
    json_lines = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("{")]
    assert json_lines, f"Node test did not emit a JSON result. stdout={result.stdout!r}"
    return json.loads(json_lines[-1])


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
    forbidden = ["<all_urls>", "debugger", "cookies", "history", "management"]
    for perm in forbidden:
        assert perm not in permissions, f"Forbidden permission '{perm}' must not be in permissions"

    assert "nativeMessaging" in permissions, "Manifest must include 'nativeMessaging' permission"

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

    # Background service worker check
    background = manifest.get("background", {})
    assert background.get("service_worker") == "background.js"


def test_extension_files_exist():
    """Ensure all required extension files exist."""
    required_files = [
        "manifest.json",
        "popup.html",
        "popup.js",
        "content.js",
        "background.js",
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
    # Bridge elements & explicit onboarding connect button
    assert "bridge-status-indicator" in content
    assert "btn-connect-bridge" in content
    assert "Kết nối ứng dụng" in content
    assert "btn-send-desktop" in content
    assert "Gửi sang ứng dụng" in content
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
    """Verify basic JS syntax of content.js, popup.js, and background.js."""
    for script in ["content.js", "popup.js", "background.js"]:
        script_path = EXTENSION_DIR / script
        assert script_path.exists()
        result = subprocess.run(
            ["node", "--check", str(script_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"JS syntax error in {script}: {result.stderr}"

    """Verify JavaScript files do not contain obvious syntax anomalies or prohibited APIs."""
    js_files = ["extractor_core.js", "content.js", "popup.js", "background.js"]

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


def test_background_js_structure_and_constants():
    """Verify background.js exists, contains Native Host name, version 1, and user-initiated messaging."""
    bg_path = EXTENSION_DIR / "background.js"
    assert bg_path.exists()
    content = bg_path.read_text(encoding="utf-8")

    assert "com.shopee_image_downloader.bridge" in content
    assert "connectNative" in content
    assert "PROTOCOL_VERSION = 1" in content
    assert "GET_BRIDGE_STATUS" in content
    assert "CONNECT_DESKTOP" in content
    assert "SEND_PRODUCT_TO_DESKTOP" in content
    assert "DISCONNECTED" in content
    assert "CONNECTING" in content
    assert "CONNECTED" in content
    assert "product_result" in content


def test_background_js_runtime_state_machine():
    """Verify background.js state machine, native messaging lifecycle, and zero auto-reconnect behavior."""
    bg_path = EXTENSION_DIR / "background.js"
    js_test = f"""
    const fs = require('fs');
    let messageListener = null;
    let broadcastHistory = [];
    let nativeConnectCount = 0;
    let activePorts = [];

    // Mock Native Port
    class MockNativePort {{
      constructor(name) {{
        nativeConnectCount++;
        this.name = name;
        this.sentMessages = [];
        this.messageListeners = [];
        this.disconnectListeners = [];
        this.onMessage = {{
          addListener: (fn) => this.messageListeners.push(fn),
          removeListener: (fn) => {{
            this.messageListeners = this.messageListeners.filter(l => l !== fn);
          }}
        }};
        this.onDisconnect = {{
          addListener: (fn) => this.disconnectListeners.push(fn),
          removeListener: (fn) => {{
            this.disconnectListeners = this.disconnectListeners.filter(l => l !== fn);
          }}
        }};
        activePorts.push(this);
      }}
      postMessage(data) {{
        this.sentMessages.push(data);
      }}
      disconnect() {{
        for (const fn of this.disconnectListeners) fn();
      }}
      simulateMessage(data) {{
        for (const fn of this.messageListeners) fn(data);
      }}
      simulateDisconnect(errMessage) {{
        if (errMessage) {{
          global.chrome.runtime.lastError = {{ message: errMessage }};
        }} else {{
          global.chrome.runtime.lastError = null;
        }}
        for (const fn of this.disconnectListeners) fn();
      }}
    }}

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        onMessage: {{
          addListener: (fn) => {{
            messageListener = fn;
          }}
        }},
        sendMessage: (msg, cb) => {{
          broadcastHistory.push(msg);
          if (cb) cb();
        }},
        connectNative: (name) => {{
          return new MockNativePort(name);
        }},
        lastError: null
      }}
    }};

    // 1. Startup: Load background.js
    const bgCode = fs.readFileSync({json.dumps(str(bg_path))}, 'utf-8');
    eval(bgCode);

    (async () => {{
      const results = {{}};

      // Requirement 1: Startup -> Native connect called 0 times
      results.startupNativeCount = nativeConnectCount;

      // Requirement 2: Popup opened (GET_BRIDGE_STATUS) -> Native connect called 0 times
      let initStatus = null;
      messageListener({{ action: 'GET_BRIDGE_STATUS' }}, {{}}, (resp) => {{
        initStatus = resp;
      }});
      results.startupStatus = initStatus;
      results.afterPopupOpenNativeCount = nativeConnectCount;

      // Requirement 3: User clicks CONNECT_DESKTOP -> connectNative called exactly 1 time
      let manualConnectResp = null;
      messageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, (resp) => {{
        manualConnectResp = resp;
      }});
      results.connectNativeCount = nativeConnectCount;
      results.connectStatus = manualConnectResp;

      // Requirement 4: Failed connection / Host missing -> immediate DISCONNECTED, 0 auto-reconnects
      const initialPort = activePorts[activePorts.length - 1];
      initialPort.simulateDisconnect('Specified native messaging host not found.');

      let postFailStatus = null;
      messageListener({{ action: 'GET_BRIDGE_STATUS' }}, {{}}, (resp) => {{
        postFailStatus = resp;
      }});
      results.postFailStatus = postFailStatus;
      results.postFailNativeCount = nativeConnectCount; // Remains 1, no retry

      // Requirement 5: User clicks CONNECT_DESKTOP again -> connects successfully
      messageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      const healthyPort = activePorts[activePorts.length - 1];
      healthyPort.simulateMessage({{
        type: 'bridge_status',
        protocol_version: 1,
        desktop_connected: true,
        message: 'Đã kết nối với Desktop.'
      }});

      let connectedStatus = null;
      messageListener({{ action: 'GET_BRIDGE_STATUS' }}, {{}}, (resp) => {{
        connectedStatus = resp;
      }});
      results.connectedStatus = connectedStatus;

      // Test product send while connected
      let sendProductSuccess = null;
      messageListener({{
        action: 'SEND_PRODUCT_TO_DESKTOP',
        payload: {{
          url: 'https://shopee.vn/test-product-i.123.456',
          product_name: 'Test Product',
          shop_id: '123',
          item_id: '456',
          images: ['https://example.com/1.jpg']
        }}
      }}, {{}}, (resp) => {{
        sendProductSuccess = resp;
      }});

      await new Promise(r => setTimeout(r, 100));

      results.sendProductSuccess = sendProductSuccess;
      results.productMsgSent = healthyPort.sentMessages.some(m => m.type === 'product_result');

      // Requirement 6: Native port disconnects -> state DISCONNECTED, automatic attempts = 0
      healthyPort.simulateDisconnect();

      let postCloseStatus = null;
      messageListener({{ action: 'GET_BRIDGE_STATUS' }}, {{}}, (resp) => {{
        postCloseStatus = resp;
      }});
      results.postCloseStatus = postCloseStatus;
      results.postCloseNativeCount = nativeConnectCount; // Remains 2, no auto reconnect

      // Requirement 7: User clicks reconnect -> exactly one new connection attempt
      messageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      results.userReconnectNativeCount = nativeConnectCount; // Becomes 3

      console.log(JSON.stringify(results));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    json_lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert json_lines, f"No JSON output from test: {result.stdout}"
    res_data = json.loads(json_lines[-1])

    # 1. Startup cleanliness
    assert res_data["startupNativeCount"] == 0
    assert res_data["startupStatus"]["status"] == "DISCONNECTED"
    assert res_data["startupStatus"]["connected"] is False

    # 2. Popup open does not trigger connection
    assert res_data["afterPopupOpenNativeCount"] == 0

    # 3. Explicit user click triggers exactly 1 connection
    assert res_data["connectNativeCount"] == 1
    assert res_data["connectStatus"]["status"] == "CONNECTING"

    # 4. Host missing returns to DISCONNECTED without auto-retries
    assert res_data["postFailStatus"]["status"] == "DISCONNECTED"
    assert res_data["postFailNativeCount"] == 1
    assert res_data["postFailStatus"]["hostInstalled"] is False
    assert "Native Host chưa được cài đặt" in res_data["postFailStatus"]["message"]

    # 5. Successful handshake and product send
    assert res_data["connectedStatus"]["status"] == "CONNECTED"
    assert res_data["connectedStatus"]["connected"] is True
    assert res_data["sendProductSuccess"]["success"] is True
    assert res_data["productMsgSent"] is True

    # 6. Connection close returns to DISCONNECTED without auto-reconnect
    assert res_data["postCloseStatus"]["status"] == "DISCONNECTED"
    assert res_data["postCloseNativeCount"] == 2
    assert "Mất kết nối" in res_data["postCloseStatus"]["message"]

    # 7. User clicks reconnect -> exactly one new attempt
    assert res_data["userReconnectNativeCount"] == 3



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
      left_boundary: "CONFIRMED",
      right_boundary: "CONFIRMED",
      completeness_reason: "CAROUSEL_BOUNDS_CONFIRMED",
      completed_at: Date.now() - 1000,
      debug: {
        product_key: "100:200",
        scan_state: "COMPLETE",
        left_boundary: "CONFIRMED",
        right_boundary: "CONFIRMED",
        completeness_reason: "CAROUSEL_BOUNDS_CONFIRMED",
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
            querySelectorAll: (qSel) => qSel.includes('qIctnQ') ? [1, 2, 3, 4, 5].map(idx => ({
              tagName: 'div',
              className: 'qIctnQ',
              querySelector: (s) => {
                if (s.includes('play')) return null;
                return { getAttribute: (a) => a === 'src' ? `https://down-vn.img.susercontent.com/file/vn-prod-${idx}` : null };
              },
              getAttribute: () => null
            })) : [],
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


def test_background_js_syntax_and_structure():
    """Verify background.js contains batch worker handling and passes node syntax check."""
    bg_path = EXTENSION_DIR / "background.js"
    assert bg_path.exists()
    content = bg_path.read_text(encoding="utf-8")

    # Verify key batch handlers exist
    assert "handleOpenProductRequest" in content
    assert "sendCompleteProductToDesktop" in content
    assert "ensureActiveWorkerTab" in content
    assert "restoreOriginalUserTab" in content
    assert "parseExpectedProduct" in content
    assert "open_product" in content
    assert "process_url" in content
    assert "cancel_processing" in content
    assert "batch_finished" in content
    assert "process_error" in content
    assert "AUTHORITATIVE_PRODUCT_COMPLETE" in content
    assert "waiting_page" in content
    assert "navigating" in content

    # Node syntax check
    result = subprocess.run(
        ["node", "--check", str(bg_path)],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    assert result.returncode == 0


def test_background_worker_lifecycle_simulation():
    """Simulate Chrome Extension foreground worker lifecycle, tab activation, and event-driven product result."""
    bg_path = EXTENSION_DIR / "background.js"
    js_test_code = f"""
    const fs = require('fs');
    const bgCode = fs.readFileSync({json.dumps(str(bg_path))}, 'utf-8');

    const calls = {{
      tabQueries: [],
      tabCreates: [],
      tabUpdates: [],
      tabRemoves: [],
      windowUpdates: [],
      nativePosts: []
    }};

    let currentTabs = [
      {{ id: 101, windowId: 501, active: true, url: 'https://shopee.vn/user-tab' }}
    ];

    let currentWindows = [
      {{ id: 501, focused: true }}
    ];

    let runtimeMessageListener = null;
    let nativeMessageListener = null;

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        connectNative: (name) => ({{
          postMessage: (msg) => {{
            calls.nativePosts.push(msg);
          }},
          onMessage: {{
            addListener: (cb) => {{ nativeMessageListener = cb; }},
            removeListener: () => {{}}
          }},
          onDisconnect: {{
            addListener: () => {{}},
            removeListener: () => {{}}
          }},
          disconnect: () => {{}}
        }}),
        sendMessage: () => {{}},
        onMessage: {{
          addListener: (cb) => {{ runtimeMessageListener = cb; }}
        }}
      }},
      tabs: {{
        query: async (q) => {{
          calls.tabQueries.push(q);
          return currentTabs.filter(t => t.active);
        }},
        get: async (id) => {{
          const found = currentTabs.find(t => t.id === id);
          if (!found) throw new Error('Tab not found');
          return found;
        }},
        create: async (opts) => {{
          calls.tabCreates.push(opts);
          const newTab = {{ id: 202, windowId: 501, active: opts.active, url: opts.url }};
          currentTabs.push(newTab);
          return newTab;
        }},
        update: async (id, opts) => {{
          calls.tabUpdates.push({{ id, opts }});
          const found = currentTabs.find(t => t.id === id);
          if (found) Object.assign(found, opts);
          return found;
        }},
        remove: async (id) => {{
          calls.tabRemoves.push(id);
          currentTabs = currentTabs.filter(t => t.id !== id);
        }},
        onRemoved: {{
          addListener: () => {{}}
        }},
        onUpdated: {{
          addListener: () => {{}}
        }}
      }},
      windows: {{
        update: async (id, opts) => {{
          calls.windowUpdates.push({{ id, opts }});
          const found = currentWindows.find(w => w.id === id);
          if (found) Object.assign(found, opts);
          return found;
        }}
      }}
    }};

    eval(bgCode);

    (async () => {{
      // 1. Popup initiates bridge connection
      runtimeMessageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});

      // 2. Native host acknowledges connection
      nativeMessageListener({{ type: 'bridge_status', desktop_connected: true, protocol_version: 1 }});

      // 3. Desktop sends open_product (item 1)
      nativeMessageListener({{
        type: 'open_product',
        protocol_version: 1,
        request_id: 'req-001',
        url: 'https://shopee.vn/product-i.123.456'
      }});

      await new Promise(r => setTimeout(r, 50));

      // 4. Content script in worker tab reaches AUTHORITATIVE_PRODUCT_COMPLETE
      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '123:456',
        snapshot: {{
          schema_version: 1,
          scan_state: 'COMPLETE',
          product_name: 'San Pham Ao Thun',
          shop_id: '123',
          item_id: '456',
          product_key: '123:456',
          final_url: 'https://shopee.vn/product-i.123.456',
          images: ['https://img.com/1.jpg', 'https://img.com/2.jpg'],
          image_count: 2
        }}
      }}, {{ tab: {{ id: 202 }} }});

      await new Promise(r => setTimeout(r, 50));

      // 5. Desktop sends batch_finished
      nativeMessageListener({{
        type: 'batch_finished',
        protocol_version: 1,
        success_count: 1,
        fail_count: 0
      }});

      await new Promise(r => setTimeout(r, 50));

      console.log(JSON.stringify({{
        tabCreates: calls.tabCreates,
        tabUpdates: calls.tabUpdates,
        tabRemoves: calls.tabRemoves,
        windowUpdates: calls.windowUpdates,
        nativePosts: calls.nativePosts
      }}));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert len(lines) >= 1
    data = json.loads(lines[-1])

    # 1. Worker tab was created active: true
    assert len(data["tabCreates"]) >= 1
    assert data["tabCreates"][0]["active"] is True

    # 2. Window was focused
    assert len(data["windowUpdates"]) >= 1
    assert any(w["opts"].get("focused") is True for w in data["windowUpdates"])

    # 3. Product result and progress were posted
    msg_types = [p.get("type") for p in data["nativePosts"]]
    assert "process_progress" in msg_types
    assert "product_result" in msg_types

    # 4. On batch_finished, worker tab was removed and original tab restored
    assert len(data["tabRemoves"]) >= 1
    assert 202 in data["tabRemoves"]


def test_background_worker_tab_reuse_multi_items():
    """Verify multiple URLs reuse the exact same dedicated worker tab without opening multiple tabs."""
    bg_path = EXTENSION_DIR / "background.js"
    js_test_code = f"""
    const fs = require('fs');
    const bgCode = fs.readFileSync({json.dumps(str(bg_path))}, 'utf-8');

    const calls = {{
      tabCreates: [],
      tabUpdates: [],
      tabRemoves: []
    }};

    let currentTabs = [
      {{ id: 101, windowId: 501, active: true, url: 'https://shopee.vn/user-tab' }}
    ];

    let runtimeMessageListener = null;
    let nativeMessageListener = null;

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        connectNative: (name) => ({{
          postMessage: () => {{}},
          onMessage: {{
            addListener: (cb) => {{ nativeMessageListener = cb; }},
            removeListener: () => {{}}
          }},
          onDisconnect: {{ addListener: () => {{}}, removeListener: () => {{}} }},
          disconnect: () => {{}}
        }}),
        sendMessage: () => {{}},
        onMessage: {{ addListener: (cb) => {{ runtimeMessageListener = cb; }} }}
      }},
      tabs: {{
        query: async () => currentTabs.filter(t => t.active),
        get: async (id) => {{
          const found = currentTabs.find(t => t.id === id);
          if (!found) throw new Error('Tab not found');
          return found;
        }},
        create: async (opts) => {{
          calls.tabCreates.push(opts);
          const newTab = {{ id: 202, windowId: 501, active: opts.active, url: opts.url }};
          currentTabs.push(newTab);
          return newTab;
        }},
        update: async (id, opts) => {{
          calls.tabUpdates.push({{ id, opts }});
          const found = currentTabs.find(t => t.id === id);
          if (found) Object.assign(found, opts);
          return found;
        }},
        remove: async (id) => {{
          calls.tabRemoves.push(id);
          currentTabs = currentTabs.filter(t => t.id !== id);
        }},
        onRemoved: {{ addListener: () => {{}} }},
        onUpdated: {{ addListener: () => {{}} }}
      }},
      windows: {{
        update: async () => {{}}
      }}
    }};

    eval(bgCode);

    (async () => {{
      runtimeMessageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      nativeMessageListener({{ type: 'bridge_status', desktop_connected: true, protocol_version: 1 }});

      // Item 1
      nativeMessageListener({{ type: 'open_product', protocol_version: 1, request_id: 'req-001', url: 'https://shopee.vn/p1-i.123.456' }});
      await new Promise(r => setTimeout(r, 30));
      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '123:456',
        snapshot: {{
          schema_version: 1,
          scan_state: 'COMPLETE',
          product_name: 'San Pham 1',
          shop_id: '123',
          item_id: '456',
          product_key: '123:456',
          final_url: 'https://shopee.vn/p1-i.123.456',
          images: ['https://img.com/1.jpg'],
          image_count: 1
        }}
      }}, {{ tab: {{ id: 202 }} }});

      // Item 2
      nativeMessageListener({{ type: 'open_product', protocol_version: 1, request_id: 'req-002', url: 'https://shopee.vn/p2-i.123.789' }});
      await new Promise(r => setTimeout(r, 30));
      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '123:789',
        snapshot: {{
          schema_version: 1,
          scan_state: 'COMPLETE',
          product_name: 'San Pham 2',
          shop_id: '123',
          item_id: '789',
          product_key: '123:789',
          final_url: 'https://shopee.vn/p2-i.123.789',
          images: ['https://img.com/2.jpg'],
          image_count: 1
        }}
      }}, {{ tab: {{ id: 202 }} }});

      // Item 3
      nativeMessageListener({{ type: 'open_product', protocol_version: 1, request_id: 'req-003', url: 'https://shopee.vn/p3-i.123.999' }});
      await new Promise(r => setTimeout(r, 30));
      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '123:999',
        snapshot: {{
          schema_version: 1,
          scan_state: 'COMPLETE',
          product_name: 'San Pham 3',
          shop_id: '123',
          item_id: '999',
          product_key: '123:999',
          final_url: 'https://shopee.vn/p3-i.123.999',
          images: ['https://img.com/3.jpg'],
          image_count: 1
        }}
      }}, {{ tab: {{ id: 202 }} }});

      // Finish batch
      nativeMessageListener({{ type: 'batch_finished', protocol_version: 1, success_count: 3, fail_count: 0 }});
      await new Promise(r => setTimeout(r, 50));

      console.log(JSON.stringify({{
        tabCreatesCount: calls.tabCreates.length,
        tabUpdatesCount: calls.tabUpdates.length,
        tabRemoves: calls.tabRemoves
      }}));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert len(lines) >= 1
    data = json.loads(lines[-1])

    # Exactly ONE tab created across all 3 URLs
    assert data["tabCreatesCount"] == 1
    # Tab updates occurred for subsequent navigations
    assert data["tabUpdatesCount"] >= 3
    # Worker tab was removed on finish
    assert 202 in data["tabRemoves"]


def test_case_a_content_script_complete_9_images_batch_transmits_9():
    """Case A: Content script emits COMPLETE snapshot with 9 images -> Batch transmits exact 9 images."""
    bg_path = EXTENSION_DIR / "background.js"
    js_test_code = f"""
    const fs = require('fs');
    const bgCode = fs.readFileSync({json.dumps(str(bg_path))}, 'utf-8');

    const nativePosts = [];
    let runtimeMessageListener = null;
    let nativeMessageListener = null;

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        connectNative: (name) => ({{
          postMessage: (msg) => {{ nativePosts.push(msg); }},
          onMessage: {{ addListener: (cb) => {{ nativeMessageListener = cb; }}, removeListener: () => {{}} }},
          onDisconnect: {{ addListener: () => {{}}, removeListener: () => {{}} }},
          disconnect: () => {{}}
        }}),
        sendMessage: () => {{}},
        onMessage: {{ addListener: (cb) => {{ runtimeMessageListener = cb; }} }}
      }},
      tabs: {{
        query: async () => [{{ id: 101, windowId: 501, active: true }}],
        get: async (id) => ({{ id: 202, windowId: 501, active: true, url: 'https://shopee.vn/product-i.78513158.28469164720' }}),
        create: async (opts) => ({{ id: 202, windowId: 501, active: true, url: opts.url }}),
        update: async () => ({{ id: 202, windowId: 501, active: true }}),
        remove: async () => {{}},
        onRemoved: {{ addListener: () => {{}} }},
        onUpdated: {{ addListener: () => {{}} }}
      }},
      windows: {{ update: async () => {{}} }}
    }};

    eval(bgCode);

    (async () => {{
      runtimeMessageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      nativeMessageListener({{ type: 'bridge_status', desktop_connected: true, protocol_version: 1 }});

      nativeMessageListener({{
        type: 'open_product',
        protocol_version: 1,
        request_id: 'req-case-a',
        url: 'https://shopee.vn/product-i.78513158.28469164720'
      }});

      await new Promise(r => setTimeout(r, 50));

      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '78513158:28469164720',
        snapshot: {{
          schema_version: 1,
          scan_state: 'COMPLETE',
          product_key: '78513158:28469164720',
          product_name: 'Áo Thun Nam Cao Cấp',
          shop_id: '78513158',
          item_id: '28469164720',
          final_url: 'https://shopee.vn/product-i.78513158.28469164720',
          images: ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg', '6.jpg', '7.jpg', '8.jpg', '9.jpg'],
          image_count: 9
        }}
      }}, {{ tab: {{ id: 202 }} }});

      await new Promise(r => setTimeout(r, 50));

      console.log(JSON.stringify({{
        nativePosts: nativePosts
      }}));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert len(lines) >= 1
    data = json.loads(lines[-1])

    product_results = [p for p in data["nativePosts"] if p.get("type") == "product_result"]
    assert len(product_results) == 1
    outbound = product_results[0]["data"]
    assert outbound["product_name"] == "Áo Thun Nam Cao Cấp"
    assert len(outbound["images"]) == 9
    assert outbound["image_count"] == 9
    assert outbound["product_key"] == "78513158:28469164720"


def test_case_b_auto_send_exactly_once_guard():
    """Case B: Multiple COMPLETE events for the same request emit product_result exactly ONCE."""
    bg_path = EXTENSION_DIR / "background.js"
    js_test_code = f"""
    const fs = require('fs');
    const bgCode = fs.readFileSync({json.dumps(str(bg_path))}, 'utf-8');

    const nativePosts = [];
    let runtimeMessageListener = null;
    let nativeMessageListener = null;

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        connectNative: (name) => ({{
          postMessage: (msg) => {{ nativePosts.push(msg); }},
          onMessage: {{ addListener: (cb) => {{ nativeMessageListener = cb; }}, removeListener: () => {{}} }},
          onDisconnect: {{ addListener: () => {{}}, removeListener: () => {{}} }},
          disconnect: () => {{}}
        }}),
        sendMessage: () => {{}},
        onMessage: {{ addListener: (cb) => {{ runtimeMessageListener = cb; }} }}
      }},
      tabs: {{
        query: async () => [{{ id: 101, windowId: 501, active: true }}],
        get: async (id) => ({{ id: 202, windowId: 501, active: true, url: 'https://shopee.vn/product-i.78513158.28469164720' }}),
        create: async (opts) => ({{ id: 202, windowId: 501, active: true, url: opts.url }}),
        update: async () => ({{ id: 202, windowId: 501, active: true }}),
        remove: async () => {{}},
        onRemoved: {{ addListener: () => {{}} }},
        onUpdated: {{ addListener: () => {{}} }}
      }},
      windows: {{ update: async () => {{}} }}
    }};

    eval(bgCode);

    (async () => {{
      runtimeMessageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      nativeMessageListener({{ type: 'bridge_status', desktop_connected: true, protocol_version: 1 }});

      nativeMessageListener({{
        type: 'open_product',
        protocol_version: 1,
        request_id: 'req-case-b',
        url: 'https://shopee.vn/product-i.78513158.28469164720'
      }});

      await new Promise(r => setTimeout(r, 50));

      const snap = {{
        schema_version: 1,
        scan_state: 'COMPLETE',
        product_key: '78513158:28469164720',
        product_name: 'Áo Thun Nam Cao Cấp',
        shop_id: '78513158',
        item_id: '28469164720',
        final_url: 'https://shopee.vn/product-i.78513158.28469164720',
        images: ['1.jpg', '2.jpg', '3.jpg'],
        image_count: 3
      }};

      // First COMPLETE event
      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '78513158:28469164720',
        snapshot: snap
      }}, {{ tab: {{ id: 202 }} }});

      // Second duplicate COMPLETE event (e.g. from rapid DOM mutations)
      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '78513158:28469164720',
        snapshot: snap
      }}, {{ tab: {{ id: 202 }} }});

      await new Promise(r => setTimeout(r, 50));

      console.log(JSON.stringify({{
        nativePosts: nativePosts
      }}));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert len(lines) >= 1
    data = json.loads(lines[-1])

    product_results = [p for p in data["nativePosts"] if p.get("type") == "product_result"]
    assert len(product_results) == 1, f"Expected exactly 1 product_result, got {len(product_results)}"


def test_case_c_manual_and_batch_send_use_same_canonical_sender():
    """Case C: Both manual send and batch send converge through the same canonical sender and schema."""
    bg_path = EXTENSION_DIR / "background.js"
    js_test_code = f"""
    const fs = require('fs');
    const bgCode = fs.readFileSync({json.dumps(str(bg_path))}, 'utf-8');

    const nativePosts = [];
    let runtimeMessageListener = null;
    let nativeMessageListener = null;

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        connectNative: (name) => ({{
          postMessage: (msg) => {{ nativePosts.push(msg); }},
          onMessage: {{ addListener: (cb) => {{ nativeMessageListener = cb; }}, removeListener: () => {{}} }},
          onDisconnect: {{ addListener: () => {{}}, removeListener: () => {{}} }},
          disconnect: () => {{}}
        }}),
        sendMessage: () => {{}},
        onMessage: {{ addListener: (cb) => {{ runtimeMessageListener = cb; }} }}
      }},
      tabs: {{
        query: async () => [{{ id: 101, windowId: 501, active: true }}],
        get: async (id) => ({{ id: 202, windowId: 501, active: true, url: 'https://shopee.vn/product-i.78513158.28469164720' }}),
        create: async (opts) => ({{ id: 202, windowId: 501, active: true, url: opts.url }}),
        update: async () => ({{ id: 202, windowId: 501, active: true }}),
        remove: async () => {{}},
        sendMessage: async (tabId, msg) => {{
          if (msg.type === 'GET_COMPLETE_SNAPSHOT') {{
            return {{
              ok: true,
              snapshot: {{
                schema_version: 1,
                scan_state: 'COMPLETE',
                product_key: '78513158:28469164720',
                product_name: 'Áo Thun Nam Cao Cấp',
                shop_id: '78513158',
                item_id: '28469164720',
                final_url: 'https://shopee.vn/product-i.78513158.28469164720',
                images: ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg', '6.jpg', '7.jpg', '8.jpg', '9.jpg'],
                image_count: 9
              }}
            }};
          }}
          return null;
        }},
        onRemoved: {{ addListener: () => {{}} }},
        onUpdated: {{ addListener: () => {{}} }}
      }},
      windows: {{ update: async () => {{}} }}
    }};

    eval(bgCode);

    (async () => {{
      // 1. Establish bridge connection
      runtimeMessageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      nativeMessageListener({{ type: 'bridge_status', desktop_connected: true, protocol_version: 1 }});

      // 2. Manual Send
      let manualRes = null;
      runtimeMessageListener({{
        action: 'SEND_PRODUCT_TO_DESKTOP',
        tabId: 101,
        url: 'https://shopee.vn/product-i.78513158.28469164720'
      }}, {{}}, (res) => {{ manualRes = res; }});

      await new Promise(r => setTimeout(r, 50));

      // 3. Batch Send
      nativeMessageListener({{
        type: 'open_product',
        protocol_version: 1,
        request_id: 'req-batch-001',
        url: 'https://shopee.vn/product-i.78513158.28469164720'
      }});

      await new Promise(r => setTimeout(r, 50));

      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '78513158:28469164720',
        snapshot: {{
          schema_version: 1,
          scan_state: 'COMPLETE',
          product_key: '78513158:28469164720',
          product_name: 'Áo Thun Nam Cao Cấp',
          shop_id: '78513158',
          item_id: '28469164720',
          final_url: 'https://shopee.vn/product-i.78513158.28469164720',
          images: ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg', '6.jpg', '7.jpg', '8.jpg', '9.jpg'],
          image_count: 9
        }}
      }}, {{ tab: {{ id: 202 }} }});

      await new Promise(r => setTimeout(r, 50));

      console.log(JSON.stringify({{
        manualResponse: manualRes,
        nativePosts: nativePosts
      }}));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert len(lines) >= 1
    data = json.loads(lines[-1])

    product_results = [p for p in data["nativePosts"] if p.get("type") == "product_result"]
    assert len(product_results) == 2

    manual_out = product_results[0]
    batch_out = product_results[1]

    assert manual_out["source"] == "manual"
    assert len(manual_out["data"]["images"]) == 9
    assert manual_out["data"]["image_count"] == 9

    assert batch_out["source"] == "batch"
    assert len(batch_out["data"]["images"]) == 9
    assert batch_out["data"]["image_count"] == 9
    assert batch_out.get("request_id") == "req-batch-001"


def test_case_d_stale_complete_event_ignored():
    """Case D: Stale Product A event arriving after Product B starts is ignored."""
    bg_path = EXTENSION_DIR / "background.js"
    js_test_code = f"""
    const fs = require('fs');
    const bgCode = fs.readFileSync({json.dumps(str(bg_path))}, 'utf-8');

    const nativePosts = [];
    let runtimeMessageListener = null;
    let nativeMessageListener = null;

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        connectNative: (name) => ({{
          postMessage: (msg) => {{ nativePosts.push(msg); }},
          onMessage: {{ addListener: (cb) => {{ nativeMessageListener = cb; }}, removeListener: () => {{}} }},
          onDisconnect: {{ addListener: () => {{}}, removeListener: () => {{}} }},
          disconnect: () => {{}}
        }}),
        sendMessage: () => {{}},
        onMessage: {{ addListener: (cb) => {{ runtimeMessageListener = cb; }} }}
      }},
      tabs: {{
        query: async () => [{{ id: 101, windowId: 501, active: true }}],
        get: async (id) => ({{ id: 202, windowId: 501, active: true, url: 'https://shopee.vn/product-b-i.888.999' }}),
        create: async (opts) => ({{ id: 202, windowId: 501, active: true, url: opts.url }}),
        update: async () => ({{ id: 202, windowId: 501, active: true }}),
        remove: async () => {{}},
        onRemoved: {{ addListener: () => {{}} }},
        onUpdated: {{ addListener: () => {{}} }}
      }},
      windows: {{ update: async () => {{}} }}
    }};

    eval(bgCode);

    (async () => {{
      runtimeMessageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      nativeMessageListener({{ type: 'bridge_status', desktop_connected: true, protocol_version: 1 }});

      // Start Product B
      nativeMessageListener({{
        type: 'open_product',
        protocol_version: 1,
        request_id: 'req-product-b',
        url: 'https://shopee.vn/product-b-i.888.999'
      }});

      await new Promise(r => setTimeout(r, 50));

      // Stale event from old Product A (111:222) arrives
      runtimeMessageListener({{
        type: 'AUTHORITATIVE_PRODUCT_COMPLETE',
        product_key: '111:222',
        snapshot: {{
          schema_version: 1,
          scan_state: 'COMPLETE',
          product_key: '111:222',
          product_name: 'Stale Product A',
          shop_id: '111',
          item_id: '222',
          images: ['1.jpg'],
          image_count: 1
        }}
      }}, {{ tab: {{ id: 202 }} }});

      await new Promise(r => setTimeout(r, 50));

      console.log(JSON.stringify({{
        nativePosts: nativePosts
      }}));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert len(lines) >= 1
    data = json.loads(lines[-1])

    # No product_result should be sent for stale product A
    product_results = [p for p in data["nativePosts"] if p.get("type") == "product_result"]
    assert len(product_results) == 0


def test_case_e_no_complete_before_timeout_fails_with_product_timeout():
    """Case E: Bounded timeout triggers PRODUCT_TIMEOUT error when COMPLETE is not reached."""
    bg_path = EXTENSION_DIR / "background.js"
    # Reduce timeout for test
    bg_code = bg_path.read_text(encoding="utf-8")
    bg_code = bg_code.replace("PRODUCT_TIMEOUT_MS = 35000", "PRODUCT_TIMEOUT_MS = 100")

    js_test_code = f"""
    const nativePosts = [];
    let runtimeMessageListener = null;
    let nativeMessageListener = null;

    global.chrome = {{
      runtime: {{
        id: 'kjkgdknadhnpigglcpjbgkkbcngclhgf',
        connectNative: (name) => ({{
          postMessage: (msg) => {{ nativePosts.push(msg); }},
          onMessage: {{ addListener: (cb) => {{ nativeMessageListener = cb; }}, removeListener: () => {{}} }},
          onDisconnect: {{ addListener: () => {{}}, removeListener: () => {{}} }},
          disconnect: () => {{}}
        }}),
        sendMessage: () => {{}},
        onMessage: {{ addListener: (cb) => {{ runtimeMessageListener = cb; }} }}
      }},
      tabs: {{
        query: async () => [{{ id: 101, windowId: 501, active: true }}],
        get: async (id) => ({{ id: 202, windowId: 501, active: true, url: 'https://shopee.vn/product-i.78513158.28469164720' }}),
        create: async (opts) => ({{ id: 202, windowId: 501, active: true, url: opts.url }}),
        update: async () => ({{ id: 202, windowId: 501, active: true }}),
        remove: async () => {{}},
        onRemoved: {{ addListener: () => {{}} }},
        onUpdated: {{ addListener: () => {{}} }}
      }},
      windows: {{ update: async () => {{}} }}
    }};

    eval({json.dumps(bg_code)});

    (async () => {{
      runtimeMessageListener({{ action: 'CONNECT_DESKTOP' }}, {{}}, () => {{}});
      nativeMessageListener({{ type: 'bridge_status', desktop_connected: true, protocol_version: 1 }});

      nativeMessageListener({{
        type: 'open_product',
        protocol_version: 1,
        request_id: 'req-timeout-001',
        url: 'https://shopee.vn/product-i.78513158.28469164720'
      }});

      // Wait past timeout (100ms) without emitting COMPLETE
      await new Promise(r => setTimeout(r, 200));

      console.log(JSON.stringify({{
        nativePosts: nativePosts
      }}));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    result = subprocess.run(
        ["node", "-e", js_test_code],
        capture_output=True,
        encoding="utf-8",
        check=True
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith("{")]
    assert len(lines) >= 1
    data = json.loads(lines[-1])

    # No product_result emitted on timeout
    product_results = [p for p in data["nativePosts"] if p.get("type") == "product_result"]
    assert len(product_results) == 0

    # Exactly one process_error emitted with PRODUCT_TIMEOUT
    error_results = [p for p in data["nativePosts"] if p.get("type") == "process_error"]
    assert len(error_results) == 1
    assert error_results[0]["error_code"] == "PRODUCT_TIMEOUT"


def test_static_architecture_single_product_result_builder():
    """Static Code Check: Verify exactly ONE active product_result construction in background.js and zero batch DOM extractors."""
    bg_path = EXTENSION_DIR / "background.js"
    content = bg_path.read_text(encoding="utf-8")

    # Check for type: 'product_result' occurrences (should only be in sendProductSnapshotToDesktop)
    product_result_matches = re.findall(r"type:\s*['\"]product_result['\"]", content)
    assert len(product_result_matches) == 1, (
        f"Expected exactly 1 product_result construction, found {len(product_result_matches)}"
    )

    # Ensure background.js does NOT query DOM elements directly
    assert "document.querySelectorAll" not in content
    assert "document.querySelector" not in content
    assert "executeScript" not in content  # Background must NOT use executeScript for batch extraction


def test_source_selection_structured_data_always_partial():
    """
    Verify that structured_data is NEVER COMPLETE regardless of candidate count (1, 4, 20 images),
    and only gallery_carousel can achieve COMPLETE.
    """
    js_code = """
    const results = {};

    // 1. Structured = 4, Gallery = 0 -> PARTIAL
    const res4 = core.chooseBestImageSource(
      { found: true, images: ['1.jpg', '2.jpg', '3.jpg', '4.jpg'], rawCandidateCount: 4 },
      { found: false, images: [], scanQuality: 'FAILED' }
    );
    results.res4 = { source: res4.selectedSource, quality: res4.scanQuality, count: res4.finalCount };

    // 2. Structured = 1, Gallery = 0 -> PARTIAL
    const res1 = core.chooseBestImageSource(
      { found: true, images: ['1.jpg'], rawCandidateCount: 1 },
      { found: false, images: [], scanQuality: 'FAILED' }
    );
    results.res1 = { source: res1.selectedSource, quality: res1.scanQuality, count: res1.finalCount };

    // 3. Structured = 20, Gallery = 0 -> PARTIAL (Count never implies completeness)
    const imgs20 = Array.from({ length: 20 }, (_, i) => `${i + 1}.jpg`);
    const res20 = core.chooseBestImageSource(
      { found: true, images: imgs20, rawCandidateCount: 20 },
      { found: false, images: [], scanQuality: 'FAILED' }
    );
    results.res20 = { source: res20.selectedSource, quality: res20.scanQuality, count: res20.finalCount };

    // 4. Structured = 4, Gallery = 9 COMPLETE -> gallery_carousel COMPLETE 9
    const imgs9 = Array.from({ length: 9 }, (_, i) => `${i + 1}.jpg`);
    const resGal9 = core.chooseBestImageSource(
      { found: true, images: ['1.jpg', '2.jpg', '3.jpg', '4.jpg'], rawCandidateCount: 4 },
      {
        found: true,
        images: imgs9,
        initialVisibleCount: 5,
        carouselLeftAdvances: 2,
        carouselRightAdvances: 2,
        leftmostReached: true,
        rightmostReached: true,
        leftBoundary: 'CONFIRMED',
        rightBoundary: 'CONFIRMED',
        totalDiscoveredCount: 9,
        imageMediaCount: 9,
        videoMediaCount: 0,
        unknownMediaCount: 0,
        scanQuality: 'COMPLETE',
        completenessReason: 'CAROUSEL_BOUNDS_CONFIRMED'
      }
    );
    results.resGal9 = { source: resGal9.selectedSource, quality: resGal9.scanQuality, count: resGal9.finalCount };

    console.log(JSON.stringify(results));
    """
    res = run_node_code(js_code)

    assert res["res4"]["source"] == "structured_data"
    assert res["res4"]["quality"] == "PARTIAL"
    assert res["res4"]["count"] == 4

    assert res["res1"]["source"] == "structured_single_fallback"
    assert res["res1"]["quality"] == "PARTIAL"
    assert res["res1"]["count"] == 1

    assert res["res20"]["source"] == "structured_data"
    assert res["res20"]["quality"] == "PARTIAL"
    assert res["res20"]["count"] == 20

    assert res["resGal9"]["source"] == "gallery_carousel"
    assert res["resGal9"]["quality"] == "COMPLETE"
    assert res["resGal9"]["count"] == 9


_MUTABLE_GALLERY_HARNESS_JS = r"""
function createMutableGalleryHarness(initialFrames, initialArrowsEnabled = true) {
  let frames = initialFrames;
  let position = 0;
  let arrowsEnabled = initialArrowsEnabled;
  const observerInstances = [];

  class HarnessMutationObserver {
    constructor(callback) {
      this.callback = callback;
      this.connected = false;
      this.target = null;
      observerInstances.push(this);
    }
    observe(target) {
      this.target = target;
      this.connected = true;
    }
    disconnect() {
      this.connected = false;
      this.target = null;
    }
  }

  function imageUrl(id) {
    return `https://down-vn.img.susercontent.com/file/vn-gallery-${id}`;
  }

  function makeMedia(definition) {
    const isVideo = typeof definition === 'object' && definition.type === 'video';
    const id = isVideo ? definition.id : definition;
    return {
      tagName: 'div',
      className: 'qIctnQ',
      textContent: isVideo ? `video-${id}` : '',
      getAttribute: () => null,
      querySelector: (selector) => {
        if (isVideo) {
          if (selector.includes('video') || selector.includes('play') || selector.includes('emXGWZ')) {
            return { tagName: 'video', getAttribute: () => null };
          }
          return null;
        }
        if (selector.includes('video') || selector.includes('play') || selector.includes('emXGWZ')) {
          return null;
        }
        if (selector.includes('img') || selector.includes('picture')) {
          return {
            tagName: 'img',
            src: imageUrl(id),
            currentSrc: imageUrl(id),
            getAttribute: (name) => name === 'src' ? imageUrl(id) : null
          };
        }
        return null;
      }
    };
  }

  function currentMedia() {
    return (frames[Math.min(position, frames.length - 1)] || []).map(makeMedia);
  }

  function notifyMutation() {
    observerInstances.forEach(observer => {
      if (observer.connected && observer.target === gallery) {
        observer.callback([{ type: 'childList', target: gallery }], observer);
      }
    });
  }

  function makeButton(direction) {
    const button = {
      tagName: 'button',
      className: direction === 'left' ? 'shopee-icon-button UTST3I' : 'shopee-icon-button mARMpd',
      disabled: false,
      getAttribute: (name) => name === 'aria-disabled' ? 'false' : null,
      click: () => {
        const previous = position;
        if (direction === 'left' && position > 0) position--;
        if (direction === 'right' && position < frames.length - 1) position++;
        if (position !== previous) notifyMutation();
      }
    };
    button.closest = () => button;
    return button;
  }

  function leftButton() {
    return arrowsEnabled && position > 0 ? makeButton('left') : null;
  }

  function rightButton() {
    return arrowsEnabled && position < frames.length - 1 ? makeButton('right') : null;
  }

  const gallery = {
    className: 'Wi_1Rq',
    parentElement: null,
    getAttribute: () => null,
    querySelector: (selector) => {
      if (selector.includes('arrow left') || selector.includes('UTST3I')) return leftButton();
      if (selector.includes('arrow right') || selector.includes('mARMpd')) return rightButton();
      return null;
    },
    querySelectorAll: (selector) => {
      if (selector.includes('qIctnQ') || selector.includes('image-carousel__item')) return currentMedia();
      if (selector.includes('button.shopee-icon-button')) {
        return [leftButton(), rightButton()].filter(Boolean);
      }
      return [];
    }
  };

  const briefing = {
    querySelector: (selector) => {
      if (selector.includes('Wi_1Rq') || selector.includes('image-carousel')) return gallery;
      if (selector.includes('qIctnQ')) return currentMedia()[0] || null;
      return null;
    }
  };

  const titleElement = { textContent: 'Gấu bông kỳ lân mềm mại' };
  const doc = {
    body: {},
    documentElement: {},
    title: 'Shopee',
    visibilityState: 'visible',
    querySelectorAll: () => [],
    querySelector: (selector) => {
      if (selector.includes(' h1') || selector === 'h1') return titleElement;
      if (selector.includes('product-briefing')) return briefing;
      if (selector.includes('Wi_1Rq')) return gallery;
      if (selector.includes('qIctnQ')) return currentMedia()[0] || null;
      return null;
    }
  };

  return {
    doc,
    gallery,
    MutationObserver: HarnessMutationObserver,
    observerInstances,
    setGallery(nextFrames, nextArrowsEnabled) {
      frames = nextFrames;
      position = 0;
      arrowsEnabled = nextArrowsEnabled;
      notifyMutation();
    }
  };
}
"""


def test_real_scanner_early_four_no_arrows_is_partial_then_hydrated_nine_complete():
    """Exercise the production core against the exact old false-COMPLETE timeline."""
    core_path = EXTENSION_DIR / "extractor_core.js"
    js_code = f"const core = require({json.dumps(str(core_path))});\n" + _MUTABLE_GALLERY_HARNESS_JS + r"""
const key = '78513158:28469164720';
const url = 'https://shopee.vn/product-i.78513158.28469164720';
const harness = createMutableGalleryHarness([['A', 'B', 'C', 'D']], false);
core.ProductCache.clear();
const session = core.createGalleryStabilitySession({
  documentRef: harness.doc,
  expectedProductKey: key,
  settleWindowMs: 80,
  MutationObserver: harness.MutationObserver
});
const options = {
  forceRescan: true,
  galleryStabilitySession: session,
  documentRef: harness.doc,
  productKey: key,
  advanceDelayMs: 1
};

(async () => {
  const early = await core.extractProductData(harness.doc, url, options);
  const earlyCacheComplete = core.ProductCache.hasComplete(key);
  harness.setGallery([
    ['A', 'B', 'C', 'D', 'E'],
    ['D', 'E', 'F', 'G', 'H'],
    ['F', 'G', 'H', 'I']
  ], true);
  const hydrated = await core.extractProductData(harness.doc, url, options);
  session.disconnect();
  console.log(JSON.stringify({
    early,
    earlyCacheComplete,
    hydrated,
    hydratedCacheComplete: core.ProductCache.hasComplete(key),
    observersDisconnected: harness.observerInstances.every(observer => !observer.connected)
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(["node", "-e", js_code], capture_output=True, encoding="utf-8", check=True)
    data = json.loads([line for line in result.stdout.splitlines() if line.startswith("{")][-1])

    assert data["early"]["image_count"] == 4
    assert data["early"]["extraction_status"] == "PARTIAL"
    assert data["early"]["left_boundary"] == "UNKNOWN"
    assert data["early"]["right_boundary"] == "UNKNOWN"
    assert data["early"]["completeness_reason"] == "NOT_COMPLETE"
    assert data["earlyCacheComplete"] is False
    assert data["hydrated"]["extraction_status"] == "COMPLETE"
    assert data["hydrated"]["image_count"] == 9
    assert data["hydrated"]["completeness_reason"] == "CAROUSEL_BOUNDS_CONFIRMED"
    assert data["hydratedCacheComplete"] is True
    assert data["observersDisconnected"] is True


def test_real_scanner_stable_single_page_four_images_becomes_complete():
    """A genuine no-arrow gallery becomes complete only after scoped stability proof."""
    core_path = EXTENSION_DIR / "extractor_core.js"
    js_code = f"const core = require({json.dumps(str(core_path))});\n" + _MUTABLE_GALLERY_HARNESS_JS + r"""
const key = '78513158:28469164720';
const url = 'https://shopee.vn/product-i.78513158.28469164720';
const harness = createMutableGalleryHarness([['A', 'B', 'C', 'D']], false);
core.ProductCache.clear();
const session = core.createGalleryStabilitySession({
  documentRef: harness.doc,
  expectedProductKey: key,
  settleWindowMs: 50,
  MutationObserver: harness.MutationObserver
});
const options = {
  forceRescan: true,
  galleryStabilitySession: session,
  documentRef: harness.doc,
  productKey: key,
  advanceDelayMs: 1
};

(async () => {
  const initial = await core.extractProductData(harness.doc, url, options);
  await new Promise(resolve => setTimeout(resolve, 70));
  const stable = await core.extractProductData(harness.doc, url, options);
  session.disconnect();
  console.log(JSON.stringify({
    initial,
    stable,
    cacheComplete: core.ProductCache.hasComplete(key),
    observersDisconnected: harness.observerInstances.every(observer => !observer.connected)
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(["node", "-e", js_code], capture_output=True, encoding="utf-8", check=True)
    data = json.loads([line for line in result.stdout.splitlines() if line.startswith("{")][-1])

    assert data["initial"]["extraction_status"] == "PARTIAL"
    assert data["initial"]["completeness_reason"] == "NOT_COMPLETE"
    assert data["stable"]["extraction_status"] == "COMPLETE"
    assert data["stable"]["image_count"] == 4
    assert data["stable"]["completeness_reason"] == "STABLE_SINGLE_PAGE"
    assert data["cacheComplete"] is True
    assert data["observersDisconnected"] is True


def test_real_scanner_carousel_nine_images_and_one_video_regression():
    """Preserve overlapping carousel enumeration while excluding video media."""
    core_path = EXTENSION_DIR / "extractor_core.js"
    js_code = f"const core = require({json.dumps(str(core_path))});\n" + _MUTABLE_GALLERY_HARNESS_JS + r"""
const key = '78513158:28469164720';
const url = 'https://shopee.vn/product-i.78513158.28469164720';
const harness = createMutableGalleryHarness([
  ['I1', 'I2', { type: 'video', id: 'V1' }, 'I3', 'I4'],
  ['I3', 'I4', 'I5', 'I6', 'I7'],
  ['I6', 'I7', 'I8', 'I9']
], true);
core.ProductCache.clear();

(async () => {
  const result = await core.extractProductData(harness.doc, url, {
    forceRescan: true,
    documentRef: harness.doc,
    productKey: key,
    advanceDelayMs: 1
  });
  console.log(JSON.stringify(result));
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(["node", "-e", js_code], capture_output=True, encoding="utf-8", check=True)
    data = json.loads([line for line in result.stdout.splitlines() if line.startswith("{")][-1])

    assert data["extraction_status"] == "COMPLETE"
    assert data["image_count"] == 9
    assert data["debug"]["video_media"] == 1
    assert data["completeness_reason"] == "CAROUSEL_BOUNDS_CONFIRMED"
    assert data["left_boundary"] == "CONFIRMED"
    assert data["right_boundary"] == "CONFIRMED"


def test_content_script_lifecycle_emits_authoritative_complete_on_hydration():
    """Verify content.js automatic lifecycle emits AUTHORITATIVE_PRODUCT_COMPLETE when gallery hydrates to 9 images."""
    content_path = EXTENSION_DIR / "content.js"
    core_path = EXTENSION_DIR / "extractor_core.js"
    js_code = (
        f"const fs = require('fs');\nconst core = require({json.dumps(str(core_path))});\n"
        + f"const contentCode = fs.readFileSync({json.dumps(str(content_path))}, 'utf-8');\n"
        + _MUTABLE_GALLERY_HARNESS_JS
        + r"""
const key = '78513158:28469164720';
const harness = createMutableGalleryHarness([['A', 'B', 'C', 'D']], false);
let sentRuntimeMessages = [];
global.MutationObserver = harness.MutationObserver;
global.ShopeeExtractorCore = core;
global.document = harness.doc;
global.window = { location: { href: 'https://shopee.vn/product-i.78513158.28469164720' } };
global.chrome = {
  runtime: {
    sendMessage: (msg, cb) => {
      sentRuntimeMessages.push(msg);
      if (cb) cb();
    },
    onMessage: { addListener: () => {} }
  }
};
core.ProductCache.clear();
eval(contentCode);

(async () => {
  // Initial 4 images: not complete yet
  await new Promise(resolve => setTimeout(resolve, 50));
  const countBefore = sentRuntimeMessages.length;

  // Hydrate full carousel (9 images)
  harness.setGallery([
    ['A', 'B', 'C', 'D', 'E'],
    ['D', 'E', 'F', 'G', 'H'],
    ['F', 'G', 'H', 'I']
  ], true);

  // Allow lifecycle loop to detect hydrated gallery
  const deadline = Date.now() + 3000;
  while (sentRuntimeMessages.length === countBefore && Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 50));
  }

  console.log(JSON.stringify({
    countBefore,
    sentMessages: sentRuntimeMessages
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
    )
    result = subprocess.run(["node", "-e", js_code], capture_output=True, encoding="utf-8", check=True)
    data = json.loads([line for line in result.stdout.splitlines() if line.startswith("{")][-1])

    assert data["countBefore"] == 0
    assert len(data["sentMessages"]) >= 1
    msg = data["sentMessages"][0]
    assert msg["type"] == "AUTHORITATIVE_PRODUCT_COMPLETE"
    assert msg["product_key"] == "78513158:28469164720"
    assert msg["snapshot"]["image_count"] == 9
    assert msg["snapshot"]["scan_state"] == "COMPLETE"


def test_content_script_lifecycle_no_complete_when_only_structured_4():
    """Structured-data-only 4 images must NOT emit AUTHORITATIVE_PRODUCT_COMPLETE."""
    content_path = EXTENSION_DIR / "content.js"
    core_path = EXTENSION_DIR / "extractor_core.js"
    content_code = content_path.read_text(encoding="utf-8")
    js_code = f"""
const core = require({json.dumps(str(core_path))});
const structuredProduct = {{
  '@type': 'Product',
  name: 'Gấu bông kỳ lân mềm mại',
  image: [1, 2, 3, 4].map(i => `https://down-vn.img.susercontent.com/file/vn-structured-${{i}}`)
}};
let sentRuntimeMessages = [];
global.ShopeeExtractorCore = core;
global.window = {{ location: {{ href: 'https://shopee.vn/product-i.78513158.28469164720' }} }};
global.document = {{
  body: {{}},
  documentElement: {{}},
  title: 'Shopee',
  visibilityState: 'visible',
  querySelectorAll: selector => selector.includes('application/ld+json')
    ? [{{ textContent: JSON.stringify(structuredProduct) }}]
    : [],
  querySelector: selector => selector === 'h1'
    ? {{ textContent: 'Gấu bông kỳ lân mềm mại' }}
    : null
}};
global.chrome = {{
  runtime: {{
    sendMessage: (msg, cb) => {{
      sentRuntimeMessages.push(msg);
      if (cb) cb();
    }},
    onMessage: {{ addListener: () => {{}} }}
  }}
}};
core.ProductCache.clear();
eval({json.dumps(content_code)});

(async () => {{
  await new Promise(resolve => setTimeout(resolve, 600));
  console.log(JSON.stringify({{ sentMessages: sentRuntimeMessages }}));
  process.exit(0);
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""
    result = subprocess.run(["node", "-e", js_code], capture_output=True, encoding="utf-8", check=True)
    data = json.loads([line for line in result.stdout.splitlines() if line.startswith("{")][-1])

    # No complete message emitted when only structured 4 images
    assert len(data["sentMessages"]) == 0
