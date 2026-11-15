"""Classeur — turns fetched HTML into searchable documents.

Extraction keeps the readable part of a page (``<main>``/``<article>`` when
present, minus navigation, scripts and boilerplate) and collects the metadata
the crawler needs: links, canonical URL and robots directives.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from .db import utcnow
from .urls import host_of, url_terms

MAX_TITLE = 300
MAX_DESCRIPTION = 500
MAX_BODY = 200_000

STRIP_TAGS = ["script", "style", "noscript", "template", "svg", "canvas", "iframe", "object", "embed", "form", "button", "select"]
BOILERPLATE_TAGS = ["nav", "header", "footer", "aside"]
BOILERPLATE_ROLES = ["navigation", "banner", "contentinfo", "complementary", "search"]
BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "li", "ul", "ol", "dl", "dt", "dd", "table", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "figure", "figcaption", "br", "hr",
}

PERMALINK_SYMBOLS = {"¶", "#", "§", "🔗"}
WORD_RE = re.compile(r"[^\W\d_]{3,24}")
MAX_VOCAB_PER_DOC = 3000


@dataclass
class Link:
    href: str
    nofollow: bool = False


@dataclass
class Page:
    title: str = ""
    description: str = ""
    body: str = ""
    lang: str | None = None
    canonical: str | None = None
    base_href: str | None = None
    noindex: bool = False
    nofollow: bool = False
    links: list[Link] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.body.split())


def _squash(text: str | None) -> str:
    return " ".join((text or "").split())


def _meta(soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None) -> str:
    attrs = {"name": re.compile(f"^{re.escape(name)}$", re.I)} if name else {"property": prop}
    tag = soup.find("meta", attrs=attrs)
    return _squash(tag.get("content")) if tag and tag.get("content") else ""


def extract(html: str) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    page = Page()

    robots = " ".join(
        (tag.get("content") or "").lower()
        for tag in soup.find_all("meta", attrs={"name": re.compile(r"^(robots|cleabot)$", re.I)})
    )
    page.noindex = "noindex" in robots or "none" in robots
    page.nofollow = "nofollow" in robots or "none" in robots

    base = soup.find("base", href=True)
    page.base_href = base["href"].strip() if base else None
    for link in soup.find_all("link", href=True):
        rel = [r.lower() for r in (link.get("rel") or [])]
        if "canonical" in rel:
            page.canonical = link["href"].strip()
            break

    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        page.lang = html_tag["lang"].strip()[:16]

    title = _squash(soup.title.get_text()) if soup.title else ""
    if not title:
        title = _meta(soup, prop="og:title")
    if not title and soup.find("h1"):
        title = _squash(soup.find("h1").get_text())
    page.title = title[:MAX_TITLE]
    page.description = (_meta(soup, name="description") or _meta(soup, prop="og:description"))[:MAX_DESCRIPTION]

    for a in soup.find_all("a", href=True):
        rel = [r.lower() for r in (a.get("rel") or [])]
        page.links.append(Link(a["href"].strip(), nofollow="nofollow" in rel))

    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"aria-hidden": "true"}):
        tag.decompose()
    # Heading permalink anchors ("¶", "#", "🔗") added by Sphinx, MkDocs and friends.
    for a in soup.find_all("a"):
        if a.get_text(strip=True) in PERMALINK_SYMBOLS or "headerlink" in (a.get("class") or []):
            a.decompose()

    container = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article")
    if container is None or len(container.get_text(strip=True)) < 200:
        container = soup.body or soup
    for tag in container.find_all(BOILERPLATE_TAGS):
        tag.decompose()
    for role in BOILERPLATE_ROLES:
        for tag in container.find_all(attrs={"role": role}):
            tag.decompose()

    # Put line breaks around block elements so words from adjacent blocks don't fuse.
    for tag in container.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = (_squash(line) for line in container.get_text().splitlines())
    page.body = " ".join(line for line in lines if line)[:MAX_BODY]
    if not page.title:
        page.title = page.body[:80]
    return page


def content_hash(page: Page) -> str:
    return hashlib.sha256(f"{page.title}\n{page.body}".encode()).hexdigest()


# --- vocabulary (did-you-mean / autocomplete) ---------------------------------

def vocabulary(*texts: str) -> set[str]:
    words: set[str] = set()
    for text in texts:
        for word in WORD_RE.findall(text.lower()):
            words.add(word)
            if len(words) >= MAX_VOCAB_PER_DOC:
                return words
    return words


def _adjust_words(conn: sqlite3.Connection, removed: set[str], added: set[str]) -> None:
    if added:
        conn.executemany(
            "INSERT INTO words(word, df) VALUES (?, 1) ON CONFLICT(word) DO UPDATE SET df = df + 1",
            [(w,) for w in added],
        )
    if removed:
        conn.executemany("UPDATE words SET df = df - 1 WHERE word = ?", [(w,) for w in removed])
        conn.execute("DELETE FROM words WHERE df <= 0")


# --- documents -------------------------------------------------------------------

def index_page(conn: sqlite3.Connection, *, url_id: int, site_id: int, url: str, page: Page) -> tuple[bool, str | None]:
    """Insert or update the document for ``url_id``.

    Returns ``(indexed, reason)``; ``indexed`` is False when the page is an
    exact duplicate of a document already stored under another URL.
    """
    digest = content_hash(page)
    duplicate = conn.execute(
        "SELECT url FROM documents WHERE content_hash = ? AND url_id != ? LIMIT 1", (digest, url_id)
    ).fetchone()
    if duplicate:
        remove_document(conn, url_id)
        return False, f"duplicate of {duplicate['url']}"

    old = conn.execute("SELECT title, body FROM documents WHERE url_id = ?", (url_id,)).fetchone()
    old_words = vocabulary(old["title"], old["body"]) if old else set()
    new_words = vocabulary(page.title, page.body)

    conn.execute(
        """
        INSERT INTO documents (url_id, site_id, url, host, title, description, body, url_terms,
                               lang, word_count, content_hash, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url_id) DO UPDATE SET
            site_id = excluded.site_id, url = excluded.url, host = excluded.host,
            title = excluded.title, description = excluded.description, body = excluded.body,
            url_terms = excluded.url_terms, lang = excluded.lang, word_count = excluded.word_count,
            content_hash = excluded.content_hash, indexed_at = excluded.indexed_at
        """,
        (
            url_id, site_id, url, host_of(url), page.title, page.description, page.body, url_terms(url),
            page.lang, page.word_count, digest, utcnow(),
        ),
    )
    _adjust_words(conn, old_words - new_words, new_words - old_words)
    return True, None


def remove_document(conn: sqlite3.Connection, url_id: int) -> None:
    row = conn.execute("SELECT title, body FROM documents WHERE url_id = ?", (url_id,)).fetchone()
    if row:
        _adjust_words(conn, vocabulary(row["title"], row["body"]), set())
        conn.execute("DELETE FROM documents WHERE url_id = ?", (url_id,))


def remove_site_documents(conn: sqlite3.Connection, site_id: int) -> None:
    for row in conn.execute("SELECT url_id FROM documents WHERE site_id = ?", (site_id,)).fetchall():
        remove_document(conn, row["url_id"])
