"""Xác thực bằng Supabase Auth: frontend gửi access token, backend hỏi lại Supabase để xác minh.

Cách này hoạt động với cả JWT secret cũ (HS256) lẫn signing keys mới (ES256/RS256),
không cần giữ JWT secret trong backend. Kết quả được cache 2 phút để giảm số request.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, Header, HTTPException

from . import db
from .config import settings


@dataclass
class User:
    id: str
    email: str
    role: str
    quota_overrides: dict

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_TTL = 120


def _verify_with_supabase(token: str) -> dict:
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    try:
        r = httpx.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Không kết nối được dịch vụ đăng nhập (Supabase). Thử lại sau.")
    if r.status_code != 200:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Hãy đăng nhập lại.")
    try:
        data = r.json()
    except ValueError:
        raise HTTPException(503, "SUPABASE_URL trên server bị sai (phải dạng https://xxxx.supabase.co).")
    with _cache_lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = (now + _TTL, data)
    return data


def _email_allowed(email: str) -> bool:
    email = (email or "").lower()
    if not settings.allowed_emails and not settings.allowed_email_domains:
        return True  # không cấu hình allowlist => ai đăng ký được cũng dùng được
    if email in settings.allowed_emails:
        return True
    domain = email.split("@")[-1]
    return domain in settings.allowed_email_domains


def current_user(authorization: str = Header(default="")) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Chưa đăng nhập.")
    data = _verify_with_supabase(authorization.split(" ", 1)[1].strip())
    uid, email = data.get("id"), (data.get("email") or "").lower()
    if not uid:
        raise HTTPException(401, "Token không hợp lệ.")
    if not _email_allowed(email):
        raise HTTPException(403, "Email này chưa được admin cho phép sử dụng app.")
    role = "admin" if email in settings.admin_emails else "user"
    row = db.one(
        """insert into profiles(id, email, role) values (%s,%s,%s)
           on conflict (id) do update set email = excluded.email,
             role = case when excluded.role = 'admin' then 'admin' else profiles.role end
           returning role, quota_overrides""",
        (uid, email, role),
    )
    return User(id=uid, email=email, role=row["role"], quota_overrides=row["quota_overrides"] or {})


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Chỉ admin.")
    return user
