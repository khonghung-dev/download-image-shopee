# Shopee Product Extractor (Chrome Extension Spike)

Feasibility spike extension (Manifest V3) for extracting Shopee product name, Shop ID, Item ID, and main gallery image URLs from the currently active tab.

---

## 🔒 Security & Privacy Notice

- **Zero access to personal browser files**: This extension runs entirely within Google Chrome's standard extension sandbox. It does **not** read local Chrome files, passwords, cookies, or history.
- **No browser automation**: This extension does not automate login, bypass CAPTCHAs, or control your browser. You browse normally and trigger extraction on-demand by clicking the extension icon.
- **Minimal Permissions**: Uses only `activeTab` and `scripting`, strictly bounded to Shopee regional domains.

---

## 📦 How to Install Manually

1. Open **Google Chrome** on your computer.
2. In the Chrome address bar, navigate to:
   ```
   chrome://extensions
   ```
3. In the top-right corner of the Extensions page, turn **ON** the **Developer mode** toggle switch.
4. Click the **Load unpacked** (Tải tiện ích đã giải nén) button in the top-left toolbar.
5. In the file picker dialog, navigate to and select this folder:
   ```
   D:\download-picture-shopee\chrome_extension
   ```
6. The extension **"Shopee Product Extractor"** will appear in your extensions list.
7. Click the Extensions puzzle piece icon on your Chrome toolbar and pin **Shopee Product Extractor** for easy access.

---

## 🚀 How to Use & Test

1. Open Google Chrome using your normal profile (e.g. `Thi Dieu Linh Tran`).
2. Log into Shopee if you wish to view authenticated / restricted items.
3. Manually open any Shopee product listing page (e.g. `https://shopee.vn/product/...` or `https://shopee.vn/...-i.12345.67890`).
4. Click the **Shopee Product Extractor** icon in your toolbar.
5. The extension popup will display:
   - **Product Name** (Tên sản phẩm)
   - **Shop ID** & **Item ID**
   - **Total Images Count**
   - Gallery image preview thumbnails
6. Click **[Sao chép kết quả (JSON)]** / **[Copy Result]** to copy the complete JSON object to your clipboard.
7. Open a text editor (Notepad, VS Code) and press `Ctrl + V` to inspect the extracted JSON.

---

## 📋 JSON Output Schema

```json
{
  "url": "https://shopee.vn/...",
  "product_name": "Tên sản phẩm ví dụ",
  "shop_id": "12345678",
  "item_id": "987654321",
  "images": [
    "https://down-vn.img.susercontent.com/file/vn-11134207-...",
    "https://down-vn.img.susercontent.com/file/vn-11134207-..."
  ]
}
```

---

## 🧪 Edge Cases & Non-Shopee Tabs

- If you click the extension on non-Shopee tabs (e.g. Google, YouTube), the popup will cleanly inform you:
  > *"Đây không phải trang sản phẩm Shopee."*
