"""Worker chạy trong cùng process với API (free tier chỉ có 1 service).

- Hàng đợi nằm trong Postgres (bảng jobs) => server restart/spin-down không mất job; job đang chạy dở được
  tự động trả lại hàng đợi khi mất heartbeat (resume).
- Giới hạn concurrency (WORKER_CONCURRENCY) + giới hạn job chạy song song mỗi user.
- Retry có giới hạn với backoff; lỗi không thể retry (quota, file hỏng) dừng ngay.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid

import httpx

from .. import db
from ..ai.base import AIError
from ..collectors.base import CollectorError
from ..config import settings
from ..media.pipeline import MediaError
from ..quota import QuotaExceeded
from . import aggregate_stage, collect_stage, video_stage
from .common import Cancelled

log = logging.getLogger("worker")

HANDLERS = {
    "collect": (collect_stage.handle, collect_stage.on_final_failure),
    "process_video": (video_stage.handle, video_stage.on_final_failure),
    "aggregate": (aggregate_stage.handle, aggregate_stage.on_final_failure),
}


class Worker:
    def __init__(self) -> None:
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.stop = threading.Event()
        self.active = 0
        self.lock = threading.Lock()
        self.started_at = time.time()
        self.last_error: str | None = None

    def start(self) -> None:
        for i in range(max(1, settings.worker_concurrency)):
            threading.Thread(target=self._loop, name=f"worker-{i}", daemon=True).start()
        threading.Thread(target=self._maintenance, name="maintenance", daemon=True).start()
        log.info("worker %s started (concurrency=%s)", self.id, settings.worker_concurrency)

    # ---------------- main loop ----------------
    def _loop(self) -> None:
        idle = 2.0
        while not self.stop.is_set():
            try:
                job = db.one("select * from claim_job(%s,%s)", (self.id, settings.max_running_jobs_per_user))
            except Exception as e:
                self.last_error = f"claim: {e}"
                log.warning("claim failed: %s", e)
                time.sleep(10)
                continue
            if not job:
                time.sleep(idle)
                idle = min(idle * 1.5, 10)
                continue
            idle = 2.0
            with self.lock:
                self.active += 1
            try:
                self._run(job)
            finally:
                with self.lock:
                    self.active -= 1

    def _heartbeat(self, job_id: int, done: threading.Event) -> None:
        while not done.wait(20):
            try:
                db.run("update jobs set heartbeat_at=now() where id=%s and status='running'", (job_id,))
            except Exception:
                pass

    def _run(self, job: dict) -> None:
        handler, on_fail = HANDLERS[job["type"]]
        done = threading.Event()
        threading.Thread(target=self._heartbeat, args=(job["id"], done), daemon=True).start()
        try:
            handler(job)
            db.run("update jobs set status='done', updated_at=now(), locked_by=null where id=%s", (job["id"],))
        except Cancelled:
            db.run("update jobs set status='cancelled', updated_at=now() where id=%s", (job["id"],))
            if job.get("video_id"):
                db.run("update videos set status='cancelled', stage=null where id=%s and status not in ('done','failed','skipped')",
                       (job["video_id"],))
        except Exception as e:  # noqa: BLE001 — mọi lỗi đều phải được ghi lại, không được giết worker
            msg = f"{type(e).__name__}: {e}"[:1500]
            retryable = True
            if isinstance(e, QuotaExceeded | MediaError):
                retryable = False
            elif isinstance(e, AIError):
                retryable = e.retryable
            elif isinstance(e, CollectorError):
                retryable = True
            if retryable and job["attempts"] < job["max_attempts"]:
                delay = 30 * (2 ** (job["attempts"] - 1))
                db.run("update jobs set status='queued', last_error=%s, run_after=now() + make_interval(secs => %s), "
                       "locked_by=null, updated_at=now() where id=%s", (msg, delay, job["id"]))
                db.log(str(job["analysis_id"]), f"Job {job['type']} lỗi (lần {job['attempts']}), thử lại sau {delay}s: {msg}",
                       "warn", str(job["video_id"]) if job.get("video_id") else None)
            else:
                db.run("update jobs set status='failed', last_error=%s, updated_at=now(), locked_by=null where id=%s",
                       (msg, job["id"]))
                try:
                    on_fail(job, msg)
                except Exception as e2:
                    log.exception("on_final_failure crashed: %s", e2)
        finally:
            done.set()

    # ---------------- maintenance ----------------
    def _maintenance(self) -> None:
        last_cleanup = 0.0
        last_ping = 0.0
        while not self.stop.wait(60):
            try:
                n = db.one("select requeue_stale_jobs(%s) n", (settings.stale_job_seconds,))["n"]
                if n:
                    log.info("requeued %s stale jobs", n)
            except Exception as e:
                self.last_error = f"maintenance: {e}"
            # Render free spin-down sau 15 phút không có request vào => khi còn job, tự ping URL public
            if settings.keepalive_while_busy and settings.public_base_url and time.time() - last_ping > 240:
                try:
                    pending = db.one("select count(*) n from jobs where status in ('queued','running')")["n"]
                    if pending:
                        httpx.get(f"{settings.public_base_url}/api/health", timeout=15)
                        last_ping = time.time()
                except Exception:
                    pass
            if time.time() - last_cleanup > 3600:
                last_cleanup = time.time()
                try:
                    from ..cleanup import run_cleanup
                    run_cleanup()
                except Exception as e:
                    log.warning("cleanup failed: %s", e)

    def status(self) -> dict:
        return {"id": self.id, "active_jobs": self.active, "uptime_sec": int(time.time() - self.started_at),
                "last_error": self.last_error}


worker = Worker()
