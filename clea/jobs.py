"""Background crawl jobs and the crawl scheduler.

One job runs at a time (the job itself crawls several hosts in parallel), so
HTTP requests return immediately; the UI polls ``/api/jobs`` for progress. Job
state lives in SQLite, so the history survives restarts (jobs cut short by a
restart are marked ``interrupted``). A scheduler thread checks
``schedule.due()`` every ``tick_seconds`` and submits automatic crawls.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime

from . import glaneur, schedule
from .config import Settings
from .db import connect, utcnow

log = logging.getLogger("clea.jobs")

ACTIVE = ("queued", "running")
PROGRESS_INTERVAL = 0.5


class JobConflict(Exception):
    pass


def job_dict(row) -> dict:
    job = dict(row)
    job["params"] = json.loads(job.get("params") or "{}")
    return job


class JobManager:
    def __init__(self, settings: Settings, *, tick_seconds: float = 30.0):
        self.settings = settings
        self.tick_seconds = tick_seconds
        self._queue: queue.Queue[int] = queue.Queue()
        self._cancel: dict[int, threading.Event] = {}
        self._lock = threading.Lock()
        self._started = False
        self._stop = threading.Event()

    def _conn(self):
        return connect(self.settings.db_path)

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        conn = self._conn()
        conn.execute(
            "UPDATE jobs SET status = 'interrupted', finished_at = ?, message = 'Server restarted while the job was active' "
            "WHERE status IN ('queued', 'running')",
            (utcnow(),),
        )
        conn.execute("UPDATE sites SET status = 'pending' WHERE status = 'crawling'")
        conn.commit()
        conn.close()
        threading.Thread(target=self._worker, name="clea-crawl-worker", daemon=True).start()
        threading.Thread(target=self._scheduler, name="clea-scheduler", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        for event in self._cancel.values():
            event.set()

    # -- public API ----------------------------------------------------------------

    def submit_crawl(
        self,
        *,
        site_ids: list[int] | None = None,
        mode: str = "new",
        recrawl: bool | None = None,
        reason: str = "manual",
        max_seconds: float | None = None,
        workers: int | None = None,
    ) -> dict:
        if recrawl is not None:
            mode = "recrawl" if recrawl else "new"
        if mode not in glaneur.MODES:
            raise ValueError(f"Unknown crawl mode {mode!r}")
        conn = self._conn()
        try:
            if workers is None:
                workers = schedule.load(conn, self.settings)["workers"]
            with self._lock:
                active = conn.execute("SELECT id FROM jobs WHERE status IN ('queued', 'running') LIMIT 1").fetchone()
                if active:
                    raise JobConflict(f"Job #{active['id']} is still running; wait for it or cancel it first.")
                params = {"site_ids": site_ids, "mode": mode, "reason": reason, "max_seconds": max_seconds, "workers": workers}
                cur = conn.execute(
                    "INSERT INTO jobs (kind, params, status, created_at, message) VALUES ('crawl', ?, 'queued', ?, 'Waiting to start')",
                    (json.dumps(params), utcnow()),
                )
                conn.commit()
                job_id = cur.lastrowid
                self._cancel[job_id] = threading.Event()
            self._queue.put(job_id)
            return self.get(job_id, conn)
        finally:
            conn.close()

    def cancel(self, job_id: int) -> dict | None:
        event = self._cancel.get(job_id)
        if event:
            event.set()
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE jobs SET status = 'cancelled', finished_at = ?, message = 'Cancelled before it started' "
                "WHERE id = ? AND status = 'queued'",
                (utcnow(), job_id),
            )
            conn.commit()
            return self.get(job_id, conn)
        finally:
            conn.close()

    def get(self, job_id: int, conn=None) -> dict | None:
        own = conn is None
        conn = conn or self._conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return job_dict(row) if row else None
        finally:
            if own:
                conn.close()

    def recent(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        try:
            return [job_dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))]
        finally:
            conn.close()

    # -- worker --------------------------------------------------------------------

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._run(job_id)
            except Exception:  # never let the worker thread die
                log.exception("job %s crashed", job_id)
            finally:
                self._cancel.pop(job_id, None)

    def _run(self, job_id: int) -> None:
        conn = self._conn()
        try:
            job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None or job["status"] != "queued":
                return
            params = json.loads(job["params"])
            cancel = self._cancel.setdefault(job_id, threading.Event())
            conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ?, message = 'Crawling' WHERE id = ?", (utcnow(), job_id)
            )
            conn.commit()

            last = [0.0]

            def progress(update: dict) -> None:
                now = time.monotonic()
                if now - last[0] < PROGRESS_INTERVAL:
                    return
                last[0] = now
                conn.execute(
                    "UPDATE jobs SET pages_fetched = ?, pages_indexed = ?, pages_skipped = ?, pages_failed = ?, current_url = ? WHERE id = ?",
                    (update["pages_fetched"], update["pages_indexed"], update["pages_skipped"], update["pages_failed"], update["current_url"], job_id),
                )
                conn.commit()

            status, message, error = "done", "Finished", None
            counts = {}
            mode = params.get("mode") or ("recrawl" if params.get("recrawl") else "new")
            try:
                counts = glaneur.crawl(
                    conn, self.settings, site_ids=params.get("site_ids"), mode=mode,
                    workers=params.get("workers"), max_seconds=params.get("max_seconds"),
                    cancel=cancel, progress=progress,
                )
                message = f"Indexed {counts['pages_indexed']} pages ({counts['pages_fetched']} fetched)"
                if counts.get("time_limited"):
                    message += " · stopped at the time limit"
                if counts.get("errors"):
                    message += f" · {counts['errors']} worker(s) failed, see the server log"
            except glaneur.Cancelled:
                status, message = "cancelled", "Cancelled"
            except Exception as exc:
                log.exception("crawl job %s failed", job_id)
                status, message, error = "failed", "Failed", f"{type(exc).__name__}: {exc}"
            conn.rollback()
            fields = counts or {}
            conn.execute(
                """UPDATE jobs SET status = ?, message = ?, error = ?, finished_at = ?, current_url = NULL,
                       pages_fetched = COALESCE(?, pages_fetched), pages_indexed = COALESCE(?, pages_indexed),
                       pages_skipped = COALESCE(?, pages_skipped), pages_failed = COALESCE(?, pages_failed)
                   WHERE id = ?""",
                (status, message, error, utcnow(), fields.get("pages_fetched"), fields.get("pages_indexed"),
                 fields.get("pages_skipped"), fields.get("pages_failed"), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    # -- scheduler -----------------------------------------------------------------

    def tick(self, now: datetime | None = None) -> dict | None:
        """Submit a scheduled crawl if one is due. Returns the job, if any."""
        conn = self._conn()
        try:
            kind = schedule.due(conn, self.settings, now=now)
            if kind is None:
                return None
            cfg = schedule.load(conn, self.settings)
            site_ids = [r["id"] for r in conn.execute("SELECT id FROM sites WHERE auto_crawl = 1 ORDER BY id")]
        finally:
            conn.close()
        if not site_ids:
            return None
        try:
            job = self.submit_crawl(
                site_ids=site_ids,
                mode="recrawl" if kind == "refresh" else "new",
                reason=f"scheduled-{kind}",
                max_seconds=cfg["max_run_minutes"] * 60,
                workers=cfg["workers"],
            )
        except JobConflict:
            return None  # a manual crawl is running; try again next tick
        conn = self._conn()
        try:
            schedule.record_run(conn, kind, job["id"])
        finally:
            conn.close()
        log.info("started scheduled %s crawl (job %s) for %d site(s)", kind, job["id"], len(site_ids))
        return job

    def _scheduler(self) -> None:
        while not self._stop.wait(self.tick_seconds):
            try:
                self.tick()
            except Exception:  # keep scheduling even if one tick fails
                log.exception("scheduler tick failed")
