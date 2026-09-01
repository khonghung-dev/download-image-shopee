SHOPEE IMAGE DOWNLOADER — HƯỚNG DẪN CÀI ĐẶT
============================================================

Extension ID chính thức:
bhbnfalghoklngoohdpnjedcdcplbjhm

Bước 1 — Nạp Chrome Extension

1. Mở Chrome và truy cập: chrome://extensions
2. Bật Developer mode (Chế độ dành cho nhà phát triển).
3. Nếu phiên bản phát triển cũ còn hiển thị, hãy xóa hoặc tải lại Extension đó.
4. Chọn Load unpacked (Tải tiện ích đã giải nén).
5. Chọn thư mục chrome_extension nằm cạnh tập tin hướng dẫn này.
6. Kiểm tra Extension ID phải là:
   bhbnfalghoklngoohdpnjedcdcplbjhm

Bước 2 — Đăng ký Native Host

Nhấp chuột phải vào install_native_host.ps1, chọn Run with PowerShell.
Không cần quyền Administrator. Script chỉ đăng ký khóa HKCU của người dùng
hiện tại cho Native Host com.shopee_image_downloader.bridge.

Bước 3 — Mở ứng dụng

Chạy ShopeeImageDownloader.exe.

Khi xử lý tự động, Chrome sẽ mở hoặc tái sử dụng một tab Shopee thật làm tab
xử lý. Tab này xuất hiện ở phía trước là hành vi có chủ đích để Shopee hoạt
động trong phiên Chrome bình thường và để bạn hoàn thành xác minh khi cần.

Kiểm tra nhanh sau khi cài

- Extension hiển thị đúng ID ở trên.
- Mở ứng dụng Desktop, sau đó kết nối Extension với Desktop.
- Với sản phẩm chuẩn có 9 ảnh và 1 video, chế độ tự động phải nhận 9 ảnh.

Gỡ đăng ký Native Host

Chạy uninstall_native_host.ps1. Script chỉ xóa đúng khóa Native Host nói trên.
