"""Hàm thuần (không I/O) để gộp giới hạn — có unit test."""
from __future__ import annotations


def merge_limits(defaults: dict, overrides: dict | None, is_admin: bool = False) -> dict:
    out = dict(defaults)
    for k, v in (overrides or {}).items():
        if k in out:
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                continue
    if is_admin:
        # Admin được gấp 5 lần, nhưng vẫn bị chặn bởi global cap của project
        for k in ("max_analyses_per_day", "max_videos_per_day", "max_ai_requests_per_day"):
            if not (overrides or {}).get(k):
                out[k] = out[k] * 5
        out["max_active_analyses"] = max(out["max_active_analyses"], 3)
    return out
