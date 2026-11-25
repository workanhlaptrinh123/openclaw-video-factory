# Hướng dẫn thiết lập OAuth 1-Click (Miễn phí 0đ) cho Google & Facebook

Để khách hàng chỉ cần bấm **1 nút Đăng nhập Google / Facebook** trên file `.exe` (không phải tự tạo JSON hay copy Token):

## 1. Google OAuth App (dùng chung cho Google Sheet + Google Drive + YouTube)
1. Vào https://console.cloud.google.com/ → tạo 1 Project mới (ví dụ `OpenClaw Video Factory`).
2. Vào **APIs & Services → Library**, bật 3 API miễn phí:
   - **Google Sheets API**
   - **Google Drive API**
   - **YouTube Data API v3**
3. Vào **OAuth consent screen**:
   - Chọn **External**, điền tên ứng dụng và link Chính sách bảo mật (Privacy Policy).
   - Chỉ thêm 3 scope sau (**KHÔNG** thêm scope `drive` toàn phần để tránh kiểm định CASA mất phí):
     - `https://www.googleapis.com/auth/drive.file`
     - `https://www.googleapis.com/auth/spreadsheets`
     - `https://www.googleapis.com/auth/youtube.upload`
4. Vào **Credentials → Create Credentials → OAuth client ID** → chọn **Desktop app** (hoặc Web app với redirect `http://127.0.0.1:18765/callback`).
5. Dán `client_id` và `client_secret` vào `src/installer/app_oauth_config.json` trước khi build `.exe`.

## 2. Meta App (Đăng nhập Facebook & tự chọn Fanpage)
1. Vào https://developers.facebook.com/ → **My Apps → Create App** → chọn loại **Business**.
2. Thêm sản phẩm **Facebook Login for Business**, thêm Valid OAuth Redirect URI:
   - `http://127.0.0.1:18765/callback`
3. Xin duyệt 2 quyền (miễn phí 0đ qua Meta App Review):
   - `pages_show_list`
   - `pages_manage_posts`
   - `pages_read_engagement`
4. Dán `app_id` và `app_secret` vào `src/installer/app_oauth_config.json` trước khi build `.exe`.
