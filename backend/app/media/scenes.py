"""Hàm thuần xử lý dữ liệu cảnh (có unit test)."""
from __future__ import annotations

import re

_PTS = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def parse_showinfo(stderr: str) -> list[float]:
    times = sorted({round(float(m.group(1)), 2) for m in _PTS.finditer(stderr or "")})
    return times


def cuts_per_minute(cuts: list[float], duration: float) -> float | None:
    if not duration or duration <= 0:
        return None
    return round(len(cuts) / (duration / 60), 1)


def pick_keyframe_times(cuts: list[float], duration: float, n: int) -> list[float]:
    """Chọn n mốc thời gian: luôn có giây ~0.5 (hook), phần còn lại ưu tiên điểm cắt cảnh, rải đều."""
    if duration <= 0 or n <= 0:
        return []
    picks = [min(0.5, duration / 2)]
    if n == 1:
        return picks
    candidates = [c for c in cuts if 1.0 < c < duration - 0.3]
    slots = n - 1
    if len(candidates) >= slots:
        step = len(candidates) / slots
        picks += [candidates[int(i * step)] for i in range(slots)]
    else:
        picks += candidates
        remaining = n - len(picks)
        for i in range(1, remaining + 1):
            picks.append(round(duration * i / (remaining + 1), 2))
    out = sorted({round(t, 2) for t in picks})
    return out[:n]
