"""Chạy toàn bộ Stage 2–6 với DB và AI giả lập (kiểm tra logic tổng hợp, chống bịa ref, báo cáo)."""
import importlib
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone


def _stub_missing():
    """Cho phép chạy test khi chưa cài psycopg/httpx/fastapi (CI có cài thì không stub)."""
    def stub(name, **attrs):
        try:
            importlib.import_module(name)
        except ImportError:
            m = types.ModuleType(name)
            m.__dict__.update(attrs)
            sys.modules[name] = m

    stub("psycopg")
    stub("psycopg.rows", dict_row=None)
    stub("psycopg.types")
    stub("psycopg.types.json", Jsonb=lambda x: x)
    stub("psycopg_pool", ConnectionPool=object)
    stub("httpx", HTTPError=Exception, TimeoutException=Exception, Client=object, Response=object)
    stub("fastapi", Depends=lambda *a, **k: None, Header=lambda *a, **k: None,
         HTTPException=type("HTTPException", (Exception,), {}))


_stub_missing()

from app import db  # noqa: E402
from app.ai import registry  # noqa: E402
from app.ai.base import AIResult  # noqa: E402
from app.ai.local_embed import local_embed  # noqa: E402
from app.worker import aggregate_stage, common  # noqa: E402

NOW = datetime.now(timezone.utc)
AID = str(uuid.uuid4())
UID = str(uuid.uuid4())


def _videos():
    vids, vas = [], []
    topics = [("nấu phở bò nước dùng", "tutorial"), ("review điện thoại camera pin", "review")]
    for i in range(12):
        t, fmt = topics[i % 2]
        vid = uuid.uuid4()
        vids.append({"id": vid, "ref": f"V{i + 1:02d}", "caption": t, "url": f"https://www.tiktok.com/@x/video/{i}",
                     "status": "done" if i < 11 else "failed", "views": 1000 + i * 100 if i != 4 else 90000,
                     "likes": 50, "comments": 5, "shares": 1, "posted_at": NOW - timedelta(days=10 + i),
                     "duration_sec": 30, "media_meta": {"cuts_per_minute": 12}})
        if i < 11:
            vas.append({"video_id": vid, "transcript": f"{t} chi tiết", "input_mode": "video",
                        "analysis": {"main_topic": t, "content_format": fmt, "hook": {"type": "question", "text": "Bạn có biết?"},
                                     "cta": {"present": i % 3 == 0}, "content_formula": "hook + 3 bước", "confidence": 0.8}})
    return vids, vas


VIDEOS, VAS = _videos()
WRITES = []


def fake_one(sql, params=None):
    if "from analyses" in sql:
        return {"id": AID, "user_id": UID, "status": "aggregating", "title": "@x", "options": {"handle": "x"}}
    return None


def fake_all(sql, params=None):
    if sql.startswith("select * from videos"):
        return VIDEOS
    if "from video_analyses" in sql:
        return VAS
    return []


def fake_run(sql, params=None):
    WRITES.append((sql, params))
    return 1


def fake_call_json(uid, lim, prompt, **kw):
    if "Stage 2" in prompt:
        d = {"name": "Nhóm", "description": "d", "representative_ref": "V99", "confidence": 0.7}
    elif "Stage 3" in prompt:
        d = {"pillars": [{"name": "Pillar A", "topic_keys": ["T1"], "confidence": 0.8}]}  # cố tình bỏ sót T2
    elif "Stage 4" in prompt:
        d = {"channel_dna": {"summary": "Kênh", "confidence": 90},
             "content_formula": {"formula": "A+B"},
             "insights": [{"conclusion": "Hook câu hỏi", "evidence": ["V05 gấp nhiều lần median"], "video_refs": ["V05", "V77"], "confidence": 0.8}],
             "weaknesses": [{"conclusion": "Thiếu CTA", "video_refs": [], "confidence": 0.9}]}
    else:
        d = {"summary": "s", "opportunities": [], "strategy": [{"conclusion": "Làm thêm review", "evidence": ["e"], "video_refs": ["V02"]}],
             "experiments": [{"idea": "x", "based_on_refs": ["V02", "V88"]}]}
    return AIResult(d, "", "fake", "fake")


def test_aggregate_end_to_end(monkeypatch):
    monkeypatch.setattr(db, "one", fake_one)
    monkeypatch.setattr(db, "all_", fake_all)
    monkeypatch.setattr(db, "run", fake_run)
    monkeypatch.setattr(db, "log", lambda *a, **k: None)
    monkeypatch.setattr(db, "j", lambda x: x)
    monkeypatch.setattr(common, "stage", lambda *a, **k: None)
    monkeypatch.setattr(aggregate_stage, "check_cancel", lambda aid: fake_one("from analyses"))
    monkeypatch.setattr(aggregate_stage, "stage", lambda *a, **k: None)
    monkeypatch.setattr(aggregate_stage, "limits_for", lambda uid: {"max_ai_requests_per_day": 999})
    monkeypatch.setattr(registry, "call_json", fake_call_json)
    monkeypatch.setattr(registry, "embed", lambda uid, lim, texts: (local_embed(texts), "local", "local"))
    monkeypatch.setattr(registry, "describe", lambda: {"video_provider": "fake"})

    aggregate_stage.handle({"analysis_id": AID})

    report_write = next(p for s, p in WRITES if s.strip().startswith("insert into reports"))
    report, md = report_write[2], report_write[3]
    refs_all = {p_ref for p in report["pillars"] for p_ref in p["refs"]}
    assert len(refs_all) == 11                          # không mất video nào khi LLM bỏ sót topic
    assert sum(p["stats"]["video_count"] for p in report["pillars"]) == 11
    ins = report["channel"]["insights"][0]
    assert ins["video_refs"] == ["V05"] and ins["quality_flags"]     # ref bịa V77 bị loại
    assert report["channel"]["weaknesses"][0]["confidence"] <= 0.35  # không ref, không evidence => hạ
    assert report["channel"]["dna"]["confidence"] == 0.9
    assert report["strategy"]["experiments"][0]["based_on_refs"] == ["V02"]
    assert "V05" in report["performance"]["outliers"]["over"]
    assert any("lỗi" in n for n in report["meta"]["data_notes"])
    assert any("local" in n for n in report["meta"]["data_notes"])
    final = next(p for s, p in WRITES if "update analyses set status=%s" in s)
    assert final[0] == "partial"
    assert "## Content Pillars" in md
