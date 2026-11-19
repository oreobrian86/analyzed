"""Tự dọn dữ liệu theo retention (chạy mỗi giờ trong worker, hoặc gọi /api/admin/cleanup)."""
from __future__ import annotations

from . import db, services, storage
from .config import settings


def run_cleanup() -> dict:
    stats = {}
    # 1) Analysis hết hạn => xoá file + dữ liệu
    expired = db.all_("select id from analyses where expires_at is not null and expires_at < now() limit 50")
    for a in expired:
        services.delete_analysis(str(a["id"]))
    stats["expired_analyses"] = len(expired)
    # 2) Draft bỏ dở > 1 ngày
    drafts = db.all_("select id from analyses where status='draft' and created_at < now() - interval '1 day' limit 50")
    for a in drafts:
        services.delete_analysis(str(a["id"]))
    stats["stale_drafts"] = len(drafts)
    # 3) Keyframe cũ
    old = db.all_("""select id, keyframe_paths from videos where cardinality(keyframe_paths) > 0
                     and updated_at < now() - make_interval(days => %s) limit 200""", (settings.keyframe_retention_days,))
    storage.delete("keyframes", [p for v in old for p in v["keyframe_paths"]])
    for v in old:
        db.run("update videos set keyframe_paths='{}' where id=%s", (v["id"],))
    stats["keyframes_cleared"] = len(old)
    # 4) File upload còn sót (video lỗi/huỷ) > 6 giờ
    ups = db.all_("""select id, upload_path from videos where upload_path is not null
                     and status in ('failed','cancelled','skipped') and updated_at < now() - interval '6 hours' limit 200""")
    storage.delete("uploads", [v["upload_path"] for v in ups])
    for v in ups:
        db.run("update videos set upload_path=null, upload_bytes=0 where id=%s", (v["id"],))
    stats["orphan_uploads"] = len(ups)
    # 5) Cache, log, usage cũ
    stats["cache"] = db.run("delete from analysis_cache where last_used_at < now() - interval '90 days'")
    stats["logs"] = db.run("delete from job_logs where created_at < now() - make_interval(days => %s)", (settings.retention_days,))
    stats["jobs"] = db.run("delete from jobs where status in ('done','failed','cancelled') and updated_at < now() - interval '7 days'")
    stats["usage"] = db.run("delete from usage_daily where day < current_date - 120")
    return stats
