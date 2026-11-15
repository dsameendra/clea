"""SQLite storage: connection setup, schema and migrations.

Full-text search uses an FTS5 *external content* table that mirrors
``documents`` through triggers, so updating or deleting a document can never
leave stale postings behind. Ranking uses FTS5's built-in BM25.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id              INTEGER PRIMARY KEY,
    seed_url        TEXT NOT NULL UNIQUE,
    host            TEXT NOT NULL,
    path_prefix     TEXT NOT NULL DEFAULT '/',
    max_pages       INTEGER NOT NULL DEFAULT 200,
    max_depth       INTEGER NOT NULL DEFAULT 3,
    added_at        TEXT NOT NULL,
    last_crawled_at TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',   -- pending | crawling | ok | error
    last_error      TEXT,
    auto_crawl      INTEGER NOT NULL DEFAULT 1,        -- included in scheduled crawls
    sitemap_checked_at TEXT
);

-- The crawl frontier and per-URL fetch state.
CREATE TABLE IF NOT EXISTS urls (
    id            INTEGER PRIMARY KEY,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url           TEXT NOT NULL UNIQUE,
    depth         INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'queued',      -- queued | done | skipped | failed
    reason        TEXT,
    http_status   INTEGER,
    etag          TEXT,
    last_modified TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    discovered_at TEXT NOT NULL,
    fetched_at    TEXT
);
CREATE INDEX IF NOT EXISTS urls_site_status ON urls(site_id, status);

-- Searchable documents (one per successfully indexed URL).
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY,
    url_id       INTEGER NOT NULL UNIQUE REFERENCES urls(id) ON DELETE CASCADE,
    site_id      INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url          TEXT NOT NULL,
    host         TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    url_terms    TEXT NOT NULL DEFAULT '',
    lang         TEXT,
    word_count   INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    indexed_at   TEXT NOT NULL,
    link_density REAL NOT NULL DEFAULT 0              -- share of the text that is link text (index/nav pages)
);
CREATE INDEX IF NOT EXISTS documents_host ON documents(host);
CREATE INDEX IF NOT EXISTS documents_site ON documents(site_id);
CREATE INDEX IF NOT EXISTS documents_hash ON documents(content_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, description, body, url_terms,
    content='documents', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, description, body, url_terms)
    VALUES (new.id, new.title, new.description, new.body, new.url_terms);
END;
CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, description, body, url_terms)
    VALUES ('delete', old.id, old.title, old.description, old.body, old.url_terms);
END;
CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, description, body, url_terms)
    VALUES ('delete', old.id, old.title, old.description, old.body, old.url_terms);
    INSERT INTO documents_fts(rowid, title, description, body, url_terms)
    VALUES (new.id, new.title, new.description, new.body, new.url_terms);
END;

-- Surface-form vocabulary with document frequency; powers "did you mean" and autocomplete.
CREATE TABLE IF NOT EXISTS words (
    word TEXT PRIMARY KEY,
    df   INTEGER NOT NULL
) WITHOUT ROWID;

-- Key/value settings saved from the UI (JSON values), e.g. the crawl schedule.
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY,
    kind           TEXT NOT NULL,
    params         TEXT NOT NULL DEFAULT '{}',
    status         TEXT NOT NULL DEFAULT 'queued',     -- queued | running | done | failed | cancelled | interrupted
    created_at     TEXT NOT NULL,
    started_at     TEXT,
    finished_at    TEXT,
    pages_fetched  INTEGER NOT NULL DEFAULT 0,
    pages_indexed  INTEGER NOT NULL DEFAULT 0,
    pages_skipped  INTEGER NOT NULL DEFAULT 0,
    pages_failed   INTEGER NOT NULL DEFAULT 0,
    current_url    TEXT,
    message        TEXT,
    error          TEXT
);
"""


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    """Parse our timestamps and sitemap <lastmod> values (date or datetime, any offset)."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def get_config(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_config(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection configured for concurrent readers + one writer thread."""
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    # IMMEDIATE: write transactions take the write lock up front (waiting via the busy timeout).
    # With deferred transactions, concurrent crawler threads can fail with "database is locked"
    # when a transaction's read snapshot goes stale before its first write.
    conn = sqlite3.connect(str(path), timeout=30, isolation_level="IMMEDIATE")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add scheduling and ranking columns.

    ``link_density`` can only be computed from a page's HTML, so validators are
    cleared: the next recrawl downloads every page in full instead of getting 304s.
    """
    if "auto_crawl" not in _columns(conn, "sites"):
        conn.execute("ALTER TABLE sites ADD COLUMN auto_crawl INTEGER NOT NULL DEFAULT 1")
    if "sitemap_checked_at" not in _columns(conn, "sites"):
        conn.execute("ALTER TABLE sites ADD COLUMN sitemap_checked_at TEXT")
    if "link_density" not in _columns(conn, "documents"):
        conn.execute("ALTER TABLE documents ADD COLUMN link_density REAL NOT NULL DEFAULT 0")
        conn.execute("UPDATE urls SET etag = NULL, last_modified = NULL")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema (idempotent) and run migrations."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.executescript(SCHEMA)
    if version < SCHEMA_VERSION:
        if version == 0 and _table_exists(conn, "sitemap_urls"):
            _import_legacy_sites(conn)
        if 0 < version < 3:
            _migrate_v2_to_v3(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def open_database(db_path: Path | str, legacy_path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the database.

    When the database is created for the first time and a Clea 1.x database
    exists at ``legacy_path``, its sites are imported so they can be re-crawled.
    """
    fresh = str(db_path) == ":memory:" or not Path(db_path).exists()
    conn = connect(db_path)
    init_db(conn)
    if fresh and legacy_path is not None and Path(legacy_path).exists():
        import_legacy_file(conn, Path(legacy_path))
    return conn


def import_legacy_file(conn: sqlite3.Connection, path: Path) -> int:
    from .sites import add_site  # local import: sites imports db

    legacy = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        if not _table_exists(legacy, "sitemap_urls"):
            return 0
        urls = [row[0] for row in legacy.execute("SELECT url FROM sitemap_urls WHERE active")]
    finally:
        legacy.close()
    imported = 0
    for url in urls:
        try:
            add_site(conn, url)
            imported += 1
        except ValueError:
            continue
    return imported


def _import_legacy_sites(conn: sqlite3.Connection) -> None:
    """Carry seed URLs over from the v1 schema (``sitemap_urls``).

    The v1 word index cannot be converted (it was keyed on page ids that
    drifted on every re-index), so pages are re-crawled instead. The legacy
    tables are left untouched; drop them manually once you're happy.
    """
    from .sites import add_site  # local import: sites imports db

    rows = conn.execute("SELECT url FROM sitemap_urls WHERE active").fetchall()
    for row in rows:
        try:
            add_site(conn, row[0])
        except ValueError:
            continue
