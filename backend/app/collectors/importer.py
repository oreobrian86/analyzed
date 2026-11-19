"""Nhập danh sách URL hoặc dữ liệu CSV/JSON do người dùng cung cấp (khi không thu thập tự động được)."""
from __future__ import annotations

import csv
import io
import json
import re

from .base import CollectedVideo, CollectorError, to_int, ts, video_id_from_url

_URL = re.compile(r"https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/[^\s,;\"']+")

ALIASES = {
    "url": ("url", "link", "video_url", "webvideourl"),
    "caption": ("caption", "description", "desc", "text", "title"),
    "views": ("views", "view", "plays", "playcount", "view_count", "luot_xem"),
    "likes": ("likes", "like", "diggcount", "like_count"),
    "comments": ("comments", "comment", "commentcount", "comment_count"),
    "shares": ("shares", "share", "sharecount", "share_count"),
    "saves": ("saves", "save", "collectcount", "favorites"),
    "posted_at": ("posted_at", "date", "createtime", "createtimeiso", "upload_date", "ngay_dang"),
}


def parse_urls(text: str, limit: int) -> list[CollectedVideo]:
    urls = list(dict.fromkeys(_URL.findall(text or "")))
    if not urls:
        raise CollectorError("Không tìm thấy URL TikTok hợp lệ.")
    return [CollectedVideo(url=u.rstrip(").,"), platform_video_id=video_id_from_url(u)) for u in urls[:limit]]


def _pick(row: dict, key: str):
    low = {re.sub(r"[^a-z_]", "", str(k).lower()): v for k, v in row.items()}
    for a in ALIASES[key]:
        if a in low and low[a] not in (None, ""):
            return low[a]
    return None


def parse_import(text: str, limit: int) -> list[CollectedVideo]:
    text = (text or "").strip()
    if not text:
        raise CollectorError("Dữ liệu import trống.")
    rows: list[dict]
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise CollectorError(f"JSON không hợp lệ: {e}")
        rows = data if isinstance(data, list) else data.get("videos") or data.get("items") or []
    else:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t") if text else csv.excel
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        url = _pick(r, "url")
        caption = _pick(r, "caption")
        if not url and not caption:
            continue
        views = to_int(_pick(r, "views"))
        out.append(CollectedVideo(
            url=str(url).strip() if url else None, platform_video_id=video_id_from_url(str(url or "")),
            caption=caption, posted_at=ts(_pick(r, "posted_at")), views=views, likes=to_int(_pick(r, "likes")),
            comments=to_int(_pick(r, "comments")), shares=to_int(_pick(r, "shares")), saves=to_int(_pick(r, "saves")),
            metrics_source="user_import" if views is not None else "none"))
        if len(out) >= limit:
            break
    if not out:
        raise CollectorError("Không đọc được dòng nào. Cần ít nhất cột url (và nên có views, likes, comments, shares, date).")
    return out
