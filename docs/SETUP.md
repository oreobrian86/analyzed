# Setup guide — chuẩn bị tài khoản & dịch vụ

Làm theo đúng thứ tự. Mọi bước đều làm trên trình duyệt, không cài gì lên máy. Thời gian: khoảng 45–60 phút cho lần đầu.

Bạn cần 5 tài khoản miễn phí: **GitHub**, **Supabase**, **Google AI Studio**, **Render**, **Cloudflare**. Nên dùng chung một email Google để dễ quản lý.

> Ghi chú: trong file này, chỗ nào ghi `‹...›` là giá trị bạn phải tự điền. Hãy mở một file ghi chú riêng (Google Keep, ghi chú điện thoại...) để chép các key — và **không bao giờ dán key vào code hoặc gửi cho người khác**.

---

## Bước 1 — Đưa code lên GitHub

1. Vào https://github.com → đăng nhập → nút **+** góc phải → **New repository**.
2. Repository name: `tiktok-intel` → chọn **Private** → **Create repository**.
3. Trong repo mới, bấm **uploading an existing file** → kéo **toàn bộ nội dung** thư mục `tiktok-intel` (đã giải nén) vào → **Commit changes**.
   - Lưu ý: GitHub web không hiện thư mục bắt đầu bằng dấu chấm khi kéo thả trên một số trình duyệt. Kiểm tra repo có thư mục `.github/workflows` và file `.gitignore`. Nếu thiếu: **Add file → Create new file**, gõ tên `.github/workflows/ci.yml` rồi dán nội dung từ file tương ứng.
4. Kiểm tra repo có các thư mục: `backend/`, `frontend/`, `supabase/`, `docs/`, file `render.yaml`.

## Bước 2 — Supabase (database, storage, đăng nhập)

1. https://supabase.com → **Start your project** → đăng nhập bằng GitHub.
2. **New project**: Name `tiktok-intel`, đặt **Database Password** (chép lại!), Region **Southeast Asia (Singapore)** → **Create new project**. Đợi 1–2 phút.
3. **Tạo bảng**: menu trái **SQL Editor** → **New query** → mở file `supabase/migrations/001_init.sql` trên GitHub, bấm nút **Copy raw file**, dán vào → **Run**. Phải thấy “Success. No rows returned”.
4. Làm tương tự với `supabase/migrations/002_storage.sql` (tạo 2 bucket `uploads`, `keyframes`). Kiểm tra ở menu **Storage**.
5. **Tắt xác nhận email** (vì email miễn phí của Supabase bị giới hạn rất ít email/giờ): **Authentication → Sign In / Providers → Email** → tắt **Confirm email** → Save.
   - Muốn chặn người lạ đăng ký luôn: sau khi bạn và bạn bè đã tạo tài khoản, tắt **Allow new users to sign up**. Backend cũng có allowlist email (Bước 4).
6. **Lấy key** — **Project Settings → API Keys** (hoặc **Data API**):
   - `Project URL` → dạng `https://abcd.supabase.co` → đây là **SUPABASE_URL**.
   - Key `anon` / `publishable` → **SUPABASE_ANON_KEY** (dùng cho cả frontend).
   - Key `service_role` / `secret` → **SUPABASE_SERVICE_ROLE_KEY** (chỉ backend, bí mật tuyệt đối).
7. **Lấy chuỗi kết nối DB**: nút **Connect** trên đầu trang → tab **Connection string** → chọn **Session pooler** (hỗ trợ IPv4 — Render cần cái này) → chép chuỗi `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-...pooler.supabase.com:5432/postgres`, thay `[YOUR-PASSWORD]` bằng mật khẩu ở bước 2 → đây là **DATABASE_URL**.
   - Nếu mật khẩu có ký tự đặc biệt như `@ # / ?`, hãy đặt lại mật khẩu chỉ gồm chữ + số (Project Settings → Database → Reset password) để tránh lỗi.

## Bước 3 — Gemini API key

1. https://aistudio.google.com → đăng nhập Google → **Get API key** → **Create API key** → chép → **GEMINI_API_KEY**.
2. Xem giới hạn thật của bạn: trong AI Studio mở mục **Rate limits / Usage** của project. Ghi lại RPM (request/phút) và RPD (request/ngày) của model bạn định dùng.
3. Đặt `AI_REQUESTS_PER_MINUTE` thấp hơn RPM đó, và `GLOBAL_MAX_AI_REQUESTS_PER_DAY` thấp hơn RPD (chừa 10–20%).
4. Kiểm tra tên model: trang https://ai.google.dev/gemini-api/docs/models. Mặc định code dùng `gemini-3.5-flash` (video + text) và `gemini-embedding-001`. Nếu model đó không có trong free tier của bạn, đổi biến `GEMINI_VIDEO_MODEL` / `GEMINI_TEXT_MODEL` sang model Flash/Flash-Lite đang free.

> Quyền riêng tư: ở free tier, Google ghi rõ nội dung gửi lên có thể được dùng để cải thiện sản phẩm. Chỉ phân tích video công khai.

Tiếp theo: [DEPLOYMENT.md](DEPLOYMENT.md).
