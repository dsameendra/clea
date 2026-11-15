"""Glaneur — the crawler.

Breadth-first crawl of each site, limited to the site's host and path prefix,
a maximum depth and a page budget. Each page is fetched once: links are
extracted and the page is indexed from the same response.

Two modes:

* ``new``     – find and index new pages: re-reads each site's start page (and
               sitemaps, at most every few hours) for new links, re-fetches pages
               whose sitemap ``<lastmod>`` is newer than our copy, then crawls
               everything queued. Unchanged pages cost a 304.
* ``recrawl`` – re-fetch every known page (conditional requests).

Parallelism: sites are grouped by host and the groups are crawled concurrently
(``workers`` threads, each with its own HTTP session and database connection).
Requests to any single host stay sequential, so politeness is unaffected.

Politeness: robots.txt (RFC 9309, including Crawl-delay and Sitemap lines),
``<meta name="robots">`` noindex/nofollow, ``rel="nofollow"`` links, a
per-host delay, conditional requests (ETag / Last-Modified) and an identifying
User-Agent.
"""

from __future__ import annotations

import gzip
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import requests
from protego import Protego

from . import classeur
from .config import Settings
from .db import connect, parse_iso, to_iso, utcnow
from .urls import bare_host, in_scope, looks_like_non_html, normalize_url

log = logging.getLogger("clea.crawler")

HTML_TYPES = ("text/html", "application/xhtml+xml")
ROBOTS_TOKEN = "CleaBot"
MAX_ATTEMPTS = 3
MAX_SITEMAP_FILES = 5
FRONTIER_FACTOR = 3  # keep at most max_pages * FRONTIER_FACTOR live (queued/done) URLs per site
SITEMAP_RECHECK = timedelta(hours=6)  # "new" mode re-reads sitemaps at most this often
MODES = ("new", "recrawl")
SQL_CHUNK = 400  # max parameters per IN (...) query


class Cancelled(Exception):
    pass


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    text: str = ""
    content_type: str = ""
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None

    @property
    def not_modified(self) -> bool:
        return self.status == 304

    @property
    def is_html(self) -> bool:
        return self.content_type.split(";")[0].strip().lower() in HTML_TYPES


def _decode(raw: bytes, header_charset: str | None) -> str:
    charset = header_charset
    if not charset:
        match = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", raw[:4096], re.I)
        charset = match.group(1).decode("ascii") if match else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


class Fetcher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Language": "en;q=0.9,*;q=0.5",
            }
        )

    def get(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        html: bool = True,
        follow: Callable[[str], bool] | None = None,
        max_redirects: int = 5,
    ) -> FetchResult:
        """GET ``url``. Redirects are followed manually, only while ``follow(next_url)`` allows it.

        When a redirect is refused, the result has ``status`` 3xx and ``final_url`` set to the target.
        """
        result = FetchResult(url=url)
        current = url
        for _ in range(max_redirects + 1):
            headers = {}
            if current == url and etag:
                headers["If-None-Match"] = etag
            if current == url and last_modified:
                headers["If-Modified-Since"] = last_modified
            try:
                with self.session.get(
                    current, headers=headers, timeout=self.settings.request_timeout, stream=True, allow_redirects=False
                ) as resp:
                    result.status = resp.status_code
                    result.final_url = current
                    result.content_type = resp.headers.get("Content-Type", "")
                    result.etag = resp.headers.get("ETag")
                    result.last_modified = resp.headers.get("Last-Modified")
                    if resp.is_redirect and resp.headers.get("Location"):
                        target = normalize_url(resp.headers["Location"], base=current)
                        result.final_url = target
                        if target is None or (follow is not None and not follow(target)):
                            return result
                        current = target
                        continue
                    if resp.status_code != 200 or (html and not result.is_html):
                        return result
                    self._read_body(resp, result, current)
                    return result
            except requests.RequestException as exc:
                result.status = None
                result.error = f"{type(exc).__name__}: {exc}"[:500]
                return result
        result.error = "too many redirects"
        return result

    def _read_body(self, resp: requests.Response, result: FetchResult, url: str) -> None:
        limit = self.settings.max_page_bytes
        chunks, size = [], 0
        for chunk in resp.iter_content(64 * 1024):
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                result.error = f"page larger than {limit // 1024} KiB"
                return
        raw = b"".join(chunks)
        if url.endswith(".gz") and raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        match = re.search(r"charset=([\w-]+)", result.content_type, re.I)
        result.text = _decode(raw, match.group(1) if match else None)


class RobotsCache:
    """robots.txt per origin, following RFC 9309 error handling."""

    def __init__(self, fetcher: Fetcher):
        self.fetcher = fetcher
        self._cache: dict[str, Protego | None] = {}

    def _rules(self, url: str) -> Protego | None:
        origin = "/".join(url.split("/", 3)[:3])
        if origin not in self._cache:
            res = self.fetcher.get(origin + "/robots.txt", html=False)
            if res.status == 200:
                self._cache[origin] = Protego.parse(res.text)
            elif res.status is not None and 400 <= res.status < 500:
                self._cache[origin] = Protego.parse("")  # no robots.txt: everything allowed
            else:
                self._cache[origin] = None  # server error / unreachable: assume disallowed
        return self._cache[origin]

    def allowed(self, url: str) -> bool:
        rules = self._rules(url)
        return rules is not None and rules.can_fetch(url, ROBOTS_TOKEN)

    def crawl_delay(self, url: str) -> float:
        rules = self._rules(url)
        delay = rules.crawl_delay(ROBOTS_TOKEN) if rules else None
        return min(float(delay), 60.0) if delay else 0.0

    def sitemaps(self, url: str) -> list[str]:
        rules = self._rules(url)
        return list(rules.sitemaps) if rules else []


ProgressFn = Callable[[dict], None]
COUNTER_KEYS = ("pages_fetched", "pages_indexed", "pages_skipped", "pages_failed")


class Counters:
    """Progress counters shared by the worker threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._values = dict.fromkeys(COUNTER_KEYS, 0)
        self._current: str | None = None

    def bump(self, key: str, url: str | None) -> None:
        with self._lock:
            self._values[key] += 1
            self._current = url

    def snapshot(self) -> dict:
        with self._lock:
            return {**self._values, "current_url": self._current}


class Crawler:
    """Crawls sites one at a time. Each worker thread owns one Crawler (and its connection)."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        *,
        cancel: threading.Event | None = None,
        counters: Counters | None = None,
    ):
        self.conn = conn
        self.settings = settings
        self.cancel = cancel or threading.Event()
        self.counters = counters or Counters()
        self.fetcher = Fetcher(settings)
        self.robots = RobotsCache(self.fetcher)
        self._last_request: dict[str, float] = {}

    # -- helpers -------------------------------------------------------------------

    def _wait_turn(self, url: str) -> None:
        host = url.split("/", 3)[2]
        delay = max(self.settings.min_delay, self.robots.crawl_delay(url))
        elapsed = time.monotonic() - self._last_request.get(host, 0.0)
        if elapsed < delay and self.cancel.wait(delay - elapsed):
            raise Cancelled()
        if self.cancel.is_set():
            raise Cancelled()
        self._last_request[host] = time.monotonic()

    def _set_url(self, url_id: int, status: str, reason: str | None = None, **fields) -> None:
        cols = {"status": status, "reason": reason, **fields}
        assignments = ", ".join(f"{k} = ?" for k in cols)
        self.conn.execute(f"UPDATE urls SET {assignments} WHERE id = ?", [*cols.values(), url_id])

    def _bump(self, key: str, current_url: str | None = None) -> None:
        self.counters.bump(key, current_url)

    def _frontier_room(self, site: sqlite3.Row) -> int:
        live = self.conn.execute(
            "SELECT COUNT(*) FROM urls WHERE site_id = ? AND status IN ('queued', 'done')", (site["id"],)
        ).fetchone()[0]
        return max(0, site["max_pages"] * FRONTIER_FACTOR - live)

    def _enqueue_many(self, site: sqlite3.Row, urls: Iterable[str], depth: int) -> int:
        """Queue URLs not seen before (up to the frontier limit). Returns how many were added."""
        candidates = list(dict.fromkeys(urls))
        if not candidates:
            return 0
        known: set[str] = set()
        for i in range(0, len(candidates), SQL_CHUNK):
            chunk = candidates[i : i + SQL_CHUNK]
            marks = ",".join("?" * len(chunk))
            known.update(r[0] for r in self.conn.execute(f"SELECT url FROM urls WHERE url IN ({marks})", chunk))
        fresh = [u for u in candidates if u not in known][: self._frontier_room(site)]
        now = utcnow()
        self.conn.executemany(
            "INSERT INTO urls (site_id, url, depth, status, discovered_at) VALUES (?, ?, ?, 'queued', ?) ON CONFLICT(url) DO NOTHING",
            [(site["id"], u, depth, now) for u in fresh],
        )
        return len(fresh)

    def _enqueue(self, site: sqlite3.Row, url: str, depth: int) -> sqlite3.Row | None:
        """Queue one URL; returns its row (new or existing), or None if the frontier is full."""
        self._enqueue_many(site, [url], depth)
        return self.conn.execute("SELECT * FROM urls WHERE url = ?", (url,)).fetchone()

    def _read_sitemaps(self, site: sqlite3.Row) -> int:
        """Queue new URLs from the site's sitemaps and re-queue pages whose <lastmod> is newer than our copy."""
        parts = urlsplit(site["seed_url"])
        candidates = self.robots.sitemaps(site["seed_url"]) or [f"{parts.scheme}://{parts.netloc}/sitemap.xml"]
        added, files = 0, 0
        while candidates and files < MAX_SITEMAP_FILES and not self.cancel.is_set():
            sitemap_url = candidates.pop(0)
            if not self.robots.allowed(sitemap_url):
                continue
            files += 1
            res = self.fetcher.get(sitemap_url, html=False)
            if res.status != 200 or not res.text:
                continue
            if "<sitemapindex" in res.text[:2000].lower():
                candidates.extend(re.findall(r"<loc>\s*(.*?)\s*</loc>", res.text, re.I | re.S))
                continue
            entries: list[tuple[str, str | None]] = []
            for block in re.findall(r"<url>(.*?)</url>", res.text, re.I | re.S):
                loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.I | re.S)
                if not loc:
                    continue
                url = normalize_url(loc.group(1).replace("&amp;", "&"))
                if url and in_scope(url, site["host"], site["path_prefix"]) and not looks_like_non_html(url):
                    lastmod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.I | re.S)
                    moment = parse_iso(lastmod.group(1)) if lastmod else None
                    entries.append((url, to_iso(moment) if moment else None))
            added += self._enqueue_many(site, (u for u, _ in entries), 1)
            self.conn.executemany(
                "UPDATE urls SET status = 'queued' WHERE url = ? AND site_id = ? AND status = 'done' "
                "AND (fetched_at IS NULL OR fetched_at < ?)",
                [(u, site["id"], m) for u, m in entries if m],
            )
            self.conn.commit()  # never hold the write lock across the next network request
        if self.cancel.is_set():
            return added  # cut short: leave sitemap_checked_at alone so they are read next time
        self.conn.execute("UPDATE sites SET sitemap_checked_at = ? WHERE id = ?", (utcnow(), site["id"]))
        self.conn.commit()
        return added

    # -- crawling ------------------------------------------------------------------

    def crawl_site(self, site_id: int, *, mode: str = "new") -> None:
        if mode not in MODES:
            raise ValueError(f"unknown crawl mode {mode!r}")
        # A cancelled or time-limited run must not touch sites it never got to: no requests,
        # no status change, and no last_crawled_at, so they go first next time.
        if self.cancel.is_set():
            raise Cancelled()
        conn = self.conn
        site = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
        if site is None:
            return
        conn.execute("UPDATE sites SET status = 'crawling', last_error = NULL WHERE id = ?", (site_id,))
        if mode == "recrawl":
            # Everything is re-evaluated: robots.txt, noindex, canonical or content may have changed.
            conn.execute("UPDATE urls SET status = 'queued', attempts = 0 WHERE site_id = ?", (site_id,))
        else:
            # Re-read the start page (and where it redirects to) so newly linked pages are found.
            conn.execute("UPDATE urls SET status = 'queued', attempts = 0 WHERE site_id = ? AND depth = 0", (site_id,))
        conn.execute(
            "INSERT INTO urls (site_id, url, depth, status, discovered_at) VALUES (?, ?, 0, 'queued', ?) "
            "ON CONFLICT(url) DO NOTHING",
            (site_id, site["seed_url"], utcnow()),
        )
        conn.commit()
        checked = parse_iso(site["sitemap_checked_at"])
        if mode == "recrawl" or checked is None or datetime.now(UTC) - checked > SITEMAP_RECHECK:
            self._read_sitemaps(site)

        # Safety cap on requests per run. The real limits are max_pages documents (enforced below),
        # the frontier size and, for scheduled runs, the time limit.
        budget = site["max_pages"] * FRONTIER_FACTOR + 10
        fetched = 0
        error = None
        try:
            while fetched < budget:
                if self.cancel.is_set():
                    raise Cancelled()
                # Once the site has max_pages documents, only refresh existing ones; new URLs stay
                # queued (without being fetched) until the limit is raised.
                full = conn.execute("SELECT COUNT(*) FROM documents WHERE site_id = ?", (site_id,)).fetchone()[0] >= site["max_pages"]
                row = conn.execute(
                    """SELECT u.* FROM urls u WHERE u.site_id = ? AND u.status = 'queued'
                       AND (? OR EXISTS (SELECT 1 FROM documents d WHERE d.url_id = u.id))
                       ORDER BY u.depth, u.id LIMIT 1""",
                    (site_id, not full),
                ).fetchone()
                if row is None:
                    break
                fetched += self._process(site, row)
                conn.commit()
        except Cancelled:
            conn.commit()
            raise
        except Exception as exc:  # keep the site record honest if something unexpected breaks
            log.exception("crawl of %s failed", site["seed_url"])
            conn.rollback()
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            seed = conn.execute("SELECT status, reason FROM urls WHERE url = ?", (site["seed_url"],)).fetchone()
            if error is None and seed is not None:
                has_docs = conn.execute("SELECT 1 FROM documents WHERE site_id = ? LIMIT 1", (site_id,)).fetchone()
                if seed["status"] == "failed":
                    error = f"Start page failed: {seed['reason']}"
                elif seed["status"] == "skipped" and not has_docs and not (seed["reason"] or "").startswith("redirects to "):
                    # e.g. the start page redirects to another domain, or robots.txt blocks it
                    error = f"Nothing indexed: start page {seed['reason']}"
            conn.execute(
                "UPDATE sites SET status = ?, last_error = ?, last_crawled_at = ? WHERE id = ?",
                ("error" if error else "ok", error, utcnow(), site_id),
            )
            conn.commit()

    def _process(self, site: sqlite3.Row, row: sqlite3.Row) -> int:
        """Handle one queued URL. Returns 1 if a request was made, else 0."""
        url = row["url"]
        if looks_like_non_html(url):
            self._set_url(row["id"], "skipped", "not an HTML page")
            self._bump("pages_skipped", url)
            return 0
        if not self.robots.allowed(url):
            classeur.remove_document(self.conn, row["id"])
            self._set_url(row["id"], "skipped", "disallowed by robots.txt")
            self._bump("pages_skipped", url)
            return 0

        def follow(target: str) -> bool:
            return in_scope(target, site["host"], site["path_prefix"]) and self.robots.allowed(target)

        # Conditional requests only make sense when we hold a copy: a page skipped earlier
        # (noindex, duplicate, ...) must be downloaded again to be re-evaluated.
        has_doc = self.conn.execute("SELECT 1 FROM documents WHERE url_id = ?", (row["id"],)).fetchone() is not None
        self._wait_turn(url)
        res = self.fetcher.get(
            url,
            etag=row["etag"] if has_doc else None,
            last_modified=row["last_modified"] if has_doc else None,
            follow=follow,
        )
        now = utcnow()
        self._bump("pages_fetched", url)

        if res.error and res.status is None:
            attempts = row["attempts"] + 1
            status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
            # Network errors are retried (with the usual politeness delay) up to MAX_ATTEMPTS times.
            self._set_url(row["id"], status, res.error, attempts=attempts, fetched_at=now)
            if status == "failed":
                self._bump("pages_failed", url)
            return 1
        if res.status is not None and 300 <= res.status < 400 and res.status != 304:
            classeur.remove_document(self.conn, row["id"])
            where = "outside the site" if res.final_url and not in_scope(res.final_url, site["host"], site["path_prefix"]) else "to a disallowed or invalid URL"
            self._set_url(row["id"], "skipped", f"redirects {where}: {res.final_url}", http_status=res.status, fetched_at=now)
            self._bump("pages_skipped", url)
            return 1
        if res.not_modified:
            self._set_url(row["id"], "done", None, http_status=304, fetched_at=now)
            return 1
        if res.status != 200:
            if res.status in (404, 410):
                classeur.remove_document(self.conn, row["id"])
            self._set_url(row["id"], "failed", f"HTTP {res.status}", http_status=res.status, fetched_at=now, attempts=row["attempts"] + 1)
            self._bump("pages_failed", url)
            return 1
        if res.error:
            self._set_url(row["id"], "skipped", res.error, http_status=res.status, fetched_at=now)
            self._bump("pages_skipped", url)
            return 1
        if not res.is_html:
            self._set_url(row["id"], "skipped", f"content type {res.content_type.split(';')[0] or 'unknown'}", http_status=200, fetched_at=now)
            self._bump("pages_skipped", url)
            return 1

        # Redirects: index under the final URL (we already have its body), if it is inside the site.
        target = row
        final = normalize_url(res.final_url or url) or url
        if final != url:
            target = self._enqueue(site, final, row["depth"])
            self._set_url(row["id"], "skipped", f"redirects to {final}", http_status=200, fetched_at=now)
            classeur.remove_document(self.conn, row["id"])
            if target is None:  # frontier full
                return 1

        page = classeur.extract(res.text)
        base = normalize_url(page.base_href, base=final) if page.base_href else final
        self._discover_links(site, target, page, base or final)

        meta = {"http_status": 200, "fetched_at": now, "etag": res.etag, "last_modified": res.last_modified, "attempts": 0}
        canonical = normalize_url(page.canonical, base=final) if page.canonical else None
        if page.noindex:
            classeur.remove_document(self.conn, target["id"])
            self._set_url(target["id"], "skipped", "noindex", **meta)
            self._bump("pages_skipped", final)
        elif canonical and canonical != final and in_scope(canonical, site["host"], site["path_prefix"]):
            classeur.remove_document(self.conn, target["id"])
            self._enqueue(site, canonical, target["depth"])
            self._set_url(target["id"], "skipped", f"canonical is {canonical}", **meta)
            self._bump("pages_skipped", final)
        elif not page.body.strip():
            self._set_url(target["id"], "skipped", "no readable text", **meta)
            self._bump("pages_skipped", final)
        elif not self._has_room(site, target["id"]):
            self._set_url(target["id"], "queued", "waiting: site page limit reached", **meta)
        else:
            indexed, reason = classeur.index_page(self.conn, url_id=target["id"], site_id=site["id"], url=final, page=page)
            self._set_url(target["id"], "done" if indexed else "skipped", reason, **meta)
            self._bump("pages_indexed" if indexed else "pages_skipped", final)
        return 1

    def _has_room(self, site: sqlite3.Row, url_id: int) -> bool:
        if self.conn.execute("SELECT 1 FROM documents WHERE url_id = ?", (url_id,)).fetchone():
            return True  # updating an existing document
        count = self.conn.execute("SELECT COUNT(*) FROM documents WHERE site_id = ?", (site["id"],)).fetchone()[0]
        return count < site["max_pages"]

    def _discover_links(self, site: sqlite3.Row, row: sqlite3.Row, page: classeur.Page, base: str) -> None:
        if page.nofollow or row["depth"] >= site["max_depth"]:
            return
        urls = []
        for link in page.links:
            if link.nofollow:
                continue
            url = normalize_url(link.href, base=base)
            if url and in_scope(url, site["host"], site["path_prefix"]) and not looks_like_non_html(url):
                urls.append(url)
        self._enqueue_many(site, urls, row["depth"] + 1)


def _host_key(seed_url: str) -> str:
    parts = urlsplit(seed_url)
    return bare_host(parts.netloc.lower())


def crawl(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    site_ids: list[int] | None = None,
    mode: str = "new",
    recrawl: bool | None = None,
    workers: int | None = None,
    cancel: threading.Event | None = None,
    progress: ProgressFn | None = None,
    max_seconds: float | None = None,
) -> dict:
    """Crawl sites in parallel (one worker per host) and return counters.

    ``site_ids=None`` means every site; an empty list means none. Sites crawled
    longest ago go first, so a time-limited run doesn't always starve the same ones.
    Raises ``Cancelled`` if ``cancel`` is set (but not when ``max_seconds`` runs out;
    then ``time_limited`` is True in the result).
    """
    if recrawl is not None:
        mode = "recrawl" if recrawl else "new"
    if mode not in MODES:
        raise ValueError(f"unknown crawl mode {mode!r}")
    rows = conn.execute(
        "SELECT id, seed_url FROM sites ORDER BY last_crawled_at IS NOT NULL, last_crawled_at, id"
    ).fetchall()
    if site_ids is not None:
        wanted = set(site_ids)
        rows = [r for r in rows if r["id"] in wanted]
    counters = Counters()
    result = {**dict.fromkeys(COUNTER_KEYS, 0), "time_limited": False, "errors": 0, "sites": len(rows)}
    if not rows:
        return result

    groups: dict[str, list[int]] = {}
    for r in rows:
        groups.setdefault(_host_key(r["seed_url"]), []).append(r["id"])
    cancel = cancel or threading.Event()
    deadline_hit = threading.Event()
    timer = None
    if max_seconds:
        def _deadline():
            deadline_hit.set()
            cancel.set()

        timer = threading.Timer(max_seconds, _deadline)
        timer.daemon = True
        timer.start()

    def run_group(ids: list[int]) -> None:
        worker_conn = connect(settings.db_path)
        try:
            crawler = Crawler(worker_conn, settings, cancel=cancel, counters=counters)
            for site_id in ids:
                crawler.crawl_site(site_id, mode=mode)
        finally:
            worker_conn.close()

    n_workers = max(1, min(workers or settings.crawl_workers, len(groups)))
    report = progress or (lambda update: None)
    try:
        with ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="clea-crawl") as pool:
            futures = [pool.submit(run_group, ids) for ids in groups.values()]
            pending = futures
            while pending:
                _, pending = wait(pending, timeout=0.5)
                report(counters.snapshot())  # on the caller's thread, so it may use the caller's connection
    finally:
        if timer:
            timer.cancel()

    cancelled = False
    for future in futures:
        exc = future.exception()
        if isinstance(exc, Cancelled):
            cancelled = True
        elif exc is not None:
            result["errors"] += 1
            log.error("crawl worker failed: %s", exc)
    if cancelled and not deadline_hit.is_set():
        raise Cancelled()
    snapshot = counters.snapshot()
    result.update({k: snapshot[k] for k in COUNTER_KEYS})
    result["time_limited"] = deadline_hit.is_set()
    if result["errors"] and result["errors"] == len(futures):
        raise RuntimeError("every crawl worker failed; see the server log")
    return result
