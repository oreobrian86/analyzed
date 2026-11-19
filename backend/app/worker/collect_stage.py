"""Thu thập danh sách video của profile. Lỗi collector KHÔNG làm hỏng hệ thống: analysis chuyển 'failed'
kèm hướng dẫn dùng phương án thay thế (URL / upload / import)."""
from __future__ import annotations

from .. import db, services
from ..collectors import apify, ytdlp
from ..collectors.base import CollectorError
from ..quota import limits_for
from .common import check_cancel, stage

FALLBACK_HINT = ("Không thu thập tự động được profile này từ server cloud (TikTok thường chặn IP máy chủ hoặc đổi "
                 "cấu trúc trang). Hãy tạo phân tích mới bằng: dán danh sách URL video, upload file video, "
                 "hoặc import CSV/JSON.")


def handle(job: dict) -> None:
    aid = str(job["analysis_id"])
    a = check_cancel(aid)
    db.run("update analyses set status='collecting', updated_at=now() where id=%s", (aid,))
    opts = a.get("options") or {}
    handle_ = opts.get("handle")
    limit = int(opts.get("max_videos") or 10)
    stage(aid, f"Thu thập danh sách video của @{handle_}", 0.02)

    collectors = [("yt-dlp", ytdlp.list_profile)]
    if apify.enabled():
        collectors.append(("apify", apify.list_profile))
    errors = []
    items = None
    for name, fn in collectors:
        try:
            items = fn(handle_, limit)
            db.log(aid, f"Collector {name}: tìm thấy {len(items)} video.")
            break
        except CollectorError as e:
            errors.append(f"{name}: {e}")
            db.log(aid, f"Collector {name} lỗi: {e}", "warn")
    if not items:
        if job["attempts"] < 2:
            raise CollectorError("; ".join(errors))  # thử lại 1 lần sau (lỗi có thể tạm thời)
        db.run("update analyses set status='failed', error=%s, finished_at=now(), updated_at=now() where id=%s",
               (FALLBACK_HINT + " Chi tiết: " + " | ".join(errors)[:800], aid))
        return
    added, cut = services.insert_videos(a, items, limits_for(a["user_id"]))
    if cut:
        db.log(aid, f"{cut} video bị bỏ qua vì đã đạt giới hạn số video/ngày.", "warn")
    if added == 0:
        db.run("update analyses set status='failed', error=%s, finished_at=now() where id=%s",
               ("Đã đạt giới hạn số video phân tích hôm nay.", aid))
        return
    db.run("update analyses set status='processing', updated_at=now() where id=%s and status='collecting'", (aid,))
    stage(aid, f"Đã xếp hàng {added} video để xử lý", 0.05)


def on_final_failure(job: dict, error: str) -> None:
    db.run("update analyses set status='failed', error=%s, finished_at=now() where id=%s and status not in ('cancelled','done')",
           (FALLBACK_HINT + " Chi tiết: " + error[:600], job["analysis_id"]))
