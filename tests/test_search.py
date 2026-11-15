import pytest

from clea import classeur, servir, sites
from clea.db import utcnow

from .conftest import page


def add_doc(conn, url, title, body, *, description=""):
    site = conn.execute("SELECT id FROM sites LIMIT 1").fetchone()
    site_id = site["id"] if site else sites.add_site(conn, "https://example.com/")["id"]
    conn.execute("INSERT OR IGNORE INTO urls (site_id, url, discovered_at) VALUES (?, ?, ?)", (site_id, url, utcnow()))
    url_id = conn.execute("SELECT id FROM urls WHERE url = ?", (url,)).fetchone()["id"]
    p = classeur.Page(title=title, body=body, description=description)
    indexed, _ = classeur.index_page(conn, url_id=url_id, site_id=site_id, url=url, page=p)
    conn.commit()
    return url_id, indexed


def text(segments):
    return "".join(s["text"] for s in segments)


def urls(res):
    return [r["url"] for r in res["results"]]


@pytest.fixture
def corpus(conn):
    add_doc(conn, "https://example.com/python", "Python release notes", "Python 3.12 brings a faster interpreter and better error messages.")
    add_doc(conn, "https://example.com/rust", "Rust ownership", "The borrow checker enforces ownership rules. " * 20 + "Mentions python once.")
    add_doc(conn, "https://blog.example.com/cooking", "Cooking pasta", "Boil water, add salt and cook the pasta until al dente.")
    add_doc(conn, "https://other.org/cpp", "C++ templates", "Templates in c++ allow generic programming with zero overhead.")
    return conn


def test_title_match_outranks_body_mention(corpus):
    assert urls(servir.search(corpus, "python"))[0] == "https://example.com/python"


def test_numbers_are_searchable(corpus):
    # v1 stripped digits, so "3.12" never matched.
    assert urls(servir.search(corpus, "3.12")) == ["https://example.com/python"]


def test_stemming(corpus):
    assert "https://blog.example.com/cooking" in urls(servir.search(corpus, "cooked"))


def test_snippet_is_query_aware_and_marked(corpus):
    res = servir.search(corpus, "interpreter")
    snippet = res["results"][0]["snippet"]
    assert any(seg["match"] and seg["text"].lower() == "interpreter" for seg in snippet)


def test_phrase_exclusion_site_intitle(corpus):
    assert urls(servir.search(corpus, '"borrow checker"')) == ["https://example.com/rust"]
    assert urls(servir.search(corpus, '"checker borrow"')) == []
    assert "https://example.com/rust" not in urls(servir.search(corpus, "python -borrow"))
    assert urls(servir.search(corpus, "pasta site:example.com")) == ["https://blog.example.com/cooking"]
    assert urls(servir.search(corpus, "pasta site:other.org")) == []
    assert urls(servir.search(corpus, "intitle:ownership")) == ["https://example.com/rust"]
    assert len(urls(servir.search(corpus, "site:example.com"))) == 3


def test_prefix(corpus):
    assert "https://other.org/cpp" in urls(servir.search(corpus, "templ*"))


def test_relaxed_fallback(corpus):
    res = servir.search(corpus, "pasta zebra")
    assert res["relaxed"] and urls(res) == ["https://blog.example.com/cooking"]


@pytest.mark.parametrize("q", ['"', 'c++', 'a:b', 'NOT', 'AND OR NEAR', '*', '(', ')', '-', 'site:', 'intitle:', '"unclosed', "'; DROP TABLE documents; --", "title:x", "^", "{a b}"])
def test_hostile_queries_never_error(corpus, q):
    res = servir.search(corpus, q)
    assert isinstance(res["results"], list)


def test_cpp_query_matches(corpus):
    assert "https://other.org/cpp" in urls(servir.search(corpus, "c++"))


def test_pagination(corpus):
    for i in range(25):
        add_doc(corpus, f"https://example.com/p{i}", f"Widget {i}", f"widget number {i} documentation")
    first = servir.search(corpus, "widget", page=1, per_page=10)
    third = servir.search(corpus, "widget", page=3, per_page=10)
    assert first["total"] == 25 and len(first["results"]) == 10 and len(third["results"]) == 5
    assert not set(urls(first)) & set(urls(third))


def test_reindex_leaves_no_stale_postings(conn):
    # v1 bug: re-indexing gave the page a new id and left the old postings behind.
    url_id, _ = add_doc(conn, "https://example.com/a", "Original", "zeppelin airship history")
    add_doc(conn, "https://example.com/a", "Updated", "submarine history")
    assert servir.search(conn, "zeppelin")["total"] == 0
    assert servir.search(conn, "submarine")["total"] == 1
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    assert conn.execute("SELECT 1 FROM words WHERE word = 'zeppelin'").fetchone() is None


def test_duplicate_content_is_skipped(conn):
    add_doc(conn, "https://example.com/a", "Same", "identical content here")
    _, indexed = add_doc(conn, "https://example.com/a?print=1", "Same", "identical content here")
    assert not indexed
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_spelling_suggestion_and_autocomplete(corpus):
    res = servir.search(corpus, "interpretr")
    assert res["suggestion"] == "interpreter"
    assert servir.search(corpus, "interpreter")["suggestion"] is None
    assert "templates" in servir.autocomplete(corpus, "temp")
    assert servir.autocomplete(corpus, "c++ temp")[0].startswith("c++ temp")


def test_remove_site_removes_its_documents_and_can_be_readded(conn):
    s = sites.add_site(conn, "https://example.com/")
    add_doc(conn, "https://example.com/a", "Alpha", "unique aardvark words")
    assert servir.search(conn, "aardvark")["total"] == 1
    assert sites.remove_site(conn, s["id"])
    assert servir.search(conn, "aardvark")["total"] == 0
    assert conn.execute("SELECT COUNT(*) FROM words").fetchone()[0] == 0
    # v1 bug: a removed site could never be added again.
    again = sites.add_site(conn, "https://example.com/")
    assert again["id"] and [x["seed_url"] for x in sites.list_sites(conn)] == ["https://example.com/"]


def test_add_site_validation(conn):
    assert sites.add_site(conn, "example.org/docs/")["seed_url"] == "https://example.org/docs/"
    assert sites.add_site(conn, "example.org/docs/")["id"] == sites.add_site(conn, "https://EXAMPLE.org/docs/#x")["id"]
    with pytest.raises(ValueError):
        sites.add_site(conn, "javascript:alert(1)")
    with pytest.raises(ValueError):
        sites.add_site(conn, "https://e.com/", max_pages="lots")


def test_extract_main_content_and_metadata():
    html = page(
        "Hello",
        "Main body text that matters.",
        head='<meta name="description" content="A description"><link rel="canonical" href="/canon">'
        '<meta name="robots" content="noindex, nofollow"><script>var tracking = 1;</script>',
        links=["/a", '<a href="/b" rel="nofollow">b</a>'],
    )
    p = classeur.extract(html)
    assert p.title == "Hello" and p.description == "A description" and p.canonical == "/canon"
    assert p.noindex and p.nofollow and p.lang == "en"
    assert "Main body text" in p.body and "navigation menu" not in p.body and "footer" not in p.body
    assert "tracking" not in p.body
    assert [(link.href, link.nofollow) for link in p.links if link.href in ("/a", "/b")] == [("/a", False), ("/b", True)]


def test_stats(corpus):
    s = servir.stats(corpus)
    assert s["documents"] == 4 and s["sites"] == 1 and s["top_hosts"][0]["host"] == "example.com"


def test_legacy_v1_database_is_migrated(tmp_path):
    from clea.db import connect, init_db

    conn = connect(tmp_path / "old.db")
    conn.executescript(
        "CREATE TABLE sitemap_urls (id INTEGER PRIMARY KEY, url TEXT UNIQUE, active BOOLEAN DEFAULT TRUE);"
        "INSERT INTO sitemap_urls (url, active) VALUES ('https://kept.example/', 1), ('https://removed.example/', 0);"
    )
    init_db(conn)
    assert [s["seed_url"] for s in sites.list_sites(conn)] == ["https://kept.example/"]
    init_db(conn)  # idempotent
    assert len(sites.list_sites(conn)) == 1


def test_permalink_symbols_are_not_indexed():
    p = classeur.extract('<html><body><main><h2>Install<a class="headerlink" href="#install">¶</a></h2>'
                         '<p>Run pip install. <a href="#x">#</a></p></main></body></html>')
    assert "¶" not in p.body and "#" not in p.body and "Install" in p.body


def test_relaxed_fallback_ignores_stop_words(corpus):
    # "in" and "10" match lots of pages; the fallback should only use meaningful words.
    res = servir.search(corpus, "10 km in pasta")
    assert res["relaxed"] and urls(res) == ["https://blog.example.com/cooking"]
