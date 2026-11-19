"""Collector dự phòng TUỲ CHỌN qua Apify (dịch vụ bên thứ ba, có credit free hằng tháng nhưng KHÔNG vô hạn).
Chỉ bật khi admin đặt APIFY_TOKEN. Tên actor và tên trường có thể thay đổi — kiểm tra trang actor trước khi dùng."""
from __future__ import annotations

import httpx

from ..config import settings
from .base import CollectedVideo, CollectorError, to_int, ts


def enabled() -> bool:
    return bool(settings.apify_token)


def list_profile(handle: str, limit: int) -> list[CollectedVideo]:
    if not enabled():
        raise CollectorError("Apify chưa được cấu hình.")
    url = f"https://api.apify.com/v2/acts/{settings.apify_actor}/run-sync-get-dataset-items"
    try:
        r = httpx.post(url, params={"token": settings.apify_token, "timeout": 240},
                       json={"profiles": [handle], "resultsPerPage": limit, "shouldDownloadVideos": False}, timeout=300)
    except httpx.HTTPError as e:
        raise CollectorError(f"Apify lỗi kết nối: {e}")
    if r.status_code >= 300:
        raise CollectorError(f"Apify HTTP {r.status_code}: {r.text[:200]}")
    items = r.json() if isinstance(r.json(), list) else []
    out = []
    for it in items[:limit]:
        vurl = it.get("webVideoUrl") or it.get("url")
        if not vurl:
            continue
        out.append(CollectedVideo(
            url=vurl, platform_video_id=str(it.get("id") or "") or None, caption=it.get("text"),
            posted_at=ts(it.get("createTimeISO") or it.get("createTime")),
            duration_sec=(it.get("videoMeta") or {}).get("duration"),
            views=to_int(it.get("playCount")), likes=to_int(it.get("diggCount")),
            comments=to_int(it.get("commentCount")), shares=to_int(it.get("shareCount")),
            saves=to_int(it.get("collectCount")), metrics_source="collector"))
    if not out:
        raise CollectorError("Apify không trả video nào.")
    return out
