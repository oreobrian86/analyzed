"""FastAPI app: REST API + khởi động worker nền."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, quota, services, storage
from .ai import registry
from .auth import User, admin_user
from .collectors import apify, importer
from .collectors.base import CollectorError, parse_handle
from .config import settings
from .quota import QuotaExceeded, limits_for, rate_limited_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")
MISSING = settings.missing_required()
ACTIVE = ["draft", "queued", "collecting", "processing", "aggregating"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MISSING:
        log.error("Thiếu biến môi trường: %s — API chạy ở chế độ hạn chế, worker KHÔNG chạy.", ", ".join(MISSING))
    elif settings.run_worker:
        from .worker.runner import worker
        worker.start()
    yield


app = FastAPI(title="TikTok Channel Intelligence API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX") or None,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _owned(analysis_id: str, user: User) -> dict:
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(404, "Không tìm thấy.")
    a = db.one("select * from analyses where id=%s", (analysis_id,))
    if not a or (str(a["user_id"]) != user.id and not user.is_admin):
        raise HTTPException(404, "Không tìm thấy phân tích.")
    return a


# ---------------------------------------------------------------- public
@app.get("/api/health")
def health(db_check: bool = Query(False, alias="db")):
    out = {"ok": not MISSING, "missing_env": MISSING}
    if not MISSING and settings.run_worker:
        from .worker.runner import worker
        out["worker"] = worker.status()
    if db_check and not MISSING:
        try:
            out["db"] = bool(db.one("select 1 as x"))
        except Exception as e:
            out["db"] = False
            out["db_error"] = str(e)[:200]
    return out


@app.get("/api/config")
def public_config():
    return {
        "default_limits": settings.default_limits,
        "ai": registry.describe(),
        "collectors": ["yt-dlp"] + (["apify"] if apify.enabled() else []) + ["urls", "upload", "import"],
        "max_video_seconds": settings.max_video_seconds,
        "retention_days": settings.retention_days,
        "keyframe_retention_days": settings.keyframe_retention_days,
        "report_language": settings.report_language,
    }


# ---------------------------------------------------------------- me
@app.get("/api/me")
def me(user: User = Depends(rate_limited_user)):
    lim = limits_for(user.id, user.quota_overrides, user.role)
    active = db.one("select count(*) n from analyses where user_id=%s and status = any(%s)", (user.id, ACTIVE))["n"]
    return {"id": user.id, "email": user.email, "role": user.role, "limits": lim, "usage_today": quota.usage_today(user.id),
            "storage_used_bytes": quota.storage_used_bytes(user.id), "active_analyses": active}


@app.delete("/api/me/data")
def delete_my_data(user: User = Depends(rate_limited_user)):
    rows = db.all_("select id from analyses where user_id=%s", (user.id,))
    for r in rows:
        services.delete_analysis(str(r["id"]))
    db.run("delete from channels where user_id=%s", (user.id,))
    return {"deleted_analyses": len(rows)}


# ---------------------------------------------------------------- analyses
class CreateAnalysis(BaseModel):
    source: Literal["profile", "urls", "upload", "import"]
    profile_url: str | None = None
    urls: str | None = None
    import_text: str | None = Field(default=None, max_length=2_000_000)
    max_videos: int = Field(default=10, ge=1, le=500)
    date_from: str | None = None
    date_to: str | None = None
    title: str | None = Field(default=None, max_length=120)


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.post("/api/analyses")
def create_analysis(body: CreateAnalysis, user: User = Depends(rate_limited_user)):
    if MISSING:
        raise HTTPException(503, "Server chưa cấu hình đủ biến môi trường: " + ", ".join(MISSING))
    lim = limits_for(user.id, user.quota_overrides, user.role)
    active = db.one("select count(*) n from analyses where user_id=%s and status = any(%s)", (user.id, ACTIVE))["n"]
    if active >= lim["max_active_analyses"]:
        raise HTTPException(429, f"Bạn đang có {active} phân tích chưa xong (tối đa {lim['max_active_analyses']}). Đợi xong hoặc huỷ bớt.")
    max_videos = min(body.max_videos, lim["max_videos_per_analysis"])
    for d in (body.date_from, body.date_to):
        if d and not _DATE.match(d):
            raise HTTPException(400, "Ngày phải có dạng YYYY-MM-DD.")

    items = None
    handle = None
    try:
        if body.source == "profile":
            handle = parse_handle(body.profile_url or "")
            if not handle:
                raise HTTPException(400, "Không nhận ra profile. Dạng hợp lệ: https://www.tiktok.com/@tenkenh hoặc @tenkenh")
        elif body.source == "urls":
            items = importer.parse_urls(body.urls or "", max_videos)
        elif body.source == "import":
            items = importer.parse_import(body.import_text or "", max_videos)
    except CollectorError as e:
        raise HTTPException(400, str(e))

    try:
        quota.consume(user.id, "analyses", 1, lim["max_analyses_per_day"])
    except QuotaExceeded as e:
        raise HTTPException(429, str(e))

    channel_id = None
    if handle:
        channel_id = db.one("""insert into channels(user_id, handle, profile_url) values (%s,%s,%s)
                               on conflict (user_id, platform, handle) do update set profile_url=excluded.profile_url returning id""",
                            (user.id, handle, f"https://www.tiktok.com/@{handle}"))["id"]
    status = {"profile": "queued", "upload": "draft"}.get(body.source, "processing")
    opts = {"handle": handle, "max_videos": max_videos, "date_from": body.date_from, "date_to": body.date_to}
    title = body.title or (f"@{handle}" if handle else {"urls": "Danh sách URL", "import": "Dữ liệu import", "upload": "Video upload"}[body.source])
    a = db.one("""insert into analyses(user_id, channel_id, title, source, status, options, stage)
                  values (%s,%s,%s,%s,%s,%s,%s) returning *""",
               (user.id, channel_id, title, body.source, status, db.j(opts), "Đang chờ trong hàng đợi"))
    aid = str(a["id"])
    db.log(aid, f"Tạo phân tích ({body.source}), tối đa {max_videos} video.")
    if body.source == "profile":
        services.enqueue(user.id, aid, "collect", priority=10)
    elif items is not None:
        added, cut = services.insert_videos(a, items, lim)
        if cut:
            db.log(aid, f"{cut} video bị bỏ qua do giới hạn video/ngày.", "warn")
        if added == 0:
            db.run("update analyses set status='failed', error=%s where id=%s", ("Đã hết quota video hôm nay.", aid))
    return db.one("select * from analyses where id=%s", (aid,))


@app.get("/api/analyses")
def list_analyses(user: User = Depends(rate_limited_user)):
    return db.all_("""select a.id, a.title, a.source, a.status, a.stage, a.progress, a.video_count, a.videos_done,
                      a.videos_failed, a.videos_skipped, a.created_at, a.finished_at, a.expires_at, c.handle,
                      exists(select 1 from reports r where r.analysis_id=a.id) as has_report
                      from analyses a left join channels c on c.id=a.channel_id
                      where a.user_id=%s order by a.created_at desc limit 200""", (user.id,))


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str, user: User = Depends(rate_limited_user)):
    a = _owned(analysis_id, user)
    videos = db.all_("""select v.id, v.ref, v.url, v.caption, v.status, v.stage, v.error, v.views, v.posted_at,
                        (select last_error from jobs j where j.video_id=v.id order by j.id desc limit 1) as last_job_error,
                        (select attempts from jobs j where j.video_id=v.id order by j.id desc limit 1) as attempts
                        from videos v where v.analysis_id=%s order by v.ref""", (analysis_id,))
    jobs = db.one("""select count(*) filter (where status='queued') queued, count(*) filter (where status='running') running
                     from jobs where analysis_id=%s""", (analysis_id,))
    ahead = db.one("select count(*) n from jobs where status='queued' and id < coalesce((select min(id) from jobs where analysis_id=%s and status='queued'), 0)",
                   (analysis_id,))["n"]
    return {**a, "videos": videos, "jobs": jobs, "queue_ahead": ahead}


@app.get("/api/analyses/{analysis_id}/logs")
def get_logs(analysis_id: str, after_id: int = 0, user: User = Depends(rate_limited_user)):
    _owned(analysis_id, user)
    return db.all_("select id, video_id, level, message, created_at from job_logs where analysis_id=%s and id>%s order by id limit 300",
                   (analysis_id, after_id))


@app.post("/api/analyses/{analysis_id}/uploads")
def upload_video(analysis_id: str, file: UploadFile = File(...), user: User = Depends(rate_limited_user)):
    a = _owned(analysis_id, user)
    if a["status"] != "draft":
        raise HTTPException(400, "Chỉ upload được khi phân tích đang ở trạng thái nháp.")
    lim = limits_for(user.id, user.quota_overrides, user.role)
    n = db.one("select count(*) n from videos where analysis_id=%s", (analysis_id,))["n"]
    if n >= (a["options"] or {}).get("max_videos", lim["max_videos_per_analysis"]):
        raise HTTPException(400, "Đã đủ số video tối đa cho phân tích này.")
    if not (file.content_type or "").startswith("video/"):
        raise HTTPException(400, "Chỉ nhận file video (mp4, mov, webm).")
    max_bytes = lim["max_upload_mb"] * 1024 * 1024
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "v.mp4").suffix[:8]) as tmp:
        size = 0
        while chunk := file.file.read(1024 * 512):
            size += len(chunk)
            if size > max_bytes:
                tmp.close()
                os.unlink(tmp.name)
                raise HTTPException(413, f"File vượt {lim['max_upload_mb']} MB.")
            tmp.write(chunk)
    try:
        if quota.storage_used_bytes(user.id) + size > lim["max_storage_mb"] * 1024 * 1024:
            raise HTTPException(413, "Vượt dung lượng lưu trữ tạm của bạn. Đợi các video đang chờ xử lý xong.")
        try:
            quota.consume(user.id, "upload_bytes", size, lim["max_upload_bytes_per_day_mb"] * 1024 * 1024)
        except QuotaExceeded as e:
            raise HTTPException(429, str(e))
        vid = uuid.uuid4()
        path = f"{user.id}/{analysis_id}/{vid}{Path(tmp.name).suffix or '.mp4'}"
        storage.upload_file("uploads", path, Path(tmp.name), file.content_type)
        ref = f"V{n + 1:02d}"
        db.run("""insert into videos(id, user_id, analysis_id, ref, caption, upload_path, upload_bytes, metrics_source)
                  values (%s,%s,%s,%s,%s,%s,%s,'none')""", (vid, user.id, analysis_id, ref, file.filename, path, size))
        return {"id": str(vid), "ref": ref, "bytes": size}
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@app.post("/api/analyses/{analysis_id}/start")
def start_analysis(analysis_id: str, user: User = Depends(rate_limited_user)):
    a = _owned(analysis_id, user)
    if a["status"] != "draft":
        raise HTTPException(400, "Phân tích đã được bắt đầu.")
    vids = db.all_("select id from videos where analysis_id=%s", (analysis_id,))
    if not vids:
        raise HTTPException(400, "Chưa có video nào được upload.")
    lim = limits_for(user.id, user.quota_overrides, user.role)
    try:
        quota.consume(user.id, "videos", len(vids), lim["max_videos_per_day"])
    except QuotaExceeded as e:
        raise HTTPException(429, str(e))
    db.run("update analyses set status='processing', updated_at=now() where id=%s", (analysis_id,))
    for v in vids:
        services.enqueue(user.id, analysis_id, "process_video", str(v["id"]))
    services.refresh_counts(analysis_id)
    return {"ok": True}


@app.post("/api/analyses/{analysis_id}/cancel")
def cancel_analysis(analysis_id: str, user: User = Depends(rate_limited_user)):
    a = _owned(analysis_id, user)
    if a["status"] in ("done", "partial", "failed", "cancelled"):
        return {"ok": True, "status": a["status"]}
    db.run("update analyses set status='cancelled', stage='Đã huỷ', finished_at=now() where id=%s", (analysis_id,))
    db.run("update jobs set status='cancelled', updated_at=now() where analysis_id=%s and status='queued'", (analysis_id,))
    db.run("update videos set status='cancelled' where analysis_id=%s and status='pending'", (analysis_id,))
    if a["status"] == "draft":
        services.delete_analysis_files(analysis_id)
    db.log(analysis_id, "Người dùng huỷ phân tích.", "warn")
    return {"ok": True}


def _requeue_video(user: User, a: dict, video_id: str) -> None:
    db.run("update videos set status='pending', error=null, stage=null where id=%s", (video_id,))
    services.enqueue(str(a["user_id"]), str(a["id"]), "process_video", video_id)


@app.post("/api/analyses/{analysis_id}/retry")
def retry_analysis(analysis_id: str, user: User = Depends(rate_limited_user)):
    a = _owned(analysis_id, user)
    if a["status"] in ACTIVE:
        raise HTTPException(400, "Phân tích vẫn đang chạy.")
    if db.one("select count(*) n from analyses where user_id=%s and status = any(%s)", (user.id, ACTIVE))["n"] >= \
            limits_for(user.id, user.quota_overrides, user.role)["max_active_analyses"]:
        raise HTTPException(429, "Bạn đang có phân tích khác chạy. Đợi xong rồi retry.")
    failed = db.all_("select id from videos where analysis_id=%s and status in ('failed','cancelled')", (analysis_id,))
    total = db.one("select count(*) n from videos where analysis_id=%s", (analysis_id,))["n"]
    if total == 0 and a["source"] == "profile":
        db.run("update analyses set status='queued', error=null, finished_at=null where id=%s", (analysis_id,))
        services.enqueue(user.id, analysis_id, "collect", priority=10)
        return {"retried": "collect"}
    if failed:
        db.run("update analyses set status='processing', error=null, finished_at=null where id=%s", (analysis_id,))
        for v in failed:
            _requeue_video(user, a, str(v["id"]))
        services.refresh_counts(analysis_id)
        return {"retried": "videos", "count": len(failed)}
    db.run("update analyses set status='aggregating', error=null, finished_at=null where id=%s", (analysis_id,))
    services.enqueue(user.id, analysis_id, "aggregate", priority=50)
    return {"retried": "aggregate"}


@app.delete("/api/analyses/{analysis_id}")
def delete_analysis(analysis_id: str, user: User = Depends(rate_limited_user)):
    _owned(analysis_id, user)
    services.delete_analysis(analysis_id)
    return {"ok": True}


@app.get("/api/analyses/{analysis_id}/report")
def get_report(analysis_id: str, user: User = Depends(rate_limited_user)):
    _owned(analysis_id, user)
    r = db.one("select report, markdown, created_at from reports where analysis_id=%s", (analysis_id,))
    if not r:
        raise HTTPException(404, "Chưa có báo cáo.")
    return r


# ---------------------------------------------------------------- videos
@app.get("/api/videos")
def list_videos(analysis_id: str | None = None, q: str | None = None, user: User = Depends(rate_limited_user)):
    params: list = [user.id]
    where = "v.user_id=%s"
    if analysis_id:
        where += " and v.analysis_id=%s"
        params.append(analysis_id)
    if q:
        where += " and (v.caption ilike %s or va.analysis->>'main_topic' ilike %s)"
        params += [f"%{q}%", f"%{q}%"]
    rows = db.all_(f"""select v.id, v.ref, v.analysis_id, v.url, v.caption, v.status, v.views, v.likes, v.comments, v.shares,
                       v.posted_at, v.thumbnail_url, v.keyframe_paths, a.title as analysis_title,
                       va.analysis->>'main_topic' as main_topic, va.analysis->>'content_format' as content_format,
                       va.analysis->'hook'->>'type' as hook_type, va.confidence
                       from videos v join analyses a on a.id=v.analysis_id
                       left join video_analyses va on va.video_id=v.id
                       where {where} order by v.created_at desc, v.ref limit 300""", tuple(params))
    firsts = [r["keyframe_paths"][0] for r in rows if r["keyframe_paths"]]
    signed = storage.signed_urls("keyframes", firsts, 3600)
    for r in rows:
        kp = r.pop("keyframe_paths") or []
        r["preview_url"] = signed.get(kp[0]) if kp else None
    return rows


@app.get("/api/videos/{video_id}")
def get_video(video_id: str, user: User = Depends(rate_limited_user)):
    try:
        uuid.UUID(video_id)
    except ValueError:
        raise HTTPException(404, "Không tìm thấy.")
    v = db.one("select * from videos where id=%s", (video_id,))
    if not v or (str(v["user_id"]) != user.id and not user.is_admin):
        raise HTTPException(404, "Không tìm thấy video.")
    va = db.one("select * from video_analyses where video_id=%s", (video_id,))
    signed = storage.signed_urls("keyframes", v["keyframe_paths"] or [], 3600)
    v["keyframes"] = [{"path": p, "url": signed.get(p), "time": float(p.rsplit("_", 1)[-1].removesuffix(".jpg"))}
                      for p in v.pop("keyframe_paths") or []]
    v.pop("upload_path", None)
    jobs = db.all_("select id, status, attempts, last_error, updated_at from jobs where video_id=%s order by id desc limit 5", (video_id,))
    return {"video": v, "analysis": va, "jobs": jobs}


@app.post("/api/videos/{video_id}/retry")
def retry_video(video_id: str, user: User = Depends(rate_limited_user)):
    v = db.one("select * from videos where id=%s", (video_id,))
    if not v or str(v["user_id"]) != user.id:
        raise HTTPException(404, "Không tìm thấy video.")
    if v["status"] not in ("failed", "cancelled", "skipped"):
        raise HTTPException(400, "Chỉ retry được video lỗi / bị huỷ / bị bỏ qua.")
    a = db.one("select * from analyses where id=%s", (v["analysis_id"],))
    if a["status"] in ("collecting", "aggregating", "draft", "queued"):
        raise HTTPException(400, "Phân tích đang ở bước khác, thử lại sau.")
    _requeue_video(user, a, video_id)
    db.run("update analyses set status='processing', error=null, finished_at=null where id=%s", (a["id"],))
    services.refresh_counts(str(a["id"]))
    return {"ok": True}


# ---------------------------------------------------------------- admin
@app.get("/api/admin/overview")
def admin_overview(user: User = Depends(admin_user)):
    return {
        "global_usage_today": quota.usage_today(quota.GLOBAL_ID),
        "global_limits": {"ai_requests": settings.global_max_ai_requests_per_day, "videos": settings.global_max_videos_per_day,
                          "upload_mb": settings.global_max_upload_mb_per_day},
        "queue": db.all_("select type, status, count(*) n from jobs group by type, status order by type, status"),
        "users": db.all_("""select p.email, p.role, u.analyses, u.videos, u.ai_requests from profiles p
                            left join usage_daily u on u.user_id=p.id and u.day=current_date order by u.ai_requests desc nulls last limit 100"""),
    }


@app.post("/api/admin/cleanup")
def admin_cleanup(user: User = Depends(admin_user)):
    from .cleanup import run_cleanup
    return run_cleanup()
