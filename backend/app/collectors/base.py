from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


class CollectorError(Exception):
    pass


@dataclass
class CollectedVideo:
    url: str | None = None
    platform_video_id: str | None = None
    caption: str | None = None
    posted_at: datetime | None = None
    duration_sec: float | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    thumbnail_url: str | None = None
    metrics_source: str = "none"
    extra: dict = field(default_factory=dict)


_HANDLE = re.compile(r"tiktok\.com/@([A-Za-z0-9._]{2,32})")
_VID = re.compile(r"/video/(\d{8,25})")


def parse_handle(text: str) -> str | None:
    text = (text or "").strip()
    m = _HANDLE.search(text)
    if m:
        return m.group(1).lower()
    t = text.lstrip("@")
    if re.fullmatch(r"[A-Za-z0-9._]{2,32}", t):
        return t.lower()
    return None


def video_id_from_url(url: str) -> str | None:
    m = _VID.search(url or "")
    return m.group(1) if m else None


def ts(v) -> datetime | None:
    if v in (None, ""):
        return None
    try:
        if isinstance(v, str) and re.fullmatch(r"\d{8}", v):  # yt-dlp upload_date YYYYMMDD
            return datetime.strptime(v, "%Y%m%d").replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            return datetime.fromtimestamp(int(v), tz=timezone.utc)
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, OSError):
        return None


def to_int(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        s = str(v).strip().replace(",", "").replace(" ", "")
        mult = 1
        if s[-1:].upper() in "KMB" and s[-1:].isalpha():
            mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[s[-1].upper()]
            s = s[:-1]
        return int(float(s) * mult)
    except (ValueError, IndexError):
        return None
