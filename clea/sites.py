"""Managing the list of sites Clea crawls."""

from __future__ import annotations

import sqlite3

from .classeur import remove_site_documents
from .db import utcnow
from .urls import default_path_prefix, host_of, normalize_url

DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_DEPTH = 3
MAX_PAGES_LIMIT = 100_000
MAX_DEPTH_LIMIT = 20


def _clamp(value, default: int, upper: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("max_pages and max_depth must be whole numbers") from None
    if number < 0 or number > upper:
        raise ValueError(f"value must be between 0 and {upper}")
    return number


def add_site(
    conn: sqlite3.Connection,
    url: str,
    *,
    max_pages: int | None = None,
    max_depth: int | None = None,
    path_prefix: str | None = None,
) -> dict:
    """Add a seed URL. Returns the site; if it already exists, returns the existing one."""
    raw = (url or "").strip()
    if raw and "://" not in raw:
        raw = "https://" + raw
    seed = normalize_url(raw)
    if not seed:
        raise ValueError(f"Not a valid http(s) URL: {url!r}")

    existing = conn.execute("SELECT id FROM sites WHERE seed_url = ?", (seed,)).fetchone()
    if existing:
        return get_site(conn, existing["id"])

    prefix = path_prefix or default_path_prefix(seed)
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    cur = conn.execute(
        "INSERT INTO sites (seed_url, host, path_prefix, max_pages, max_depth, added_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            seed,
            host_of(seed),
            prefix,
            _clamp(max_pages, DEFAULT_MAX_PAGES, MAX_PAGES_LIMIT),
            _clamp(max_depth, DEFAULT_MAX_DEPTH, MAX_DEPTH_LIMIT),
            utcnow(),
        ),
    )
    site_id = cur.lastrowid
    enqueue_seed(conn, site_id, seed)
    conn.commit()
    return get_site(conn, site_id)


def enqueue_seed(conn: sqlite3.Connection, site_id: int, seed: str) -> None:
    conn.execute(
        """
        INSERT INTO urls (site_id, url, depth, status, discovered_at) VALUES (?, ?, 0, 'queued', ?)
        ON CONFLICT(url) DO UPDATE SET status = 'queued', depth = 0, site_id = excluded.site_id
        """,
        (site_id, seed, utcnow()),
    )


def update_site(conn: sqlite3.Connection, site_id: int, *, max_pages=None, max_depth=None, auto_crawl=None) -> dict | None:
    site = get_site(conn, site_id)
    if not site:
        return None
    if auto_crawl is not None and not isinstance(auto_crawl, bool):
        raise ValueError("auto_crawl must be true or false")
    conn.execute(
        "UPDATE sites SET max_pages = ?, max_depth = ?, auto_crawl = ? WHERE id = ?",
        (
            _clamp(max_pages, site["max_pages"], MAX_PAGES_LIMIT),
            _clamp(max_depth, site["max_depth"], MAX_DEPTH_LIMIT),
            int(site["auto_crawl"] if auto_crawl is None else auto_crawl),
            site_id,
        ),
    )
    conn.commit()
    return get_site(conn, site_id)


def remove_site(conn: sqlite3.Connection, site_id: int) -> bool:
    """Delete a site together with its crawl state and its documents."""
    if not conn.execute("SELECT 1 FROM sites WHERE id = ?", (site_id,)).fetchone():
        return False
    remove_site_documents(conn, site_id)
    conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
    conn.commit()
    return True


_SITE_COLUMNS = """
    s.id, s.seed_url, s.host, s.path_prefix, s.max_pages, s.max_depth, s.added_at,
    s.last_crawled_at, s.status, s.last_error, s.auto_crawl,
    (SELECT COUNT(*) FROM documents d WHERE d.site_id = s.id) AS documents,
    (SELECT COUNT(*) FROM urls u WHERE u.site_id = s.id AND u.status = 'queued') AS queued,
    (SELECT COUNT(*) FROM urls u WHERE u.site_id = s.id AND u.status = 'failed') AS failed,
    (SELECT COUNT(*) FROM urls u WHERE u.site_id = s.id AND u.status IN ('queued', 'done')) AS known
"""


def _site_dict(row: sqlite3.Row) -> dict:
    from .glaneur import FRONTIER_FACTOR

    site = dict(row)
    site["auto_crawl"] = bool(site["auto_crawl"])
    # Page limit reached: new pages stay queued (or stop being discovered) until max_pages is raised.
    known = site.pop("known")
    site["at_limit"] = site["documents"] >= site["max_pages"] or known >= site["max_pages"] * FRONTIER_FACTOR
    return site


def get_site(conn: sqlite3.Connection, site_id: int) -> dict | None:
    row = conn.execute(f"SELECT {_SITE_COLUMNS} FROM sites s WHERE s.id = ?", (site_id,)).fetchone()
    return _site_dict(row) if row else None


def list_sites(conn: sqlite3.Connection) -> list[dict]:
    return [_site_dict(row) for row in conn.execute(f"SELECT {_SITE_COLUMNS} FROM sites s ORDER BY s.added_at, s.id")]
