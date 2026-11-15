"""Servir — query parsing, ranking, snippets, suggestions and stats.

Query syntax (also implemented by the static/browser engine):

* ``word word``        all words must match (falls back to any word if nothing matches)
* ``"exact phrase"``   phrase match
* ``-word``            exclude pages containing the word
* ``prefix*``          prefix match
* ``site:example.com`` restrict to a host (and its subdomains)
* ``intitle:word``     word must appear in the title
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import time
from dataclasses import dataclass, field

MAX_QUERY_LENGTH = 512
MAX_PER_PAGE = 50
MARK_START = "\u0002"
MARK_END = "\u0003"
TOKEN_RE = re.compile(r"\w+", re.UNICODE)
# Words too common to justify a match on their own in "any word" fallback mode.
STOP_WORDS = frozenset(
    "a an and are as at be but by for from how if in into is it its no not of on or so such that the their then "
    "there these they this to was what when where which who why will with you your".split()
)
# BM25 column weights: title, description, body, url_terms.
BM25_WEIGHTS = (10.0, 4.0, 1.0, 3.0)


@dataclass
class ParsedQuery:
    terms: list[str] = field(default_factory=list)       # plain words (may end with *)
    phrases: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    title_terms: list[str] = field(default_factory=list)
    sites: list[str] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.terms or self.phrases or self.title_terms)

    @property
    def is_empty(self) -> bool:
        return not (self.has_text or self.sites)


def parse_query(raw: str) -> ParsedQuery:
    q = ParsedQuery()
    raw = (raw or "")[:MAX_QUERY_LENGTH]
    for match in re.finditer(r'(-?)"([^"]*)"?|(\S+)', raw):
        negated, phrase, word = match.groups()
        if phrase is not None:
            tokens = TOKEN_RE.findall(phrase)
            if not tokens:
                continue
            text = " ".join(tokens)
            if negated:
                q.excluded.append(text)
            elif len(tokens) == 1:
                q.terms.append(text)
            else:
                q.phrases.append(text)
            continue
        lower = word.lower()
        if lower.startswith("site:") and len(word) > 5:
            host = lower[5:].strip("/").removeprefix("www.")
            if host:
                q.sites.append(host)
            continue
        if lower.startswith("intitle:") and len(word) > 8:
            q.title_terms.extend(TOKEN_RE.findall(word[8:]))
            continue
        if word.startswith("-") and len(word) > 1:
            q.excluded.extend(TOKEN_RE.findall(word[1:]))
            continue
        prefix = word.endswith("*")
        tokens = TOKEN_RE.findall(word)
        if not tokens:
            continue
        # "3.12" or "c++" tokenise to several pieces; treat them as a phrase.
        if len(tokens) > 1:
            q.phrases.append(" ".join(tokens))
        else:
            q.terms.append(tokens[0] + ("*" if prefix else ""))
    return q


def _quote(token: str) -> str:
    if token.endswith("*"):
        return '"' + token[:-1].replace('"', '""') + '"*'
    return '"' + token.replace('"', '""') + '"'


def build_match(q: ParsedQuery, *, any_term: bool = False) -> str | None:
    """Translate a parsed query into an FTS5 MATCH expression (every token quoted)."""
    terms = q.terms
    if any_term:
        meaningful = [t for t in terms if t.lower().rstrip("*") not in STOP_WORDS and not t.isdigit()]
        terms = meaningful if meaningful or q.phrases else terms
    positives = [_quote(t) for t in terms] + [_quote(p) for p in q.phrases]
    joiner = " OR " if any_term else " AND "
    parts = []
    if positives:
        parts.append("(" + joiner.join(positives) + ")")
    parts.extend(f"title : {_quote(t)}" for t in q.title_terms)
    if not parts:
        return None
    expr = " AND ".join(parts)
    if q.excluded:
        expr = f"({expr}) NOT (" + " OR ".join(_quote(e) for e in q.excluded) + ")"
    return expr


def _site_filter(q: ParsedQuery) -> tuple[str, list[str]]:
    if not q.sites:
        return "", []
    clauses, params = [], []
    for host in q.sites:
        clauses.append("(d.host = ? OR d.host = ? OR d.host LIKE ?)")
        params.extend([host, "www." + host, "%." + host])
    return " AND (" + " OR ".join(clauses) + ")", params


def split_marks(text: str) -> list[dict]:
    """Turn FTS5 snippet markers into ``[{text, match}]`` segments for safe rendering."""
    segments: list[dict] = []
    for i, chunk in enumerate(re.split(f"{MARK_START}|{MARK_END}", text or "")):
        if chunk:
            segments.append({"text": chunk, "match": i % 2 == 1})
    return segments


def _run(conn: sqlite3.Connection, q: ParsedQuery, match: str | None, limit: int, offset: int):
    site_sql, site_params = _site_filter(q)
    if match is None:  # site: only — list that site's pages
        total = conn.execute(f"SELECT COUNT(*) FROM documents d WHERE 1=1 {site_sql}", site_params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT d.url, d.title, d.host, d.indexed_at, d.description AS description,
                       substr(d.body, 1, 240) AS snippet, 0 AS score
                FROM documents d WHERE 1=1 {site_sql}
                ORDER BY length(d.url), d.url LIMIT ? OFFSET ?""",
            [*site_params, limit, offset],
        ).fetchall()
        return total, rows
    total = conn.execute(
        f"SELECT COUNT(*) FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
        f"WHERE documents_fts MATCH ? {site_sql}",
        [match, *site_params],
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT d.url, d.title, d.host, d.indexed_at, d.description AS description,
                   snippet(documents_fts, 2, '{MARK_START}', '{MARK_END}', ' … ', 28) AS snippet,
                   highlight(documents_fts, 0, '{MARK_START}', '{MARK_END}') AS title_marked,
                   bm25(documents_fts, {', '.join(map(str, BM25_WEIGHTS))}) AS score
            FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ? {site_sql}
            ORDER BY score LIMIT ? OFFSET ?""",
        [match, *site_params, limit, offset],
    ).fetchall()
    return total, rows


def search(conn: sqlite3.Connection, raw_query: str, page: int = 1, per_page: int = 10) -> dict:
    started = time.perf_counter()
    page = max(1, int(page))
    per_page = min(max(1, int(per_page)), MAX_PER_PAGE)
    q = parse_query(raw_query)
    response = {
        "query": raw_query,
        "results": [],
        "total": 0,
        "page": page,
        "per_page": per_page,
        "relaxed": False,
        "suggestion": None,
    }
    if q.is_empty:
        response["took_ms"] = 0
        return response

    offset = (page - 1) * per_page
    total, rows = _run(conn, q, build_match(q), per_page, offset)
    # Nothing matched every word: retry with any word so long queries still find something.
    if total == 0 and len(q.terms) + len(q.phrases) > 1:
        total, rows = _run(conn, q, build_match(q, any_term=True), per_page, offset)
        response["relaxed"] = total > 0

    results = []
    for row in rows:
        snippet = row["snippet"] or ""
        if MARK_START not in snippet and row["description"]:
            snippet = row["description"]
        title = row["title_marked"] if "title_marked" in row.keys() and row["title_marked"] else row["title"]
        results.append(
            {
                "url": row["url"],
                "title": split_marks(title) or [{"text": row["url"], "match": False}],
                "snippet": split_marks(snippet),
                "host": row["host"],
                "indexed_at": row["indexed_at"],
            }
        )
    response["results"] = results
    response["total"] = total
    if total < 3 and q.terms:
        response["suggestion"] = spelling_suggestion(conn, raw_query, q)
    response["took_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return response


# --- suggestions ---------------------------------------------------------------

def _closest_word(conn: sqlite3.Connection, word: str) -> str | None:
    word = word.lower()
    if len(word) < 3 or conn.execute("SELECT 1 FROM words WHERE word = ?", (word,)).fetchone():
        return None
    candidates = conn.execute(
        "SELECT word, df FROM words WHERE length(word) BETWEEN ? AND ? AND substr(word, 1, 1) = ? "
        "ORDER BY df DESC LIMIT 5000",
        (len(word) - 2, len(word) + 2, word[0]),
    ).fetchall()
    best, best_score = None, 0.0
    for row in candidates:
        ratio = difflib.SequenceMatcher(None, word, row["word"]).ratio()
        score = ratio + min(row["df"], 1000) / 50_000  # tie-break toward common words
        if ratio >= 0.75 and score > best_score:
            best, best_score = row["word"], score
    return best


def spelling_suggestion(conn: sqlite3.Connection, raw_query: str, q: ParsedQuery | None = None) -> str | None:
    q = q or parse_query(raw_query)
    corrected = raw_query
    changed = False
    for term in q.terms:
        if term.endswith("*"):
            continue
        fix = _closest_word(conn, term)
        if fix:
            corrected = re.sub(rf"(?<![\w:-]){re.escape(term)}(?!\w)", fix, corrected, count=1, flags=re.I)
            changed = True
    return corrected if changed else None


def autocomplete(conn: sqlite3.Connection, prefix: str, limit: int = 8) -> list[str]:
    """Complete the last word of ``prefix`` from the vocabulary, most common first."""
    prefix = (prefix or "")[:MAX_QUERY_LENGTH]
    match = re.search(r"([^\W\d_]+)$", prefix.lower())
    if not match or len(match.group(1)) < 2:
        return []
    stem = match.group(1)
    head = prefix[: match.start(1)]
    rows = conn.execute(
        "SELECT word FROM words WHERE word >= ? AND word < ? AND word != ? ORDER BY df DESC LIMIT ?",
        (stem, stem + "￿", stem, limit),
    ).fetchall()
    return [head + row["word"] for row in rows]


def stats(conn: sqlite3.Connection) -> dict:
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    top_hosts = conn.execute(
        "SELECT host, COUNT(*) AS documents FROM documents GROUP BY host ORDER BY documents DESC LIMIT 10"
    ).fetchall()
    return {
        "documents": one("SELECT COUNT(*) FROM documents"),
        "sites": one("SELECT COUNT(*) FROM sites"),
        "words": one("SELECT COUNT(*) FROM words"),
        "queued": one("SELECT COUNT(*) FROM urls WHERE status = 'queued'"),
        "failed": one("SELECT COUNT(*) FROM urls WHERE status = 'failed'"),
        "last_indexed_at": one("SELECT MAX(indexed_at) FROM documents"),
        "last_crawled_at": one("SELECT MAX(last_crawled_at) FROM sites"),
        "top_hosts": [dict(r) for r in top_hosts],
    }
