"""Stage 1 với FFmpeg thật + video tổng hợp; DB, storage, TikTok, AI được giả lập."""
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.test_aggregate import _stub_missing  # noqa: F401  (đảm bảo stub khi thiếu deps)

from app import db, services, storage  # noqa: E402
from app.ai import registry  # noqa: E402
from app.ai.base import AIResult  # noqa: E402
from app.collectors import ytdlp  # noqa: E402
from app.collectors.base import CollectedVideo  # noqa: E402
from app.worker import video_stage  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="cần ffmpeg")


def _make_video(path: Path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=red:s=360x640:d=2", "-f", "lavfi",
                    "-i", "color=blue:s=360x640:d=2", "-f", "lavfi", "-i", "sine=f=300:d=4",
                    "-filter_complex", "[0][1]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2",
                    "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(path)], check=True)


class FakeVideoAI:
    name = "gemini"
    supports_video = True
    supports_images = True
    supports_transcription = True


def test_process_video_end_to_end(monkeypatch, tmp_path):
    vid, aid, uid = uuid.uuid4(), str(uuid.uuid4()), str(uuid.uuid4())
    row = {"id": vid, "analysis_id": aid, "user_id": uid, "ref": "V01", "status": "pending", "upload_path": None,
           "url": "https://www.tiktok.com/@x/video/123456789", "metrics_source": "none", "posted_at": None,
           "platform_video_id": None, "caption": None}
    writes, uploads, sent = [], [], {}

    def one(sql, params=None):
        if sql.startswith("select * from videos"):
            return row
        if "from analyses" in sql:
            return {"id": aid, "user_id": uid, "status": "processing", "options": {}}
        return None  # cache miss, không trùng

    def run(sql, params=None):
        writes.append((sql, params))
        if "platform_video_id=coalesce" in sql:
            row["platform_video_id"] = params[0]
        return 1

    def fake_call(uid_, lim, prompt, **kw):
        sent["media"] = kw["media"]
        sent["prompt"] = prompt
        return AIResult({"main_topic": "Test", "hook": {"text": "Hi", "type": "question"}, "confidence": 0.7,
                         "transcript": "xin chào"}, "", "m", "gemini", 100, 50)

    def fake_download(info, dest):
        p = dest / "source.mp4"
        _make_video(p)
        return p

    monkeypatch.setattr(db, "one", one)
    monkeypatch.setattr(db, "run", run)
    monkeypatch.setattr(db, "log", lambda *a, **k: None)
    monkeypatch.setattr(db, "j", lambda x: x)
    monkeypatch.setattr(services, "maybe_start_aggregate", lambda aid_: None)
    monkeypatch.setattr(video_stage, "limits_for", lambda u: {"max_ai_requests_per_day": 99, "max_upload_mb": 50})
    monkeypatch.setattr(registry, "provider", lambda purpose="video": FakeVideoAI())
    monkeypatch.setattr(registry, "call_json", fake_call)
    monkeypatch.setattr(storage, "upload_file", lambda b, p, f, c: uploads.append(p))
    monkeypatch.setattr(ytdlp, "fetch_metadata", lambda url: (CollectedVideo(platform_video_id="123456789", caption="cap",
                                                                             views=1000, metrics_source="collector"), {}))
    monkeypatch.setattr(ytdlp, "download", fake_download)

    video_stage.handle({"video_id": vid})

    assert sent["media"][0].kind == "video" and sent["media"][0].mime == "video/mp4"
    assert '"scene_cuts": 1' in sent["prompt"]                    # số đo FFmpeg thật được đưa vào prompt
    assert len(uploads) >= 2 and all(p.endswith(".jpg") for p in uploads)
    final = [p for s, p in writes if s.startswith("update videos set status=%s")][-1]
    assert final[0] == "done"
    assert any(s.strip().startswith("insert into analysis_cache") for s, _ in writes)
    assert any(s.strip().startswith("insert into video_analyses") for s, _ in writes)
