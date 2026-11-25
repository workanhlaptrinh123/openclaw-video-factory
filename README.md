# OpenClaw Video Factory

Bộ cài đặt & nhà máy tạo video dọc 9:16 (1080×1920) tự động nối vào **OpenClaw đang chạy trên máy khách** — hỗ trợ giọng đọc tiếng Việt (`edge-tts`), ảnh AI song song (`cx/gpt-image-2`), phụ đề chuẩn HyperFrames, và **Codex AI Tự Sửa Lỗi (Codex CLI + Codex API dự phòng)**.

## Tính năng chính của file `.exe` cài đặt
- **Tự phát hiện OpenClaw trên máy khách** (`%LOCALAPPDATA%\OpenClaw\bin\openclaw.cmd`, `OPENCLAW_STATE_DIR`, hoặc `%USERPROFILE%\.openclaw`).
- **Giao diện trực quan từng bước (7 bước)** có thanh tiến độ, trạng thái màu sắc (`⏳ / 🔄 / 🛠️ / ✅ / ❌`) và nhật ký trực tiếp.
- **2 chế độ linh hoạt:** Tạo bot Telegram riêng cho video (`video-creator`) hoặc gắn thẳng skill vào bot OpenClaw sẵn có (`main`), giữ nguyên 100% bot/Zalo cũ.
- **Tự cấp quyền thực thi toàn phần (`openclaw approvals set`)** để bot không bị chặn lệnh render.
- **Codex Tự Sửa Lỗi 2 tầng:** ưu tiên gọi `codex.cmd exec`, nếu máy không có hoặc `codex CLI` lỗi sẽ tự động chuyển sang gọi **Codex API** bằng API Key nhập trong giao diện (luôn ẩn token/key trước khi gửi).
- **An toàn tuyệt đối:** tự sao lưu `openclaw.json` trước khi sửa, tự rollback nếu `openclaw config validate` báo lỗi, và có nút Hoàn tác 1-click.

## Build file `.exe` trên Windows
```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```
File kết quả nằm tại: `dist\OpenClaw-VideoFactory-Setup.exe`.

## Đẩy lên GitHub & tự build Release
```bash
git init
git add .
git commit -m "Initial OpenClaw Video Factory installer"
git branch -M main
git remote add origin https://github.com/<tai-khoan>/<ten-repo>.git
git push -u origin main

# Tạo bản phát hành .exe tự động trên GitHub Actions:
git tag v1.0.0
git push origin v1.0.0
```
