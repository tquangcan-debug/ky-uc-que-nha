# Ký Ức Quê Nhà · sản xuất video tự động

Mỗi ngày 5h sáng (giờ Việt Nam), GitHub Actions tự:
1. chọn tập có ngày đăng hôm nay trong `tap/`,
2. tạo ảnh (Cloudflare Workers AI, miễn phí), giọng đọc (Edge TTS), dựng video dọc bằng FFmpeg (`scripts/render.py`),
3. tải lên YouTube ở chế độ riêng tư, hẹn công khai 19h, gắn nhãn nội dung AI, thumbnail, playlist (`scripts/yt_upload.py`),
4. mở một Issue "Video xong" để báo (GitHub gửi thông báo về điện thoại/email).

Chạy tay: tab **Actions** → *San xuat video hang ngay* → **Run workflow** (chọn tập, chế độ).

Bí mật (Settings → Secrets and variables → Actions): `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `YT_TOKEN_JSON`, `YT_CLIENT_SECRET_JSON`.
Biến (Variables): `MUSIC_URL`, `MUSIC_CREDIT` (ghi nguồn nhạc CC BY), `CF_IMAGE_MODEL` (tùy chọn).

Không đưa khóa hay token vào kho này.
