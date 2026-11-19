-- Tạo 2 bucket private. Chạy SAU 001_init.sql (chỉ chạy được trên Supabase vì cần schema storage).
-- uploads   : video người dùng tải lên, bị xoá ngay sau khi xử lý xong (giới hạn 100 MB/file)
-- keyframes : ảnh JPEG nhỏ trích từ video để hiển thị (giới hạn 1 MB/file), xoá theo retention
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('uploads', 'uploads', false, 104857600, array['video/mp4','video/quicktime','video/webm','video/x-matroska']),
  ('keyframes', 'keyframes', false, 1048576, array['image/jpeg'])
on conflict (id) do nothing;
