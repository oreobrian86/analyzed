# Troubleshooting

Luôn bắt đầu bằng 2 chỗ: **Render → service → Logs** và trang `https://‹api›.onrender.com/api/health?db=1`.

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Web hiện “Server miễn phí đang khởi động…” rồi chậm ~1 phút | Render free ngủ sau 15 phút không có request | Bình thường. Đợi rồi tải lại. Muốn luôn bật: Render Starter (trả phí). |
| “Thiếu cấu hình frontend” | Chưa đặt `VITE_*` trên Cloudflare, hoặc đặt sau khi build | Đặt biến → **Deployments → Retry deployment**. Biến `VITE_*` chỉ có hiệu lực khi build lại. |
| Lỗi CORS trong console / “Không kết nối được server” dù `/api/health` mở được | `CORS_ORIGINS` sai | Đúng chính xác `https://‹tên›.pages.dev`, không có `/` cuối. Link preview dạng `abc123.‹tên›.pages.dev` cần `CORS_ORIGIN_REGEX=https://.*\.‹tên›\.pages\.dev`. |
| `/api/health` báo `missing_env` | Thiếu biến môi trường | Thêm biến trên Render → Save (tự deploy lại). |
| `"db": false`, lỗi `could not translate host name` / `Network is unreachable` | Dùng *Direct connection* (IPv6) | Đổi `DATABASE_URL` sang **Session pooler** (port 5432 trên `pooler.supabase.com`). |
| `password authentication failed` | Sai mật khẩu, hoặc mật khẩu có ký tự đặc biệt | Reset password chỉ chữ + số rồi cập nhật `DATABASE_URL`. |
| `relation "jobs" does not exist` / `function claim_job does not exist` | Chưa chạy `001_init.sql` | Chạy lại file trong SQL Editor. |
| Upload lỗi `Bucket not found` | Chưa chạy `002_storage.sql` | Chạy file đó. |
| Đăng nhập được nhưng mọi trang báo 403 “Email này chưa được admin cho phép” | Email không có trong `ALLOWED_EMAILS` | Thêm email (chữ thường), Save trên Render. |
| Đăng ký báo “Email rate limit exceeded” / không nhận email xác nhận | SMTP mặc định Supabase giới hạn rất thấp | Tắt **Confirm email** (Setup bước 2.5). |
| Supabase báo project **Paused** | Không hoạt động 7 ngày | Dashboard → **Restore project**. Kiểm tra biến `BACKEND_URL` và workflow keepalive. |
| Phân tích profile lỗi “yt-dlp không lấy được danh sách…” | TikTok chặn IP server / đổi trang | Dùng tab URL / Upload / Import. Thử **Clear build cache & deploy** để cập nhật yt-dlp. Tuỳ chọn: bật Apify (`APIFY_TOKEN`, có phí khi hết credit). |
| Video lỗi “Tải video thất bại” nhưng metadata có | Video bị giới hạn vùng/tuổi, hoặc > `MAX_DOWNLOAD_MB` | Tải file về và dùng tab Upload. |
| Lỗi `Gemini HTTP 429` | Vượt rate limit/quota free tier | Giảm `AI_REQUESTS_PER_MINUTE`, giảm `GLOBAL_MAX_AI_REQUESTS_PER_DAY`, đợi sang ngày. Job tự retry có giới hạn. |
| `Gemini HTTP 404 ... models/xxx is not found` | Tên model đã đổi/ngừng | Sửa `GEMINI_VIDEO_MODEL` / `GEMINI_TEXT_MODEL` theo trang models của Google. |
| `Gemini HTTP 400 ... API key not valid` | Sai key | Tạo key mới trong AI Studio. |
| “Đã đạt giới hạn ... hôm nay” | Quota user hoặc quota toàn hệ thống | Đợi qua 7:00 sáng (giờ VN = 0:00 UTC), hoặc admin nâng giới hạn. |
| Job đứng yên ở “Đang chờ” | Worker không chạy (thiếu env), hoặc user khác đang chạy | Xem `/api/health` → `worker`. Mỗi lúc chỉ 1 job chạy (`WORKER_CONCURRENCY=1`). |
| Render log `Out of memory` / restart liên tục | Video quá nặng cho 512 MB | Giảm `MAX_VIDEO_HEIGHT=480`, `MAX_VIDEO_SECONDS=90`, giữ `WORKER_CONCURRENCY=1`. Job bị gián đoạn tự resume sau ~5 phút. |
| Báo cáo không có phần hiệu suất | Video upload không có views | Dùng Import CSV kèm views/likes, hoặc URL. |
| Pillar có cờ “mẫu nhỏ”, độ tin cậy thấp | Quá ít video | Phân tích ≥ 15–20 video để kết quả có ý nghĩa. |
| Build Cloudflare lỗi `npm ERR!` | Node cũ | Thêm biến `NODE_VERSION=22`. |

## Kiểm tra bằng tay

- Xem hàng đợi: Supabase → SQL Editor → `select type, status, count(*) from jobs group by 1,2;`
- Job lỗi gần nhất: `select id, type, attempts, last_error from jobs where status='failed' order by id desc limit 20;`
- Usage hôm nay: `select * from usage_daily where day = current_date;`
- Chạy dọn dữ liệu ngay: đăng nhập admin, gọi `POST /api/admin/cleanup` (hoặc đợi worker tự chạy mỗi giờ).
