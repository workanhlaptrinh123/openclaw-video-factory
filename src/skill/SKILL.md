---
name: "tao-video-reel"
description: "Tạo video dọc 9:16 (1080x1920) có giọng đọc tiếng Việt edge-tts, phụ đề khớp câu, ảnh AI (cx/gpt-image-2) hoặc b-roll Pexels, dựng và render sạch bằng HyperFrames."
---

# Tạo Video Reel 9:16 (OpenClaw Video Factory)

Dùng skill này khi người dùng yêu cầu tạo video ngắn, video reel, video TikTok/Reels/Shorts, hoặc chỉnh sửa/làm lại video đã tạo.

## Quy trình chuẩn

1. **Lên kịch bản JSON** (lưu vào `{{VIDEO_FACTORY_DIR}}\scripts_in\<job_id>-<version>.json`):
   - `job_id`: slug chữ thường không dấu, chỉ gồm `a-z`, `0-9`, `-` (ví dụ `meo-dung-ai-20261125`).
   - `version`: `"v1"` (khi sửa lại tăng lên `"v2"`, `"v3"`...).
   - `title`: tiêu đề ngắn gọn.
   - `caption`: mô tả + hashtag đăng bài.
   - `voice`: `"vi-VN-NamMinhNeural"` (mặc định giọng nam) hoặc `"vi-VN-HoaiMyNeural"` (giọng nữ nếu người dùng yêu cầu).
   - `rate`: `"+5%"` (mặc định).
   - `aspect_ratio`: `"9:16"` (video dọc TikTok/Reels/Shorts — mặc định), `"16:9"` (video ngang YouTube/Facebook 1920×1080), hoặc `"1:1"` (video vuông 1080×1080).
   - `scenes`: danh sách 4–8 cảnh (mỗi cảnh ~10–18 từ tiếng Việt, khoảng 3–6 giây):
     - `voice`: lời thoại tiếng Việt tự nhiên, rõ câu, kết thúc bằng dấu chấm/hỏi/chấm than.
     - `text`: dòng tiêu đề ngắn cho cảnh 1 (hook mở đầu <= 8 từ, hiển thị 3 giây đầu).
     - Một trong 3 nguồn hình ảnh:
       - `image_prompt` (ưu tiên mặc định): mô tả chi tiết bằng tiếng Anh cho ảnh dọc 9:16 photorealistic (tự tạo song song bằng `cx/gpt-image-2`). Không yêu cầu chữ/logo trong ảnh.
       - `pixabay_query`: từ khóa tiếng Anh tìm video/ảnh nền miễn phí từ Pixabay (dùng khi `{{VIDEO_FACTORY_DIR}}\.env` có `PIXABAY_API_KEY`).
       - `image`: đường dẫn file ảnh có sẵn trên máy.

2. **Báo tiến độ ngắn trước khi render**:
   - Gửi đúng 1 tin nhắn tiến độ bằng công cụ `message` trước khi chạy lệnh render.

3. **Chạy lệnh tạo video (1 lệnh duy nhất)**:
   ```powershell
   & "{{VIDEO_FACTORY_DIR}}\.venv\Scripts\python.exe" -X utf8 "{{VIDEO_FACTORY_DIR}}\make_reel.py" --script "{{VIDEO_FACTORY_DIR}}\scripts_in\<job_id>-<version>.json"
   ```

4. **Gửi video kết quả qua Telegram**:
   - Đọc JSON kết quả từ stdout. Nếu `"ok": true`, gửi file tại đường dẫn `outbound_video` (`{{OPENCLAW_STATE_DIR}}\media\outbound\...`) kèm `caption` bằng công cụ `message`.
   - Sau khi gửi thành công (có `messageId`), kết thúc lượt bằng `NO_REPLY`.

5. **Tự động lưu Google Sheet / Đăng Facebook / Đăng YouTube (khi người dùng yêu cầu hoặc đã bật trong cấu hình)**:
   ```powershell
   & "{{VIDEO_FACTORY_DIR}}\.venv\Scripts\python.exe" -X utf8 "{{VIDEO_FACTORY_DIR}}\publish_social.py" --channel sheet|facebook|youtube --video "<duong_dan_mp4>" --title "<tieu_de>" --caption "<caption>"
   ```
   - Cấu hình kênh đăng nằm tại `{{VIDEO_FACTORY_DIR}}\social_config.json`. Chỉ đăng lên Facebook/YouTube khi người dùng yêu cầu hoặc đồng ý duyệt.

## Quy tắc bắt buộc
- **TUYỆT ĐỐI CẤM** dùng FFmpeg `drawtext`, `drawbox` hoặc `-vf subtitles` để dán chữ/sub đè lên MP4 cũ.
- Khi cần sửa chữ, đổi giọng, đổi ảnh hay làm lại: sửa file kịch bản JSON (tăng `version`) rồi chạy lại `make_reel.py`.
- Không in API key hay token ra tin nhắn hoặc log.
