"""Phân tích hiệu suất XÁC ĐỊNH (không dùng LLM). Mọi con số trong báo cáo lấy từ đây.

Nguyên tắc:
- So với median của chính kênh (không so với TikTok nói chung).
- Dùng log(views) vì phân phối views rất lệch.
- Video quá mới (< min_age_days) bị loại khỏi phát hiện outlier vì views còn đang tăng.
- Outlier = khác thường so với kênh, KHÔNG đồng nghĩa "viral".
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import median


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _age_days(posted_at, now: datetime) -> float | None:
    if not posted_at:
        return None
    if isinstance(posted_at, str):
        try:
            posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    return max((now - posted_at).total_seconds() / 86400, 0.0)


def video_metrics(v: dict, now: datetime) -> dict:
    views = _num(v.get("views"))
    eng_parts = [_num(v.get(k)) for k in ("likes", "comments", "shares")]
    eng = sum(x for x in eng_parts if x is not None) if any(x is not None for x in eng_parts) else None
    age = _age_days(v.get("posted_at"), now)
    return {
        "views": views,
        "likes": _num(v.get("likes")),
        "comments": _num(v.get("comments")),
        "shares": _num(v.get("shares")),
        "engagement_rate": round(eng / views, 4) if views and eng is not None else None,
        "comment_rate": round(_num(v.get("comments")) / views, 5) if views and _num(v.get("comments")) is not None else None,
        "share_rate": round(_num(v.get("shares")) / views, 5) if views and _num(v.get("shares")) is not None else None,
        "age_days": round(age, 1) if age is not None else None,
    }


def _mad_z(values: list[float]) -> list[float]:
    """Robust z-score bằng median absolute deviation (ít bị outlier kéo lệch hơn std)."""
    if len(values) < 2:
        return [0.0] * len(values)
    med = median(values)
    mad = median([abs(x - med) for x in values])
    if mad == 0:
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1)) or 1.0
        return [(x - mean) / sd for x in values]
    return [0.6745 * (x - med) / mad for x in values]


def analyze(videos: list[dict], now: datetime | None = None, min_age_days: float = 3, z_threshold: float = 2.0,
            min_sample: int = 5) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = []
    for v in videos:
        m = video_metrics(v, now)
        m.update(video_id=str(v.get("id")), ref=v.get("ref"))
        rows.append(m)

    with_views = [r for r in rows if r["views"] is not None and r["views"] >= 0]
    notes: list[str] = []
    if len(with_views) < len(rows):
        notes.append(f"{len(rows) - len(with_views)}/{len(rows)} video không có dữ liệu lượt xem; bị loại khỏi phân tích hiệu suất.")
    if not with_views:
        return {"channel": {"videos_with_metrics": 0}, "videos": rows, "outliers": {"over": [], "under": []},
                "notes": notes + ["Không có dữ liệu metrics để phân tích hiệu suất."]}

    views = [r["views"] for r in with_views]
    med_views = median(views)
    ers = [r["engagement_rate"] for r in with_views if r["engagement_rate"] is not None]
    for r in with_views:
        r["relative_to_median"] = round(r["views"] / med_views, 2) if med_views else None

    eligible = [r for r in with_views if r["age_days"] is None or r["age_days"] >= min_age_days]
    over, under = [], []
    if len(eligible) >= min_sample:
        zs = _mad_z([math.log1p(r["views"]) for r in eligible])
        for r, z in zip(eligible, zs):
            r["views_z"] = round(z, 2)
            if z >= z_threshold:
                over.append(r["ref"])
            elif z <= -z_threshold:
                under.append(r["ref"])
    else:
        notes.append(f"Chỉ có {len(eligible)} video đủ điều kiện (≥{min_age_days:g} ngày tuổi, có views) — cần ≥{min_sample} để phát hiện outlier.")
    young = len(with_views) - len(eligible)
    if young:
        notes.append(f"{young} video đăng chưa đủ {min_age_days:g} ngày nên không xét outlier (views còn đang tăng).")
    notes.append("Outlier là video khác thường SO VỚI KÊNH NÀY; không kết luận 'viral' hay nguyên nhân chỉ từ lượt xem.")

    ages = [r["age_days"] for r in rows if r["age_days"] is not None]
    cadence = None
    if len(ages) >= 2 and max(ages) > min(ages):
        cadence = round(len(ages) / ((max(ages) - min(ages)) / 7), 2)

    channel = {
        "videos_with_metrics": len(with_views),
        "median_views": med_views,
        "mean_views": round(sum(views) / len(views), 1),
        "max_views": max(views),
        "min_views": min(views),
        "median_engagement_rate": round(median(ers), 4) if ers else None,
        "posts_per_week": cadence,
        "date_span_days": round(max(ages) - min(ages), 1) if len(ages) >= 2 else None,
    }
    return {"channel": channel, "videos": rows, "outliers": {"over": over, "under": under}, "notes": notes}


def group_stats(perf_rows: list[dict], refs: set[str], channel_median: float | None, total_videos: int) -> dict:
    sub = [r for r in perf_rows if r.get("ref") in refs]
    vv = [r["views"] for r in sub if r.get("views") is not None]
    ers = [r["engagement_rate"] for r in sub if r.get("engagement_rate") is not None]
    med = median(vv) if vv else None
    return {
        "video_count": len(refs),
        "share": round(len(refs) / total_videos, 3) if total_videos else 0,
        "videos_with_metrics": len(vv),
        "median_views": med,
        "median_vs_channel": round(med / channel_median, 2) if med is not None and channel_median else None,
        "median_engagement_rate": round(median(ers), 4) if ers else None,
        "small_sample": len(vv) < 3,
    }
