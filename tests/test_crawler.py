import threading

import pytest

from clea import glaneur, servir, sites

from .conftest import page


def build_site(site):
    b = site.base
    site.raw("/robots.txt", "User-agent: *\nDisallow: /private/\nSitemap: {base}/sitemap.xml\n", "text/plain")
    site.raw("/sitemap.xml", "<urlset><url><loc>{base}/from-sitemap</loc></url></urlset>", "application/xml")
    site.html("/", page("Home", "Welcome to the fixture site home page.", links=[
        "/a", "/b?utm_source=news#top", "/private/secret", "/file.pdf", "http://external.invalid/x",
        "/redirect", "/out", "/noindex", "/dup", "/canon-alt", '<a href="/nofollowed" rel="nofollow">x</a>',
        "/broken", "/image", "/deep1",
    ]))
    site.html("/a", page("Alpha", "Python 3.12 interpreter details."), ETag='"v1"')
    site.html("/b", page("Bravo", "Bravo page with unique content."))
    site.html("/dup", page("Bravo", "Bravo page with unique content."))
    site.html("/canon-alt", page("Canon alt", "Alternate copy.", head=f'<link rel="canonical" href="{b}/b">'))
    site.html("/private/secret", page("Secret", "should never be fetched"))
    site.html("/nofollowed", page("Nofollow", "should never be fetched"))
    site.redirect("/redirect", "/final")
    site.html("/final", page("Final destination", "Reached through a redirect."))
    site.redirect("/out", "http://external.invalid/landing", 302)
    site.html("/noindex", page("Hidden", "Not for the index.", head='<meta name="robots" content="noindex">', links=["/via-noindex"]))
    site.html("/via-noindex", page("Via noindex", "Found through a noindex page."))
    site.raw("/image", "PNGDATA", "image/png")
    site.html("/deep1", page("Deep one", "Depth two page.", links=["/deep2"]))
    site.html("/deep2", page("Deep two", "Two clicks from the seed.", links=["/deep3"]))
    site.html("/deep3", page("Deep three", "Three clicks from the seed, beyond max depth."))
    site.html("/from-sitemap", page("From sitemap", "Only linked from sitemap.xml."))


def indexed(conn):
    return {r["url"] for r in conn.execute("SELECT url FROM documents")}


@pytest.fixture
def crawled(site, conn, settings):
    build_site(site)
    s = sites.add_site(conn, site.base + "/", max_depth=2, max_pages=50)
    counts = glaneur.crawl(conn, settings)
    return s, counts


def test_crawl_indexes_in_scope_pages_once(site, conn, crawled):
    b = site.base
    assert indexed(conn) == {
        f"{b}/", f"{b}/a", f"{b}/b", f"{b}/final", f"{b}/via-noindex", f"{b}/deep1", f"{b}/deep2",
        f"{b}/from-sitemap",
    }
    # Each page fetched exactly once (v1 fetched every page twice).
    page_requests = [p for p in site.paths() if p not in ("/robots.txt", "/sitemap.xml")]
    assert len(page_requests) == len(set(page_requests))


def test_crawl_respects_rules(site, conn, crawled):
    paths = site.paths()
    assert "/private/secret" not in paths  # robots.txt
    assert "/nofollowed" not in paths  # rel=nofollow
    assert "/file.pdf" not in paths  # non-HTML extension
    assert "/deep3" not in paths  # beyond max_depth=2
    assert not any("external" in p or "landing" in p for p in paths)
    assert all("utm_source" not in p for p in paths)
    ua = dict(site.requests[0][1])["User-Agent"]
    assert ua.startswith("CleaBot/")


def test_crawl_statuses(site, conn, crawled):
    b = site.base
    status = {r["url"]: (r["status"], r["reason"]) for r in conn.execute("SELECT url, status, reason FROM urls")}
    assert status[f"{b}/noindex"] == ("skipped", "noindex")
    assert status[f"{b}/canon-alt"][0] == "skipped" and "canonical" in status[f"{b}/canon-alt"][1]
    assert status[f"{b}/dup"][0] == "skipped" and "duplicate" in status[f"{b}/dup"][1]
    assert status[f"{b}/broken"] == ("failed", "HTTP 404")
    assert status[f"{b}/image"][0] == "skipped" and "image/png" in status[f"{b}/image"][1]
    assert status[f"{b}/out"][0] == "skipped" and "outside the site" in status[f"{b}/out"][1]
    assert status[f"{b}/redirect"][0] == "skipped" and status[f"{b}/final"][0] == "done"
    assert status[f"{b}/private/secret"][1] == "disallowed by robots.txt"


def test_failed_urls_are_not_retried_by_incremental_crawl(site, conn, settings, crawled):
    # v1 bug: failed pages stayed "unindexed" and were retried on every run.
    site.requests.clear()
    glaneur.crawl(conn, settings)
    assert "/broken" not in site.paths()


def test_recrawl_uses_conditional_requests(site, conn, settings, crawled):
    site.requests.clear()
    glaneur.crawl(conn, settings, recrawl=True)
    a_headers = [h for p, h in site.requests if p == "/a"][0]
    assert a_headers.get("If-None-Match") == '"v1"'
    assert f"{site.base}/a" in indexed(conn)  # 304 keeps the document


def test_recrawl_drops_pages_that_disappear(site, conn, settings, crawled):
    del site.routes["/b"]
    glaneur.crawl(conn, settings, recrawl=True)
    assert f"{site.base}/b" not in indexed(conn)
    assert servir.search(conn, "bravo")["total"] == 0


def test_page_budget(site, conn, settings):
    build_site(site)
    sites.add_site(conn, site.base + "/", max_pages=3)
    glaneur.crawl(conn, settings)
    assert len(indexed(conn)) <= 3


def test_robots_server_error_means_disallow(site, conn, settings):
    site.raw("/robots.txt", "oops", "text/plain", status=503)
    site.html("/", page("Home", "hello"))
    sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    assert site.paths() == ["/robots.txt"]
    assert indexed(conn) == set()


def test_cancel(site, conn, settings):
    build_site(site)
    sites.add_site(conn, site.base + "/")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(glaneur.Cancelled):
        glaneur.crawl(conn, settings, cancel=cancel)


def test_seed_failure_marks_site_error(site, conn, settings):
    s = sites.add_site(conn, site.base + "/missing/")
    glaneur.crawl(conn, settings)
    assert sites.get_site(conn, s["id"])["status"] == "error"
