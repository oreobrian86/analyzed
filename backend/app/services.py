"""Logic nghiệp vụ dùng chung giữa API và worker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db, quota, storage
from .collectors.base import CollectedVideo
from .config import settings

TERMINAL_VIDEO = ("done", "failed", "skipped", "cancelled")


def enqueue(user_id: str, analysis_id: str, type_: str, video_id: str | None = None, priority: int = 100) -> None:
    db.run("insert into jobs(user_id, analysis_id, video_id, type, priority, max_attempts) values (%s,%s,%s,%s,%s,%s)",
           (user_id, analysis_id, video_id, type_, priority, settings.job_max_attempts))


def remaining_today(user_id: str, field: str, user_limit: int) -> int:
    used = quota.usage_today(user_id)[field]
    g = db.one("select * from usage_daily where user_id=%s and day=current_date", (quota.GLOBAL_ID,))
    g_used = (g or {}).get(field, 0) or 0
    g_lim = quota.global_limit(field)
    rem = user_limit - used
    if g_lim >= 0:
        rem = min(rem, g_lim - g_used)
    return max(rem, 0)


def insert_videos(analysis: dict, items: list[CollectedVideo], limits: dict) -> tuple[int, int]:
    """Thêm video vào analysis + trừ quota 'videos'. Trả (số thêm, số bị cắt do quota)."""
    uid, aid = analysis["user_id"], str(analysis["id"])
    # loại trùng
    seen, uniq = set(), []
    for it in items:
        key = it.platform_video_id or it.url or it.caption
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    allowed = min(len(uniq), remaining_today(uid, "videos", limits["max_videos_per_day"]))
    cut = len(uniq) - allowed
    uniq = uniq[:allowed]
    if not uniq:
        return 0, cut
    quota.consume(uid, "videos", len(uniq), limits["max_videos_per_day"])
    start = (db.one("select count(*) as n from videos where analysis_id=%s", (aid,)) or {"n": 0})["n"]
    for i, it in enumerate(uniq, start=start + 1):
        row = db.one(
            """insert into videos(user_id, analysis_id, ref, platform_video_id, url, caption, posted_at, duration_sec,
                 views, likes, comments, shares, saves, metrics_source, thumbnail_url)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict do nothing returning id""",
            (uid, aid, f"V{i:02d}", it.platform_video_id, it.url, it.caption, it.posted_at, it.duration_sec,
             it.views, it.likes, it.comments, it.shares, it.saves, it.metrics_source, it.thumbnail_url))
        if row:
            enqueue(uid, aid, "process_video", str(row["id"]))
    refresh_counts(aid)
    return len(uniq), cut


def refresh_counts(analysis_id: str) -> dict:
    return db.one(
        """update analyses a set
             video_count = s.total, videos_done = s.done, videos_failed = s.failed, videos_skipped = s.skipped,
             progress = case when a.status in ('processing','collecting','queued')
                        then 0.05 + 0.75 * (s.done + s.failed + s.skipped)::real / greatest(s.total,1) else a.progress end,
             updated_at = now()
           from (select count(*) total,
                        count(*) filter (where status='done') done,
                        count(*) filter (where status in ('failed','cancelled')) failed,
                        count(*) filter (where status='skipped') skipped
                 from videos where analysis_id=%s) s
           where a.id=%s returning a.*""",
        (analysis_id, analysis_id))


def maybe_start_aggregate(analysis_id: str) -> None:
    a = refresh_counts(analysis_id)
    if not a or a["status"] != "processing":
        return
    pending = db.one("select count(*) n from videos where analysis_id=%s and status <> all(%s)", (analysis_id, list(TERMINAL_VIDEO)))
    if pending["n"] > 0:
        return
    # chuyển trạng thái nguyên tử => chỉ 1 worker tạo job aggregate
    row = db.one("update analyses set status='aggregating', stage='Chuẩn bị tổng hợp kênh', updated_at=now() "
                 "where id=%s and status='processing' returning user_id", (analysis_id,))
    if row:
        if a["videos_done"] == 0:
            db.run("update analyses set status='failed', error=%s, finished_at=now() where id=%s",
                   ("Không có video nào phân tích thành công. Xem log từng video, hoặc thử nhập URL/upload video.", analysis_id))
            return
        enqueue(row["user_id"], analysis_id, "aggregate", priority=50)


def delete_analysis_files(analysis_id: str) -> None:
    vids = db.all_("select upload_path, keyframe_paths from videos where analysis_id=%s", (analysis_id,))
    storage.delete("uploads", [v["upload_path"] for v in vids if v["upload_path"]])
    storage.delete("keyframes", [p for v in vids for p in (v["keyframe_paths"] or [])])


def delete_analysis(analysis_id: str) -> None:
    delete_analysis_files(analysis_id)
    db.run("delete from analyses where id=%s", (analysis_id,))


def expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.retention_days)
