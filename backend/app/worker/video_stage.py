"""Stage 1: xử lý + phân tích từng video."""
from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime
from pathlib import Path

from .. import db, services, storage
from ..ai import prompts, registry
from ..ai.base import AIError, MediaPart
from ..analysis import normalize
from ..collectors import ytdlp
from ..collectors.base import CollectorError
from ..config import settings
from ..media import pipeline
from ..quota import limits_for
from .common import Cancelled, check_cancel


def _cache_key(kind: str, ident: str, mode: str) -> str:
    p = registry.provider("video")
    model = settings.gemini_video_model if p.name == "gemini" else (settings.openai_vision_model or settings.openai_text_model)
    return hashlib.sha256(f"{kind}:{ident}|{p.name}:{model}|{mode}|{prompts.PROMPT_VERSION}|{settings.report_language}".encode()).hexdigest()


def _stage(vid: str, stage: str) -> None:
    db.run("update videos set stage=%s, updated_at=now() where id=%s", (stage, vid))


def _save_result(v: dict, data: dict, *, provider: str, model: str, mode: str, from_cache: bool) -> None:
    a = normalize.video_analysis(data)
    db.run(
        """insert into video_analyses(video_id, user_id, transcript, ocr_text, analysis, provider, model, prompt_version,
             input_mode, confidence, from_cache) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (video_id) do update set transcript=excluded.transcript, ocr_text=excluded.ocr_text,
             analysis=excluded.analysis, provider=excluded.provider, model=excluded.model,
             prompt_version=excluded.prompt_version, input_mode=excluded.input_mode,
             confidence=excluded.confidence, from_cache=excluded.from_cache, created_at=now()""",
        (v["id"], v["user_id"], a.get("transcript"), a.get("ocr_text"), db.j(a), provider, model,
         prompts.PROMPT_VERSION, mode, a["confidence"], from_cache))


def _in_range(posted_at, opts: dict) -> bool:
    if not posted_at:
        return True
    d = posted_at.date() if isinstance(posted_at, datetime) else None
    if not d:
        return True
    f, t = opts.get("date_from"), opts.get("date_to")
    if f and str(d) < f:
        return False
    if t and str(d) > t:
        return False
    return True


def _finish(v: dict, status: str, error: str | None = None, **fields) -> None:
    sets = ["status=%s", "error=%s", "stage=null", "updated_at=now()"]
    vals: list = [status, error]
    for k, val in fields.items():
        sets.append(f"{k}=%s")
        vals.append(val)
    db.run(f"update videos set {', '.join(sets)} where id=%s", (*vals, v["id"]))
    services.maybe_start_aggregate(str(v["analysis_id"]))


def handle(job: dict) -> None:
    v = db.one("select * from videos where id=%s", (job["video_id"],))
    if not v:
        return
    aid = str(v["analysis_id"])
    if v["status"] in services.TERMINAL_VIDEO:  # đã xong (vd job được resume) => không xử lý lại
        services.maybe_start_aggregate(aid)
        return
    a = check_cancel(aid)
    lim = limits_for(v["user_id"])
    db.run("update videos set status='processing', updated_at=now() where id=%s", (v["id"],))
    db.run("update analyses set stage=%s, updated_at=now() where id=%s", (f"Stage 1: phân tích video {v['ref']}", aid))
    vp = registry.provider("video")
    mode = "video" if vp.supports_video else "frames+transcript"

    with tempfile.TemporaryDirectory(prefix="tci_") as tdir:
        td = Path(tdir)
        src: Path | None = None
        info: dict | None = None
        cache_key = None

        if v["upload_path"]:
            _stage(v["id"], "Tải file upload từ storage")
            src = td / "source.mp4"
            storage.download_to("uploads", v["upload_path"], src, lim["max_upload_mb"] * 1024 * 1024)
            h = pipeline.fast_hash(src)
            db.run("update videos set content_hash=%s where id=%s", (h, v["id"]))
            cache_key = _cache_key("upload", h, mode)
        elif v["url"]:
            _stage(v["id"], "Đọc metadata TikTok")
            try:
                meta, info = ytdlp.fetch_metadata(v["url"])
            except CollectorError as e:
                if v["metrics_source"] == "user_import":
                    db.log(aid, f"{v['ref']}: không tải được video ({e}); giữ metrics import cho phân tích hiệu suất.", "warn", str(v["id"]))
                    _finish(v, "skipped", "Không tải được video — chỉ dùng metrics đã import, không phân tích nội dung.")
                    return
                raise
            keep_import = v["metrics_source"] == "user_import"
            dup = db.one("select ref from videos where analysis_id=%s and platform_video_id=%s and id<>%s",
                         (aid, meta.platform_video_id, v["id"])) if meta.platform_video_id else None
            if dup:
                _finish(v, "skipped", f"Trùng với {dup['ref']} trong cùng phân tích.")
                return
            db.run(
                """update videos set platform_video_id=coalesce(platform_video_id,%s), caption=coalesce(%s,caption),
                     posted_at=coalesce(%s,posted_at), duration_sec=coalesce(%s,duration_sec), thumbnail_url=%s,
                     views=case when %s then views else coalesce(%s,views) end,
                     likes=case when %s then likes else coalesce(%s,likes) end,
                     comments=case when %s then comments else coalesce(%s,comments) end,
                     shares=case when %s then shares else coalesce(%s,shares) end,
                     saves=case when %s then saves else coalesce(%s,saves) end,
                     metrics_source=case when %s then metrics_source else %s end
                   where id=%s""",
                (meta.platform_video_id, meta.caption, meta.posted_at, meta.duration_sec, meta.thumbnail_url,
                 keep_import, meta.views, keep_import, meta.likes, keep_import, meta.comments, keep_import, meta.shares,
                 keep_import, meta.saves, keep_import, meta.metrics_source, v["id"]))
            v = db.one("select * from videos where id=%s", (v["id"],))
            if not _in_range(v["posted_at"], (a.get("options") or {})):
                _finish(v, "skipped", "Ngoài khoảng thời gian đã chọn.")
                return
            if v["platform_video_id"]:
                cache_key = _cache_key("tiktok", v["platform_video_id"], mode)
        else:
            _finish(v, "skipped", "Không có URL hoặc file video — không thể phân tích nội dung.")
            return

        if cache_key:
            hit = db.one("update analysis_cache set last_used_at=now() where cache_key=%s returning *", (cache_key,))
            if hit:
                _save_result(v, hit["analysis"], provider=hit["provider"], model=hit["model"], mode=hit["input_mode"], from_cache=True)
                db.log(aid, f"{v['ref']}: dùng kết quả cache (video đã phân tích trước đó, không tốn AI quota).", "info", str(v["id"]))
                _finish(v, "done", media_meta=db.j(hit.get("media_meta") or {}))
                _cleanup_upload(v)
                return

        check_cancel(aid)
        if src is None:
            _stage(v["id"], "Tải video")
            src = ytdlp.download(info, td)
        _stage(v["id"], "FFmpeg: chuẩn hoá, phát hiện cắt cảnh, keyframe")
        norm, media_meta, frames = pipeline.prepare(src, td)
        src.unlink(missing_ok=True)

        kf_paths = []
        for f in frames:
            path = f"{v['user_id']}/{aid}/{v['id']}/{f.name}"
            try:
                storage.upload_file("keyframes", path, f, "image/jpeg")
                kf_paths.append(path)
            except Exception:
                pass

        check_cancel(aid)
        _stage(v["id"], f"AI phân tích ({mode})")
        transcript_hint = None
        if mode == "video":
            media = [MediaPart("video", norm, "video/mp4")]
        else:
            media = [MediaPart("image", f, "image/jpeg") for f in frames] if vp.supports_images else []
            if vp.supports_transcription and media_meta.get("has_audio"):
                audio = pipeline.extract_audio(norm, td / "audio.mp3")
                if audio:
                    from .. import quota
                    quota.consume(v["user_id"], "ai_requests", 1, lim["max_ai_requests_per_day"])
                    transcript_hint = vp.transcribe(audio)
            if not media and not transcript_hint:
                raise AIError("Provider hiện tại không xử lý được ảnh hay audio — không thể phân tích nội dung thực tế.")
        res = registry.call_json(
            v["user_id"], lim["max_ai_requests_per_day"],
            prompts.video_prompt(v, media_meta, mode, transcript_hint),
            system=prompts.system(settings.report_language), media=media, purpose="video", max_output_tokens=8192)
        data = res.data
        if transcript_hint and not data.get("transcript"):
            data["transcript"] = transcript_hint
        _save_result(v, data, provider=res.provider, model=res.model, mode=mode, from_cache=False)
        if cache_key:
            db.run("""insert into analysis_cache(cache_key, transcript, ocr_text, analysis, media_meta, provider, model, prompt_version, input_mode)
                      values (%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (cache_key) do nothing""",
                   (cache_key, data.get("transcript"), data.get("ocr_text"), db.j(normalize.video_analysis(data)),
                    db.j(media_meta), res.provider, res.model, prompts.PROMPT_VERSION, mode))
        db.log(aid, f"{v['ref']}: phân tích xong ({res.input_tokens} in / {res.output_tokens} out tokens).", "info", str(v["id"]))
        _finish(v, "done", media_meta=db.j(media_meta), keyframe_paths=kf_paths)
        _cleanup_upload(v)


def _cleanup_upload(v: dict) -> None:
    if v.get("upload_path"):
        storage.delete("uploads", [v["upload_path"]])
        db.run("update videos set upload_path=null where id=%s", (v["id"],))


def on_final_failure(job: dict, error: str) -> None:
    v = db.one("select * from videos where id=%s", (job["video_id"],))
    if not v or v["status"] in services.TERMINAL_VIDEO:
        return
    db.log(str(v["analysis_id"]), f"{v['ref']}: THẤT BẠI — {error}", "error", str(v["id"]))
    _finish(v, "failed", error[:1000])


__all__ = ["handle", "on_final_failure", "Cancelled"]
