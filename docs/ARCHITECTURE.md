# Phase 1 — Kiến trúc & đánh giá cloud stack

Thông tin free tier dưới đây được kiểm tra vào **11/2026** và **có thể thay đổi**. Trước khi deploy, mở trang pricing của từng dịch vụ để xem lại.

## 1. Sơ đồ

```
 Trình duyệt (PC / Android)                      ┌───────────────────────────────────────────┐
 ┌─────────────────────────┐   HTTPS + JWT       │ Render (free, Docker)  — backend          │
 │ React + Vite            │ ──────────────────▶ │ FastAPI (REST API)                         │
 │ Cloudflare Pages        │                     │  + Worker thread (cùng process)           │
 │ (static, luôn bật)      │ ◀── polling ─────── │    ├ yt-dlp  → thu thập / tải video       │
 └──────────┬──────────────┘                     │    ├ FFmpeg  → chuẩn hoá, cắt cảnh, frame │
            │ đăng nhập                          │    ├ AI layer → Gemini / OpenAI-compatible │
            ▼                                    │    └ numpy/sklearn → clustering, thống kê │
 ┌─────────────────────────┐                     └──────┬───────────────┬────────────────────┘
 │ Supabase Auth           │ ◀── verify token ──────────┘               │
 │ Supabase Postgres       │ ◀── queue, dữ liệu, quota ─────────────────┤
 │ Supabase Storage        │ ◀── upload tạm, keyframe ──────────────────┘
 └─────────────────────────┘                                ┌──────────────────────────┐
                                                            │ Gemini API (AI cloud)    │
 GitHub: mã nguồn → push → Cloudflare Pages + Render       │ video/ảnh/audio/text/emb │
 tự build & deploy. GitHub Actions: CI + ping giữ DB thức. └──────────────────────────┘
```

PC của bạn không tham gia vào bất kỳ bước nào. Người dùng chỉ cần trình duyệt.

## 2. Lựa chọn từng thành phần

| Thành phần | Chọn | Lý do | Giới hạn free (11/2026) |
|---|---|---|---|
| Frontend | React + Vite trên **Cloudflare Pages** | Static, không ngủ, auto-deploy từ GitHub | Đủ cho app nhỏ |
| Backend + worker | FastAPI trên **Render Free (Docker)** | Không cần thẻ, Docker cài được FFmpeg, auto-deploy từ GitHub | 512 MB RAM, 0.1 CPU, **ngủ sau 15 phút không có request**, khởi động lại ~1 phút, 750 giờ/tháng, filesystem tạm (mất khi restart) |
| Database | **Supabase Postgres** | Postgres thật → làm luôn hàng đợi job (`FOR UPDATE SKIP LOCKED`) | 500 MB DB, **project bị pause sau 7 ngày không hoạt động**, tối đa 2 project |
| Storage | **Supabase Storage** | Cùng nhà cung cấp, private bucket + signed URL | 1 GB file, 5 GB egress |
| Auth | **Supabase Auth** (email + mật khẩu) | Miễn phí, frontend chỉ giữ anon key | 50.000 MAU; email gửi bằng SMTP mặc định bị giới hạn rất thấp → nên tắt "Confirm email" |
| AI | **Gemini API** qua lớp abstraction | Đọc trực tiếp video (hình + tiếng) ⇒ không cần Whisper/OCR riêng, có embedding đa ngôn ngữ | Rate limit theo model & project, xem trong AI Studio. **Ở free tier Google có thể dùng nội dung gửi lên để cải thiện sản phẩm.** |
| Queue | Bảng `jobs` trong Postgres | Không thêm dịch vụ; sống sót qua restart | — |

### Phương án đã cân nhắc và loại
- **Hugging Face Docker Spaces**: nhiều RAM hơn, nhưng theo nguồn tổng hợp tháng 7/2026, Docker Spaces đã chuyển sang yêu cầu gói trả phí → không chọn (cần xác minh nếu muốn dùng).
- **Koyeb free**: không ngủ, nhưng yêu cầu thẻ khi đăng ký → để làm phương án thay thế.
- **Fly.io / Heroku**: không còn free tier.
- **Google Cloud Run**: free tier tốt nhưng bắt buộc bật billing (gắn thẻ) → rủi ro phát sinh phí.
- **GitHub Actions làm worker xử lý video**: kỹ thuật thì chạy được, nhưng điều khoản của GitHub không cho dùng Actions làm máy tính toán cho một dịch vụ không liên quan đến dự án phần mềm → không dùng. Actions chỉ dùng cho CI và 1 lệnh ping nhẹ mỗi 3 ngày.
- **Whisper / OCR / CLIP tự host**: cần CPU/RAM/GPU lớn hơn free tier → thay bằng khả năng đa phương thức của Gemini. Nếu dùng provider không đọc được video, hệ thống tự chuyển sang chế độ *keyframe + transcript*.

## 3. Pipeline xử lý 1 video (Stage 1)

1. **Metadata**: yt-dlp đọc trang video (1 request) → caption, ngày, views, likes, comments, shares.
2. **Cache**: nếu video TikTok này đã được phân tích với cùng model + prompt version ⇒ dùng lại, **không tốn AI quota**.
3. **Tải**: dùng lại kết quả bước 1 để tải file (giới hạn `MAX_DOWNLOAD_MB`).
4. **FFmpeg** (trong thư mục tạm, tự xoá):
   - Cắt tối đa `MAX_VIDEO_SECONDS`, scale xuống `MAX_VIDEO_HEIGHT` (640p), H.264 CRF 30, audio mono 64 kbps → file nhỏ để gửi AI.
   - Phát hiện cắt cảnh (`scene > 0.30`) → **số lần cắt / phút là số đo thật**, không phải AI đoán.
   - Trích `KEYFRAMES_PER_VIDEO` ảnh (giây 0.5 cho hook + các điểm cắt cảnh), JPEG 360px → lưu Storage để hiển thị.
5. **AI**: gửi video đã chuẩn hoá + metadata + số đo FFmpeg → JSON có cấu trúc: transcript, OCR, topic, format, hook + loại hook, storytelling, cấu trúc cảnh, retention, CTA, công thức, điểm mạnh/yếu, bằng chứng có timestamp, confidence, giới hạn dữ liệu.
6. Xoá file upload gốc (nếu có). Video không bao giờ được lưu lâu dài.

## 4. Phân tích phân cấp (Stage 2–6)

| Stage | Cách làm | Có dùng LLM? |
|---|---|---|
| Hiệu suất | Engagement rate, so với **median của chính kênh**, robust z-score trên log(views), loại video < 3 ngày tuổi, cần ≥ 5 video mới phát hiện outlier | Không |
| Embedding + clustering | Embedding Gemini (`taskType=CLUSTERING`) trên văn bản tổng hợp từ phân tích thật; KMeans cosine, chọn k bằng silhouette; cấu trúc yếu ⇒ giữ 1 nhóm. Fallback: embedding local (hashing TF-IDF, bỏ dấu tiếng Việt) | Không (chỉ embedding) |
| 2. Topic | Mỗi cluster: 1 prompt với tóm tắt có cấu trúc (≤ 25 video) + thống kê xác định | Có |
| 3. Pillar | Gộp topic thành 2–6 pillar; topic bị bỏ sót tự thành pillar riêng; số liệu tính lại bằng code | Có |
| 4. Channel | DNA, Content Formula, insight, điểm yếu — từ pillar + phân bổ + hiệu suất | Có |
| 5. Strategy | Cơ hội, chiến lược, tỷ trọng, thử nghiệm có chỉ số đo | Có |
| 6. Report | Ghép JSON + Markdown, ghi chú giới hạn dữ liệu | Không |

**Chống bịa dữ liệu**: mọi con số trong báo cáo do code tính. Mỗi insight có `conclusion / evidence / video_refs / observed_data / pattern / hypothesis / recommendation / confidence`. Video ref không tồn tại bị loại; insight không có ref hợp lệ hoặc không có bằng chứng bị hạ confidence và gắn cờ ⚠.

Số AI request cho 1 kênh 20 video ≈ 20 (video) + 1 (embedding) + số cluster (2–8) + 3 ≈ **26–32 request**.

## 5. Kiểm soát chi phí & lạm dụng

- Quota theo user/ngày: số phân tích, số video, số AI request, dung lượng upload, số phân tích chạy song song. Admin ghi đè cho từng user qua cột `profiles.quota_overrides`.
- **Giới hạn tổng của cả project** (`GLOBAL_MAX_*`) kiểm tra nguyên tử trong cùng hàm SQL ⇒ một người không thể dùng hết quota chung.
- Rate limiter AI toàn cục (`AI_REQUESTS_PER_MINUTE`), retry tối đa `AI_MAX_RETRIES` có tôn trọng `retryDelay` của Gemini; mỗi lần thử đều trừ quota.
- Worker: `WORKER_CONCURRENCY=1`, mỗi user tối đa `MAX_RUNNING_JOBS_PER_USER` job cùng lúc ⇒ các user xen kẽ nhau trong hàng đợi.
- API rate limit theo user (`API_RATE_PER_MINUTE`).
- Allowlist email (`ALLOWED_EMAILS` / `ALLOWED_EMAIL_DOMAINS`) ⇒ người lạ có đăng ký cũng không gọi được API.
- Không dịch vụ trả phí nào được bật tự động. Apify chỉ chạy khi admin tự đặt `APIFY_TOKEN`.

## 6. Độ bền với free tier

- **Render ngủ**: job nằm trong Postgres. Khi đang có job, worker tự ping URL public mỗi 4 phút để không bị ngủ giữa chừng; trang Processing cũng polling mỗi 4 giây. Khi hết job, server được phép ngủ (tiết kiệm 750 giờ/tháng).
- **Render restart giữa chừng**: job mất heartbeat > 5 phút được trả lại hàng đợi (resume); video đã xong không bị xử lý lại.
- **Supabase pause 7 ngày**: workflow `keepalive.yml` gọi `/api/health?db=1` mỗi 3 ngày.
- **Disk tạm**: mọi file nằm trong thư mục tạm của từng job; cleanup mỗi giờ xoá keyframe cũ, upload mồ côi, phân tích hết hạn, cache/log cũ.

## 7. Những giới hạn khiến giải pháp KHÔNG miễn phí vô hạn

1. **Gemini free tier** có giới hạn request/phút và request/ngày theo model; vượt ⇒ lỗi 429 đến hết ngày. Muốn nhiều hơn phải bật billing (trả theo token).
2. **Render free** CPU 0.1: FFmpeg chậm (1 video 60s có thể mất 30–90 giây xử lý); 750 giờ/tháng; bandwidth gói Hobby mới đã bị giảm mạnh trong 2026 (xem lại trang pricing) — upload video lên Gemini tính vào băng thông ra.
3. **Supabase free**: 500 MB DB (≈ vài nghìn video đã phân tích), 1 GB storage.
4. **TikTok**: thu thập từ IP server có thể bị chặn bất kỳ lúc nào; không có cách "miễn phí và ổn định" hợp lệ để vượt. Phương án hợp lệ: URL thủ công, upload, import, hoặc dịch vụ scraping trả phí (Apify) do bạn tự bật.
5. Nâng cấp khi cần: Render Starter (~7 USD/tháng, không ngủ), Gemini paid tier, Supabase Pro (25 USD/tháng).
