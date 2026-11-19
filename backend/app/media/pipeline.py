"""Xử lý media trên server cloud: tải video, chuẩn hoá (giảm độ phân giải/bitrate), phát hiện cắt cảnh,
trích keyframe, tách audio. Mọi file nằm trong thư mục tạm và bị xoá khi job kết thúc."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from ..config import settings
from .scenes import cuts_per_minute, parse_showinfo, pick_keyframe_times


class MediaError(Exception):
    pass


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MediaError(f"{cmd[0]} quá thời gian ({timeout}s)")
    return p


def probe(path: Path) -> dict:
    p = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], 60)
    if p.returncode != 0:
        raise MediaError("File không phải video hợp lệ: " + p.stderr[-300:])
    info = json.loads(p.stdout or "{}")
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        raise MediaError("Không tìm thấy luồng video.")
    return {
        "duration": float(info.get("format", {}).get("duration") or v.get("duration") or 0),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "has_audio": a is not None,
        "vcodec": v.get("codec_name"),
        "size": path.stat().st_size,
    }


def normalize(src: Path, dst: Path, max_seconds: int, max_height: int) -> None:
    """Cắt tối đa max_seconds, scale xuống max_height (giữ tỉ lệ), H.264 CRF cao + AAC mono 64k."""
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", str(max_seconds),
        "-vf", f"scale=-2:'min({max_height},ih)'", "-r", "30",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", "-threads", "1", str(dst),
    ]
    p = _run(cmd, 600)
    if p.returncode != 0 or not dst.exists():
        raise MediaError("ffmpeg chuẩn hoá thất bại: " + p.stderr[-400:])


def detect_cuts(path: Path, threshold: float) -> list[float]:
    p = _run(["ffmpeg", "-v", "info", "-threads", "1", "-i", str(path),
              "-vf", f"fps=5,scale=128:-2,select='gt(scene,{threshold})',showinfo",
              "-an", "-f", "null", "-"], 300)
    return parse_showinfo(p.stderr)


def extract_frames(path: Path, times: list[float], outdir: Path, width: int = 360) -> list[Path]:
    out = []
    for i, t in enumerate(times):
        f = outdir / f"kf_{i:02d}_{t:.2f}.jpg"
        p = _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                  "-vf", f"scale={width}:-2", "-q:v", "6", str(f)], 60)
        if p.returncode == 0 and f.exists() and f.stat().st_size > 0:
            out.append(f)
    return out


def extract_audio(path: Path, dst: Path) -> Path | None:
    p = _run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(dst)], 300)
    return dst if p.returncode == 0 and dst.exists() and dst.stat().st_size > 1000 else None


def fast_hash(path: Path) -> str:
    h = hashlib.sha256()
    size = path.stat().st_size
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, 2)
            h.update(f.read())
    return h.hexdigest()[:32]


MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".mkv": "video/x-matroska"}
FAST_CODECS = {"h264", "hevc", "vp9", "av1"}


def prepare(src: Path, workdir: Path) -> tuple[Path, dict, list[Path]]:
    """Trả (video gửi AI, media_meta, keyframes).

    Fast path: video gốc đã ngắn + nhỏ + codec phổ biến => KHÔNG chuyển mã (bước nặng nhất trên CPU yếu),
    gửi thẳng file gốc cho AI. Ngược lại mới chuyển mã xuống độ phân giải thấp.
    """
    info = probe(src)
    if info["duration"] <= 0:
        raise MediaError("Không đọc được thời lượng video.")
    mime = MIME.get(src.suffix.lower())
    fast = (mime is not None and info["vcodec"] in FAST_CODECS
            and info["duration"] <= settings.max_video_seconds + 0.5
            and info["size"] <= settings.inline_video_max_mb * 1024 * 1024)
    if fast:
        out, oinfo = src, info
    else:
        out = workdir / "normalized.mp4"
        normalize(src, out, settings.max_video_seconds, settings.max_height)
        oinfo, mime = probe(out), "video/mp4"
    cuts = detect_cuts(out, settings.scene_threshold)
    times = pick_keyframe_times(cuts, oinfo["duration"], settings.keyframes_per_video)
    frames = extract_frames(out, times, workdir)
    meta = {
        "original_duration": round(info["duration"], 2),
        "analyzed_seconds": round(oinfo["duration"], 2),
        "truncated": info["duration"] > settings.max_video_seconds + 0.5,
        "width": oinfo["width"], "height": oinfo["height"], "has_audio": oinfo["has_audio"],
        "scene_cuts": len(cuts),
        "cut_times": cuts[:200],
        "cuts_per_minute": cuts_per_minute(cuts, oinfo["duration"]),
        "scene_threshold": settings.scene_threshold,
        "keyframe_times": [float(f.stem.split("_")[-1]) for f in frames],
        "sent_bytes": out.stat().st_size,
        "transcoded": not fast,
        "mime": mime,
    }
    return out, meta, frames
