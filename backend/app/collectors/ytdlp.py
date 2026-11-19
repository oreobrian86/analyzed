"""Collector dùng yt-dlp. TikTok thường chặn IP datacenter / đổi cấu trúc trang => có thể lỗi bất cứ lúc nào.
Không vượt CAPTCHA, không dùng cookie đăng nhập, không giả mạo để né chặn."""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from .base import CollectedVideo, CollectorError, to_int, ts


def _opts(**extra) -> dict:
    o = {"quiet": True, "no_warnings": True, "noprogress": True, "socket_timeout": 30, "retries": 2,
         "extractor_retries": 1, "noplaylist": False, "cachedir": False}
    o.update(extra)
    return o


def _from_info(info: dict) -> CollectedVideo:
    has_metrics = info.get("view_count") is not None
    return CollectedVideo(
        url=info.get("webpage_url") or info.get("url"),
        platform_video_id=str(info.get("id")) if info.get("id") else None,
        caption=info.get("description") or info.get("title"),
        posted_at=ts(info.get("timestamp") or info.get("upload_date")),
        duration_sec=info.get("duration"),
        views=to_int(info.get("view_count")),
        likes=to_int(info.get("like_count")),
        comments=to_int(info.get("comment_count")),
        shares=to_int(info.get("repost_count")),
        saves=to_int(info.get("save_count")),
        thumbnail_url=info.get("thumbnail"),
        metrics_source="collector" if has_metrics else "none",
    )


def list_profile(handle: str, limit: int) -> list[CollectedVideo]:
    import yt_dlp

    url = f"https://www.tiktok.com/@{handle}"
    try:
        with yt_dlp.YoutubeDL(_opts(extract_flat="in_playlist", playlistend=limit)) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # yt_dlp.utils.DownloadError và các lỗi khác
        raise CollectorError(f"yt-dlp không lấy được danh sách video của @{handle}: {str(e)[:300]}")
    entries = [e for e in (info or {}).get("entries") or [] if e]
    if not entries:
        raise CollectorError(f"Không tìm thấy video công khai nào của @{handle} (có thể bị TikTok chặn từ server).")
    out = []
    for e in entries[:limit]:
        vid = str(e.get("id") or "")
        out.append(CollectedVideo(url=e.get("url") or e.get("webpage_url") or f"https://www.tiktok.com/@{handle}/video/{vid}",
                                  platform_video_id=vid or None, caption=e.get("description") or e.get("title"),
                                  posted_at=ts(e.get("timestamp")), views=to_int(e.get("view_count")),
                                  metrics_source="collector" if e.get("view_count") is not None else "none"))
    return out


def fetch_metadata(url: str) -> tuple[CollectedVideo, dict]:
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL(_opts(noplaylist=True)) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise CollectorError(f"Không đọc được metadata video: {str(e)[:300]}")
    return _from_info(info), info


def download(info: dict, dest_dir: Path) -> Path:
    """Tải file video (gọi yt-dlp lại từ URL). Ưu tiên H.264 ≤720p: nhẹ, FFmpeg xử lý nhanh."""
    import yt_dlp

    url = info.get("webpage_url") or info.get("original_url") or info.get("url")
    opts = _opts(
        noplaylist=True,
        outtmpl=str(dest_dir / "source.%(ext)s"),
        format="best[vcodec^=h264][height<=720]/best[vcodec^=avc][height<=720]/best[height<=720]/best",
        max_filesize=settings.max_download_mb * 1024 * 1024,
        overwrites=True,
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as e:
        raise CollectorError(f"Tải video thất bại: {str(e)[:300]}") from e
    files = [p for p in dest_dir.glob("source*") if p.is_file() and p.suffix not in (".part", ".ytdl", ".jpg", ".webp", ".json")]
    if not files:
        raise CollectorError(f"Không tải được video (có thể vượt {settings.max_download_mb} MB hoặc bị chặn).")
    return max(files, key=lambda p: p.stat().st_size)
