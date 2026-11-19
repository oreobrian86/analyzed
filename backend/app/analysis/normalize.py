"""Chuẩn hoá output của LLM: ép kiểu, giới hạn confidence, loại bỏ video ref không tồn tại (chống bịa)."""
from __future__ import annotations

from typing import Any

INSIGHT_FIELDS = ("conclusion", "evidence", "video_refs", "observed_data", "pattern", "hypothesis", "recommendation", "confidence")


def conf(v: Any, default: float = 0.5) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f > 1 and f <= 100:
        f = f / 100
    return round(min(max(f, 0.0), 1.0), 2)


def as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [v]


def as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        import json
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def video_analysis(d: dict) -> dict:
    out = dict(d or {})
    for k in ("subtopics", "retention_mechanisms", "strengths", "weaknesses", "evidence", "data_limitations", "scene_structure"):
        out[k] = as_list(out.get(k))
    for k in ("main_topic", "content_format", "target_audience", "storytelling", "narrative_structure", "visual_style",
              "editing_rhythm", "ending", "content_formula", "transcript", "ocr_text"):
        out[k] = as_str(out.get(k))
    hook = out.get("hook") if isinstance(out.get("hook"), dict) else {"text": as_str(out.get("hook"))}
    hook.setdefault("type", "unknown")
    out["hook"] = hook
    if not isinstance(out.get("cta"), dict):
        out["cta"] = {"present": bool(out.get("cta")), "text": as_str(out.get("cta")) or None, "type": "unknown"}
    if not isinstance(out.get("audio"), dict):
        out["audio"] = {"voice": as_str(out.get("audio"))}
    out["confidence"] = conf(out.get("confidence"))
    out["content_format"] = (out["content_format"] or "other").strip().lower().replace(" ", "_")
    return out


def insight(d: Any, valid_refs: set[str]) -> dict | None:
    if not isinstance(d, dict) or not as_str(d.get("conclusion")).strip():
        return None
    refs = [str(r).strip().upper() for r in as_list(d.get("video_refs"))]
    good = [r for r in refs if r in valid_refs]
    dropped = [r for r in refs if r not in valid_refs]
    out = {
        "conclusion": as_str(d.get("conclusion")),
        "evidence": [as_str(e) for e in as_list(d.get("evidence"))],
        "video_refs": list(dict.fromkeys(good)),
        "observed_data": as_str(d.get("observed_data")),
        "pattern": as_str(d.get("pattern")),
        "hypothesis": as_str(d.get("hypothesis")),
        "recommendation": as_str(d.get("recommendation")),
        "confidence": conf(d.get("confidence")),
    }
    flags = []
    if dropped:
        flags.append(f"Đã loại {len(dropped)} tham chiếu video không tồn tại: {', '.join(dropped[:5])}")
    if not good:
        out["confidence"] = min(out["confidence"], 0.35)
        flags.append("Không có video tham chiếu hợp lệ — độ tin cậy bị hạ.")
    if not out["evidence"]:
        out["confidence"] = min(out["confidence"], 0.3)
        flags.append("Thiếu bằng chứng cụ thể.")
    out["quality_flags"] = flags
    return out


def insights(items: Any, valid_refs: set[str]) -> list[dict]:
    return [x for x in (insight(i, valid_refs) for i in as_list(items)) if x]
