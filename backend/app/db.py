"""Kết nối Postgres (Supabase) qua psycopg3 + pool nhỏ (free tier giới hạn số connection)."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ConnectionPool(
                    settings.database_url,
                    min_size=1,
                    max_size=max(3, settings.worker_concurrency + 3),
                    # prepare_threshold=None: tương thích Supabase transaction pooler (port 6543)
                    kwargs={"row_factory": dict_row, "prepare_threshold": None, "autocommit": True},
                    open=True,
                    timeout=20,
                )
    return _pool


@contextmanager
def conn() -> Iterator[Any]:
    with pool().connection() as c:
        yield c


@contextmanager
def tx() -> Iterator[Any]:
    """Transaction tường minh (autocommit mặc định bật)."""
    with pool().connection() as c:
        with c.transaction():
            yield c


def one(sql: str, params: tuple | dict | None = None) -> dict | None:
    with conn() as c:
        return c.execute(sql, params).fetchone()


def all_(sql: str, params: tuple | dict | None = None) -> list[dict]:
    with conn() as c:
        return c.execute(sql, params).fetchall()


def run(sql: str, params: tuple | dict | None = None) -> int:
    with conn() as c:
        return c.execute(sql, params).rowcount


def j(value: Any) -> Jsonb:
    return Jsonb(value)


def log(analysis_id: str, message: str, level: str = "info", video_id: str | None = None) -> None:
    try:
        run(
            "insert into job_logs(analysis_id, video_id, level, message) values (%s,%s,%s,%s)",
            (analysis_id, video_id, level, message[:2000]),
        )
    except Exception:  # log không bao giờ được làm hỏng job
        pass
