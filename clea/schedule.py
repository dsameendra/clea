"""Automatic crawling: settings and "is a run due?" logic.

Two independent schedules, both editable from the admin panel:

* **discover** – find new pages (crawl mode ``new``) every N minutes
* **refresh**  – re-fetch every page (crawl mode ``recrawl``) every N hours

Intervals are measured from the end of the previous scheduled run, so a long
crawl never triggers the next one straight away. Settings and run history live
in the database: restarting Clea neither double-fires nor replays missed runs
(a run that came due while Clea was off happens once, shortly after start).
Environment variables (``CLEA_DISCOVER_MINUTES``, ``CLEA_RECRAWL_HOURS``,
``CLEA_CRAWL_WORKERS``) only provide defaults until settings are saved.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from .config import Settings
from .db import get_config, parse_iso, set_config, to_iso

CONFIG_KEY = "crawl_settings"
STATE_KEY = "crawl_schedule_state"
KINDS = ("refresh", "discover")  # refresh first: it is a superset of discover

# (minimum, maximum) for each numeric setting. The minimums keep Clea polite to the sites it crawls.
LIMITS = {
    "discover_minutes": (5, 7 * 24 * 60),
    "refresh_hours": (1, 365 * 24),
    "max_run_minutes": (1, 24 * 60),
    "workers": (1, 16),
}


def defaults(settings: Settings) -> dict:
    return {
        "discover_enabled": settings.discover_minutes > 0,
        "discover_minutes": _clamp("discover_minutes", settings.discover_minutes or 60),
        "refresh_enabled": settings.recrawl_hours > 0,
        "refresh_hours": _clamp("refresh_hours", settings.recrawl_hours or 168),
        "max_run_minutes": 30,
        "workers": _clamp("workers", settings.crawl_workers),
    }


def _clamp(key: str, value: float) -> float:
    lo, hi = LIMITS[key]
    return max(lo, min(hi, value))


def load(conn: sqlite3.Connection, settings: Settings) -> dict:
    saved = get_config(conn, CONFIG_KEY, {}) or {}
    return {**defaults(settings), **{k: v for k, v in saved.items() if k in defaults(settings)}}


def validate(patch: dict) -> dict:
    clean = {}
    for key, value in patch.items():
        if key in ("discover_enabled", "refresh_enabled"):
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            clean[key] = value
        elif key in LIMITS:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{key} must be a number")
            lo, hi = LIMITS[key]
            if not lo <= value <= hi:
                raise ValueError(f"{key} must be between {lo} and {hi}")
            clean[key] = int(value) if key == "workers" else value
        else:
            raise ValueError(f"Unknown setting {key!r}")
    return clean


def save(conn: sqlite3.Connection, settings: Settings, patch: dict, *, now: datetime | None = None) -> dict:
    current = load(conn, settings)
    updated = {**current, **validate(patch)}
    state = get_config(conn, STATE_KEY, {}) or {}
    stamp = to_iso(now or datetime.now(UTC))
    # Turning a schedule on, or changing its interval, starts its clock now.
    for kind, unit in (("discover", "discover_minutes"), ("refresh", "refresh_hours")):
        enabled = updated[f"{kind}_enabled"]
        if enabled and (not current[f"{kind}_enabled"] or updated[unit] != current[unit]):
            state[f"{kind}_anchor"] = stamp
    set_config(conn, CONFIG_KEY, updated)
    set_config(conn, STATE_KEY, state)
    conn.commit()
    return updated


def _interval(cfg: dict, kind: str) -> timedelta:
    return timedelta(minutes=cfg["discover_minutes"]) if kind == "discover" else timedelta(hours=cfg["refresh_hours"])


def _job(conn: sqlite3.Connection, job_id) -> sqlite3.Row | None:
    if not job_id:
        return None
    return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def status(conn: sqlite3.Connection, settings: Settings, *, now: datetime | None = None) -> dict:
    """Per schedule: last run, whether it is running, and when the next run is due."""
    now = now or datetime.now(UTC)
    cfg = load(conn, settings)
    state = get_config(conn, STATE_KEY, {}) or {}
    finished: dict[str, datetime | None] = {}
    out: dict[str, dict] = {}
    for kind in KINDS:
        job = _job(conn, state.get(f"{kind}_job_id"))
        running = bool(job and job["status"] in ("queued", "running"))
        last = parse_iso(job["finished_at"] or job["started_at"] or job["created_at"]) if job else None
        finished[kind] = None if running else last
        out[kind] = {
            "enabled": cfg[f"{kind}_enabled"],
            "running": running,
            "last_run_at": to_iso(last) if last else None,
            "last_job_id": job["id"] if job else None,
            "next_run_at": None,
        }
    for kind in KINDS:
        if not cfg[f"{kind}_enabled"] or out[kind]["running"]:
            continue
        marks = [parse_iso(state.get(f"{kind}_anchor")), finished[kind]]
        if kind == "discover":
            marks.append(finished["refresh"])  # a refresh also finds new pages
        marks = [m for m in marks if m]
        base = max(marks) if marks else now
        out[kind]["next_run_at"] = to_iso(base + _interval(cfg, kind))
    return out


def due(conn: sqlite3.Connection, settings: Settings, *, now: datetime | None = None) -> str | None:
    """The schedule that should run now ("refresh" or "discover"), if any."""
    now = now or datetime.now(UTC)
    state = get_config(conn, STATE_KEY, {}) or {}
    info = status(conn, settings, now=now)
    if any(v["running"] for v in info.values()):
        return None
    changed = False
    for kind in KINDS:
        if info[kind]["enabled"] and not state.get(f"{kind}_anchor") and not info[kind]["last_run_at"]:
            # Enabled through an environment variable and never run: start its clock now.
            state[f"{kind}_anchor"] = to_iso(now)
            changed = True
    if changed:
        set_config(conn, STATE_KEY, state)
        conn.commit()
        return None
    for kind in KINDS:
        nxt = parse_iso(info[kind]["next_run_at"])
        if nxt and nxt <= now:
            return kind
    return None


def record_run(conn: sqlite3.Connection, kind: str, job_id: int) -> None:
    state = get_config(conn, STATE_KEY, {}) or {}
    state[f"{kind}_job_id"] = job_id
    set_config(conn, STATE_KEY, state)
    conn.commit()
