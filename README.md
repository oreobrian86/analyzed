# TikTok Channel Intelligence

Web app phân tích kênh TikTok: tìm **Channel DNA, Content Pillars, Content Formula, hiệu suất, điểm yếu, cơ hội và chiến lược nội dung** — dựa trên nội dung thật của video (hình, tiếng, chữ trên màn hình), không chỉ caption.

Chạy 100% trên cloud miễn phí (có giới hạn): **Cloudflare Pages + Render + Supabase + Gemini API**. Máy tính cá nhân không cần bật; người dùng chỉ cần trình duyệt (PC hoặc điện thoại).

## Tính năng

- **4 cách nhập video**: profile TikTok (yt-dlp, tuỳ chọn Apify) · danh sách URL · upload file · import CSV/JSON. Collector lỗi không làm hỏng hệ thống.
- **Pipeline cloud**: FFmpeg chuẩn hoá (giới hạn thời lượng, độ phân giải, dung lượng), đo cắt cảnh, trích keyframe; file tạm tự xoá.
- **Phân tích từng video**: topic, subtopic, format, khán giả, hook + loại hook, storytelling, cấu trúc kể, retention, visual, cảnh, OCR, audio, nhịp dựng (đo thật), CTA, kết, công thức, điểm mạnh/yếu, bằng chứng có timestamp, confidence.
- **Phân tích kênh phân cấp 6 stage**: video → topic (embedding + clustering) → pillar → kênh → chiến lược → báo cáo. Số liệu do code tính, AI không được tạo số.
- **Evidence-first**: mỗi insight có kết luận, bằng chứng, video tham chiếu, dữ liệu quan sát, pattern, giả thuyết, khuyến nghị, độ tin cậy; ref bịa bị loại.
- **Hàng đợi bền**: Postgres queue, giới hạn concurrency, retry có giới hạn, resume sau restart, cancel, cache kết quả.
- **Nhiều người dùng**: đăng nhập Supabase, allowlist email, quota theo user + quota tổng của project, rate limit, retention & cleanup tự động.
- **AI provider abstraction**: Gemini (mặc định) hoặc mọi API tương thích OpenAI; embedding fallback chạy local.

## Cấu trúc

```
backend/            FastAPI + worker (Docker, deploy Render)
  app/ai/           provider abstraction, Gemini, OpenAI-compatible, prompts, embedding local
  app/collectors/   yt-dlp, Apify (tuỳ chọn), import URL/CSV/JSON
  app/media/        FFmpeg pipeline
  app/analysis/     hiệu suất, clustering, chuẩn hoá & kiểm chứng insight, xuất Markdown
  app/worker/       hàng đợi, Stage 1 (video), Stage 2–6 (kênh)
  tests/            unit test
frontend/           React + Vite (deploy Cloudflare Pages)
supabase/migrations SQL: bảng, hàng đợi, quota, bucket
docs/               kiến trúc, setup, deploy, troubleshooting
.github/workflows   CI + giữ Supabase không bị pause
```

## Bắt đầu

1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — kiến trúc, đánh giá free tier, giới hạn thật.
2. [docs/SETUP.md](docs/SETUP.md) — tạo tài khoản, database, lấy key.
3. [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — deploy backend + frontend, nối hai đầu.
4. [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — xử lý lỗi.

## Bảo mật

- Secret chỉ nằm trong environment variables của Render. Frontend chỉ có Supabase **anon/publishable** key (công khai theo thiết kế) và URL API.
- Mọi bảng bật RLS không có policy ⇒ trình duyệt không đọc/ghi DB trực tiếp; mọi truy cập đi qua backend có kiểm tra quyền sở hữu.
- Video chỉ được gửi tới AI provider đã cấu hình. Ở free tier Gemini, Google có thể dùng dữ liệu để cải thiện sản phẩm — chỉ phân tích nội dung công khai.

## Phát triển (tuỳ chọn, cho ai có Python/Node)

```bash
cd backend && pip install -r requirements-dev.txt && pytest -q
cd frontend && npm install && npm run dev
```
