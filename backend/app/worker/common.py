from __future__ import annotations

from .. import db


class Cancelled(Exception):
    pass


def check_cancel(analysis_id: str) -> dict:
    a = db.one("select * from analyses where id=%s", (analysis_id,))
    if not a or a["status"] == "cancelled":
        raise Cancelled()
    return a


def stage(analysis_id: str, text: str, progress: float | None = None) -> None:
    if progress is None:
        db.run("update analyses set stage=%s, updated_at=now() where id=%s", (text, analysis_id))
    else:
        db.run("update analyses set stage=%s, progress=%s, updated_at=now() where id=%s", (text, progress, analysis_id))
    db.log(analysis_id, text)
