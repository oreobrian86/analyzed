# Deployment guide — đưa app online

Làm sau khi xong [SETUP.md](SETUP.md). Backend deploy trước (để có URL API), rồi tới frontend, rồi quay lại sửa CORS.

## A. Backend lên Render

1. https://render.com → **Get Started** → đăng nhập bằng **GitHub** → cho phép Render đọc repo `tiktok-intel`.
2. **New + → Web Service** → chọn repo `tiktok-intel`.
3. Điền:
   - **Name**: `tiktok-intel-api` (URL sẽ là `https://tiktok-intel-api.onrender.com` hoặc có thêm hậu tố)
   - **Region**: Singapore
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime / Language**: **Docker**
   - **Instance Type**: **Free**
4. Mục **Environment Variables** → **Add from .env** hoặc thêm từng dòng. Tối thiểu:

   | Key | Giá trị |
   |---|---|
   | `SUPABASE_URL` | từ Setup bước 2.6 |
   | `SUPABASE_ANON_KEY` | từ Setup bước 2.6 |
   | `SUPABASE_SERVICE_ROLE_KEY` | từ Setup bước 2.6 |
   | `DATABASE_URL` | từ Setup bước 2.7 |
   | `GEMINI_API_KEY` | từ Setup bước 3 |
   | `ALLOWED_EMAILS` | email của bạn và bạn bè, cách nhau dấu phẩy |
   | `ADMIN_EMAILS` | email của bạn |
   | `CORS_ORIGINS` | tạm để `http://localhost:5173`, sửa ở bước C |
   | `PUBLIC_BASE_URL` | tạm để trống, sửa ở bước C |

   Toàn bộ biến khác (giới hạn, model...) xem `backend/.env.example` — không đặt thì dùng mặc định.
5. **Advanced → Health Check Path**: `/api/health`. Auto-Deploy: **On Commit**.
6. **Create Web Service**. Lần build đầu mất 5–10 phút (cài FFmpeg). Xong khi thấy `Your service is live`.
7. Mở `https://‹tên-service›.onrender.com/api/health` → phải thấy `{"ok": true, "missing_env": [], "worker": {...}}`.
   Mở thêm `/api/health?db=1` → phải có `"db": true`.

> Cách khác: **New + → Blueprint** → chọn repo → Render đọc `render.yaml` và hỏi các secret.

## B. Frontend lên Cloudflare Pages

1. https://dash.cloudflare.com → đăng ký → menu **Workers & Pages** → **Create** → tab **Pages** → **Connect to Git** → chọn GitHub → repo `tiktok-intel`.
2. Cấu hình build:
   - **Framework preset**: Vite (hoặc None)
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
   - **Root directory (advanced)**: `frontend`
3. **Environment variables** (Production):

   | Key | Giá trị |
   |---|---|
   | `VITE_SUPABASE_URL` | SUPABASE_URL |
   | `VITE_SUPABASE_ANON_KEY` | SUPABASE_ANON_KEY (**không** dùng service role) |
   | `VITE_API_URL` | `https://‹tên-service›.onrender.com` (không có `/` cuối) |
   | `NODE_VERSION` | `22` |
4. **Save and Deploy**. Xong sẽ có link `https://‹tên›.pages.dev`.

## C. Nối hai đầu

1. Quay lại Render → service → **Environment**:
   - `CORS_ORIGINS` = `https://‹tên›.pages.dev` (nhiều domain thì cách nhau dấu phẩy)
   - `PUBLIC_BASE_URL` = `https://‹tên-service›.onrender.com`
   - **Save Changes** → Render tự deploy lại.
2. Supabase → **Authentication → URL Configuration** → **Site URL** = `https://‹tên›.pages.dev`.
3. GitHub repo → **Settings → Secrets and variables → Actions → tab Variables → New repository variable**: `BACKEND_URL` = `https://‹tên-service›.onrender.com`. Vào tab **Actions** → **Keep Supabase awake** → **Run workflow** để thử.

## D. Dùng thử

1. Mở link `pages.dev` (trên PC hoặc điện thoại) → **Đăng ký** bằng email nằm trong `ALLOWED_EMAILS` → đăng nhập.
2. **Phân tích mới** → thử trước với tab **Danh sách URL video** (3–5 link) để kiểm tra AI chạy được.
3. Sau đó thử tab **Profile TikTok**. Nếu bị lỗi thu thập, đó là do TikTok chặn server — dùng URL/upload/import.
4. Gửi link `pages.dev` cho bạn bè; nhớ thêm email của họ vào `ALLOWED_EMAILS` trên Render.

## E. Cập nhật code về sau

Sửa file trên GitHub (bút chì ✏️ → Commit) ⇒ Render và Cloudflare tự build lại. Theo dõi ở tab **Events** (Render) và **Deployments** (Cloudflare). CI ở tab **Actions** của GitHub chạy test cho mỗi commit.

Nếu TikTok đổi cấu trúc trang khiến yt-dlp lỗi: Render → **Manual Deploy → Clear build cache & deploy** để lấy bản yt-dlp mới nhất.

## F. Chỉnh giới hạn

- Giới hạn mặc định cho mọi user: biến môi trường `MAX_*` trên Render.
- Giới hạn riêng 1 user: Supabase → **Table Editor → profiles** → cột `quota_overrides`, ví dụ `{"max_videos_per_day": 100, "max_videos_per_analysis": 50}`.
- Admin: đặt `role` = `admin` hoặc thêm email vào `ADMIN_EMAILS` (admin xem được mục Admin trong Settings).
