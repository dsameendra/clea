"""New-page discovery, parallel crawling and the crawl scheduler."""

import json
import threading
from datetime import timedelta

import pytest

from clea import glaneur, schedule, servir, sites
from clea.db import connect, init_db, parse_iso, utcnow
from clea.jobs import JobManager

from .conftest import page


def indexed(conn):
    return {r["url"] for r in conn.execute("SELECT url FROM documents")}


def page_requests(site):
    return [p for p in site.paths() if p not in ("/robots.txt", "/sitemap.xml")]


def simple_site(site, n=2, label="", **seed_headers):
    site.raw("/robots.txt", "", "text/plain")
    site.html("/", page("Home", f"Welcome to the {label} home page.", links=[f"/p{i}" for i in range(n)]), **seed_headers)
    for i in range(n):
        site.html(f"/p{i}", page(f"Page {i}", f"Content of {label} page number {i} with word{i}."))


# -- discovery -------------------------------------------------------------------------


def test_new_mode_finds_pages_linked_from_the_start_page(site, conn, settings):
    simple_site(site)
    sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    assert len(indexed(conn)) == 3
    # The site publishes a new page and links it from the home page.
    site.html("/", page("Home", "Welcome to the home page.", links=["/p0", "/p1", "/fresh"]))
    site.html("/fresh", page("Fresh news", "Brand new zeppelin article."))
    site.requests.clear()
    glaneur.crawl(conn, settings)
    assert f"{site.base}/fresh" in indexed(conn)
    assert servir.search(conn, "zeppelin")["total"] == 1
    assert sorted(page_requests(site)) == ["/", "/fresh"]  # existing pages are not re-fetched


def test_unchanged_site_costs_one_conditional_request(site, conn, settings):
    simple_site(site, ETag='"home-v1"')
    sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    site.requests.clear()
    glaneur.crawl(conn, settings)
    assert page_requests(site) == ["/"]
    assert site.requests[-1][1].get("If-None-Match") == '"home-v1"'


def test_full_site_queues_new_pages_without_fetching(site, conn, settings):
    simple_site(site)
    s = sites.add_site(conn, site.base + "/", max_pages=3)
    glaneur.crawl(conn, settings)
    site.html("/", page("Home", "Welcome.", links=["/p0", "/p1", "/fresh"]))
    site.html("/fresh", page("Fresh", "New page."))
    site.requests.clear()
    glaneur.crawl(conn, settings)
    assert "/fresh" not in site.paths()
    status = conn.execute("SELECT status FROM urls WHERE url = ?", (f"{site.base}/fresh",)).fetchone()["status"]
    assert status == "queued"
    assert sites.get_site(conn, s["id"])["at_limit"] is True


def test_redirecting_start_page_still_discovers(site, conn, settings):
    site.raw("/robots.txt", "", "text/plain")
    site.redirect("/", "/home")
    site.html("/home", page("Home", "Welcome.", links=["/p0"]))
    site.html("/p0", page("Page 0", "First page."))
    sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    assert indexed(conn) == {f"{site.base}/home", f"{site.base}/p0"}
    site.html("/home", page("Home", "Welcome.", links=["/p0", "/fresh"]))
    site.html("/fresh", page("Fresh", "Fresh page via redirect."))
    glaneur.crawl(conn, settings)
    assert f"{site.base}/fresh" in indexed(conn)


def test_pages_without_a_copy_are_fetched_unconditionally(site, conn, settings):
    # A noindex page with an ETag: once it becomes indexable it must not get a 304.
    simple_site(site, n=0)
    site.html("/", page("Home", "Welcome.", links=["/hidden"]))
    site.html("/hidden", page("Hidden", "secret words", head='<meta name="robots" content="noindex">'), ETag='"h1"')
    sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    site.html("/hidden", page("Hidden", "public words now"), ETag='"h1"')
    glaneur.crawl(conn, settings, mode="recrawl")
    assert f"{site.base}/hidden" in indexed(conn)


def test_sitemap_lastmod_requeues_changed_pages(site, conn, settings):
    simple_site(site)
    site.raw("/sitemap.xml", "<urlset><url><loc>{base}/p0</loc><lastmod>2000-01-01</lastmod></url></urlset>", "application/xml")
    s = sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    site.html("/p0", page("Page 0", "Rewritten with the word quokka."))
    site.raw("/sitemap.xml", "<urlset><url><loc>{base}/p0</loc><lastmod>2999-01-01T00:00:00+00:00</lastmod></url></urlset>", "application/xml")
    conn.execute("UPDATE sites SET sitemap_checked_at = NULL WHERE id = ?", (s["id"],))  # pretend the recheck interval passed
    conn.commit()
    glaneur.crawl(conn, settings)
    assert servir.search(conn, "quokka")["total"] == 1


def test_sitemaps_are_rechecked_at_most_every_few_hours(site, conn, settings):
    simple_site(site)
    sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    site.requests.clear()
    glaneur.crawl(conn, settings)
    assert "/sitemap.xml" not in site.paths()


def test_start_page_redirecting_off_site_is_reported(site, conn, settings):
    site.raw("/robots.txt", "", "text/plain")
    site.redirect("/", "https://elsewhere.invalid/")
    s = sites.add_site(conn, site.base + "/")
    glaneur.crawl(conn, settings)
    info = sites.get_site(conn, s["id"])
    assert info["status"] == "error" and "outside the site" in info["last_error"]


# -- parallelism -------------------------------------------------------------------------


def _overlaps(a, b):
    return any(s1 < e2 and s2 < e1 for _, s1, e1 in a for _, s2, e2 in b)


def test_different_hosts_are_crawled_in_parallel(site, other_site, conn, settings):
    for label, s in (("first", site), ("second", other_site)):
        simple_site(s, n=3, label=label)
        s.delay = 0.15
        sites.add_site(conn, s.base + "/")
    counts = glaneur.crawl(conn, settings, workers=2)
    assert counts["pages_indexed"] == 8
    assert _overlaps(site.timings, other_site.timings)


def test_one_host_is_never_hit_concurrently(site, conn, settings):
    site.raw("/robots.txt", "", "text/plain")
    for section in ("a", "b"):
        site.html(f"/{section}/", page(section, f"Section {section}.", links=[f"/{section}/x", f"/{section}/y"]))
        site.html(f"/{section}/x", page("x", f"{section} x"))
        site.html(f"/{section}/y", page("y", f"{section} y"))
        sites.add_site(conn, f"{site.base}/{section}/")
    site.delay = 0.05
    glaneur.crawl(conn, settings, workers=4)
    assert len([p for p, _, _ in site.timings if p not in ("/robots.txt", "/sitemap.xml")]) == 6
    spans = sorted((s, e) for _, s, e in site.timings)
    assert all(spans[i][1] <= spans[i + 1][0] + 1e-3 for i in range(len(spans) - 1))


def test_empty_site_list_crawls_nothing(site, conn, settings):
    simple_site(site)
    sites.add_site(conn, site.base + "/")
    assert glaneur.crawl(conn, settings, site_ids=[])["sites"] == 0
    assert site.paths() == []


def test_time_limit_stops_gracefully(site, conn, settings):
    simple_site(site, n=10)
    site.delay = 0.2
    sites.add_site(conn, site.base + "/")
    counts = glaneur.crawl(conn, settings, max_seconds=0.5)
    assert counts["time_limited"] and counts["pages_indexed"] < 11


def test_cancel_from_another_thread(site, conn, settings):
    simple_site(site, n=10)
    site.delay = 0.1
    sites.add_site(conn, site.base + "/")
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    with pytest.raises(glaneur.Cancelled):
        glaneur.crawl(conn, settings, cancel=cancel)


# -- schedule ---------------------------------------------------------------------------------


CLOCK_START = parse_iso(utcnow()) - timedelta(hours=6)  # jobs really finish "now", after these times


def T(minutes):  # noqa: N802 - a controllable clock for scheduler tests
    return CLOCK_START + timedelta(minutes=minutes)


def test_schedule_validation(conn, settings):
    with pytest.raises(ValueError):
        schedule.save(conn, settings, {"discover_minutes": 1})  # below the politeness floor
    with pytest.raises(ValueError):
        schedule.save(conn, settings, {"workers": 99})
    with pytest.raises(ValueError):
        schedule.save(conn, settings, {"bogus": 1})
    with pytest.raises(ValueError):
        schedule.save(conn, settings, {"discover_enabled": "yes"})


def test_env_defaults_until_saved(conn, settings):
    settings.recrawl_hours = 24
    assert schedule.load(conn, settings)["refresh_enabled"] is True
    schedule.save(conn, settings, {"refresh_enabled": False})
    assert schedule.load(conn, settings)["refresh_enabled"] is False


def test_scheduler_runs_discovery_on_time_and_only_for_auto_sites(site, conn, settings):
    simple_site(site)
    auto = sites.add_site(conn, site.base + "/")
    manual = sites.add_site(conn, site.base + "/other/")
    sites.update_site(conn, manual["id"], auto_crawl=False)
    schedule.save(conn, settings, {"discover_enabled": True, "discover_minutes": 30}, now=T(0))
    jm = JobManager(settings)

    assert jm.tick(now=T(29)) is None
    job = jm.tick(now=T(31))
    assert job and job["params"]["mode"] == "new" and job["params"]["site_ids"] == [auto["id"]]
    assert job["params"]["reason"] == "scheduled-discover"
    assert jm.tick(now=T(90)) is None  # previous run still queued: never overlaps

    jm._run(job["id"])  # run the job synchronously
    finished = parse_iso(jm.get(job["id"])["finished_at"])
    info = schedule.status(conn, settings, now=finished)
    assert parse_iso(info["discover"]["next_run_at"]) == finished + timedelta(minutes=30)
    assert indexed(conn)


def test_refresh_takes_priority_and_resets_discovery(conn, settings, site):
    simple_site(site)
    sites.add_site(conn, site.base + "/")
    schedule.save(conn, settings, {"discover_enabled": True, "discover_minutes": 60, "refresh_enabled": True, "refresh_hours": 1}, now=T(0))
    jm = JobManager(settings)
    job = jm.tick(now=T(61))
    assert job["params"]["mode"] == "recrawl"
    jm._run(job["id"])
    end = parse_iso(jm.get(job["id"])["finished_at"])
    info = schedule.status(conn, settings, now=end)
    assert parse_iso(info["discover"]["next_run_at"]) == end + timedelta(minutes=60)


def test_scheduler_skips_when_a_manual_job_is_running(conn, settings, site):
    simple_site(site)
    sites.add_site(conn, site.base + "/")
    schedule.save(conn, settings, {"discover_enabled": True, "discover_minutes": 5}, now=T(0))
    jm = JobManager(settings)
    manual = jm.submit_crawl()
    assert jm.tick(now=T(10)) is None
    jm._run(manual["id"])
    assert jm.tick(now=T(10)) is not None  # due run happens once the manual job is done


def test_env_enabled_schedule_waits_one_interval(conn, settings, site):
    simple_site(site)
    sites.add_site(conn, site.base + "/")
    settings.discover_minutes = 15
    jm = JobManager(settings)
    assert jm.tick(now=T(0)) is None  # starts the clock instead of firing immediately
    assert jm.tick(now=T(14)) is None
    assert jm.tick(now=T(16)) is not None


def test_schedule_survives_restart(conn, settings, site):
    simple_site(site)
    sites.add_site(conn, site.base + "/")
    schedule.save(conn, settings, {"discover_enabled": True, "discover_minutes": 30}, now=T(0))
    first = JobManager(settings).tick(now=T(31))
    JobManager(settings)._run(first["id"])
    end = parse_iso(JobManager(settings).get(first["id"])["finished_at"])
    again = JobManager(settings)  # "restart"
    assert again.tick(now=end + timedelta(minutes=29)) is None
    assert again.tick(now=end + timedelta(minutes=31)) is not None


# -- migration -------------------------------------------------------------------------------


def test_v2_database_is_upgraded(tmp_path):
    path = tmp_path / "v2.db"
    conn = connect(path)
    init_db(conn)
    s = sites.add_site(conn, "https://example.com/")
    conn.execute("UPDATE urls SET etag = '\"x\"' WHERE site_id = ?", (s["id"],))
    conn.execute("ALTER TABLE sites DROP COLUMN auto_crawl")
    conn.execute("ALTER TABLE sites DROP COLUMN sitemap_checked_at")
    conn.execute("ALTER TABLE documents DROP COLUMN link_density")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    conn = connect(path)
    init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert sites.get_site(conn, s["id"])["auto_crawl"] is True
    assert conn.execute("SELECT COUNT(*) FROM urls WHERE etag IS NOT NULL").fetchone()[0] == 0
    assert json  # imported for parity with other tests


# -- ranking ------------------------------------------------------------------------------------


def test_link_heavy_index_pages_rank_below_topical_pages(site, conn, settings):
    site.raw("/robots.txt", "", "text/plain")
    index_links = "".join(f'<a href="/x{i}">widget function {i}</a> ' for i in range(60))
    site.html("/", page("Home", "Start.", links=["/genindex", "/widgets"]))
    site.html("/genindex", f"<html><head><title>Index</title></head><body><main><p>All entries.</p>{index_links}</main></body></html>")
    site.html("/widgets", page("Working with widgets", "Widgets are reusable functions. " * 5))
    s = sites.add_site(conn, site.base + "/", max_depth=1)
    glaneur.crawl(conn, settings, site_ids=[s["id"]])
    density = dict(conn.execute("SELECT url, link_density FROM documents").fetchall())
    assert density[f"{site.base}/genindex"] > 0.8 > density[f"{site.base}/widgets"]
    assert servir.search(conn, "widget function")["results"][0]["url"] == f"{site.base}/widgets"


def test_parallel_stress_no_lock_errors(conn, settings):
    from .conftest import FixtureSite

    hosts = [FixtureSite() for _ in range(4)]
    try:
        for h_i, h in enumerate(hosts):
            simple_site(h, n=25, label=f"host{h_i}")
            sites.add_site(conn, h.base + "/")
        counts = glaneur.crawl(conn, settings, workers=4)
        assert counts["errors"] == 0
        assert counts["pages_indexed"] == 4 * 26
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 104
    finally:
        for h in hosts:
            h.close()


def test_cancel_leaves_unstarted_sites_untouched(conn, settings):
    """Sites still waiting for a worker when a crawl is cancelled must not be touched or marked crawled."""
    from .conftest import FixtureSite

    hosts = [FixtureSite() for _ in range(3)]
    try:
        for i, h in enumerate(hosts):
            simple_site(h, n=5, label=f"host{i}")
            h.delay = 0.1
        ids = [sites.add_site(conn, h.base + "/")["id"] for h in hosts]
        cancel = threading.Event()
        threading.Timer(0.4, cancel.set).start()
        with pytest.raises(glaneur.Cancelled):
            glaneur.crawl(conn, settings, workers=1, cancel=cancel)
        started = [h for h in hosts if h.paths()]
        assert len(started) == 1, "only the first host should have been contacted"
        untouched = [sites.get_site(conn, i) for i, h in zip(ids, hosts, strict=True) if not h.paths()]
        assert all(s["status"] == "pending" and s["last_crawled_at"] is None for s in untouched)
        assert all(conn.execute("SELECT sitemap_checked_at FROM sites WHERE id = ?", (s["id"],)).fetchone()[0] is None for s in untouched)
        # The next run starts with the sites that were never crawled.
        order = [r["id"] for r in conn.execute("SELECT id FROM sites ORDER BY last_crawled_at IS NOT NULL, last_crawled_at, id")]
        assert order[:2] == [s["id"] for s in untouched]
    finally:
        for h in hosts:
            h.close()
