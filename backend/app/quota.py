"""Quota theo user + giới hạn tổng của toàn project (cost protection)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from . import db
from .auth import User, current_user
from .config import settings
from .limits import merge_limits

GLOBAL_ID = "00000000-0000-0000-0000-000000000000"


class QuotaExceeded(Exception):
    pass


def limits_for(user_id: str, overrides: dict | None = None, role: str = "user") -> dict:
    if overrides is None:
        row = db.one("select quota_overrides, role from profiles where id=%s", (user_id,))
        overrides = (row or {}).get("quota_overrides") or {}
        role = (row or {}).get("role") or role
    return merge_limits(settings.default_limits, overrides, is_admin=(role == "admin"))


def global_limit(field: str) -> int:
    return {
        "ai_requests": settings.global_max_ai_requests_per_day,
        "videos": settings.global_max_videos_per_day,
        "upload_bytes": settings.global_max_upload_mb_per_day * 1024 * 1024,
    }.get(field, -1)


def consume(user_id: str, field: str, amount: int, user_limit: int) -> None:
    """Cộng usage nguyên tử. Ném QuotaExceeded nếu vượt giới hạn user HOẶC global."""
    row = db.one(
        "select consume_usage(%s,%s,%s,%s,%s) as ok",
        (user_id, field, amount, user_limit, global_limit(field)),
    )
    if not row or not row["ok"]:
        raise QuotaExceeded(
            f"Đã đạt giới hạn '{field}' hôm nay (của bạn hoặc của toàn hệ thống). Thử lại vào ngày mai (giờ UTC)."
        )


def add_tokens(user_id: str, input_tokens: int, output_tokens: int) -> None:
    db.run(
        """update usage_daily set ai_input_tokens = ai_input_tokens + %s, ai_output_tokens = ai_output_tokens + %s
           where day = current_date and user_id in (%s, %s)""",
        (input_tokens or 0, output_tokens or 0, user_id, GLOBAL_ID),
    )


def usage_today(user_id: str) -> dict:
    row = db.one("select * from usage_daily where user_id=%s and day=current_date", (user_id,))
    base = {"analyses": 0, "videos": 0, "ai_requests": 0, "ai_input_tokens": 0, "ai_output_tokens": 0, "upload_bytes": 0}
    if row:
        base.update({k: row[k] for k in base})
    return base


def storage_used_bytes(user_id: str) -> int:
    row = db.one(
        "select coalesce(sum(upload_bytes),0) as b from videos where user_id=%s and upload_path is not null",
        (user_id,),
    )
    return int(row["b"]) if row else 0


# ---------- Rate limit API (trong bộ nhớ, đủ cho 1 instance) ----------
_hits: dict[str, deque] = defaultdict(deque)
_rl_lock = threading.Lock()


def rate_limited_user(user: User = Depends(current_user)) -> User:
    now = time.time()
    with _rl_lock:
        q = _hits[user.id]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= settings.api_rate_per_minute:
            raise HTTPException(429, "Bạn thao tác quá nhanh. Đợi một chút rồi thử lại.")
        q.append(now)
    return user
