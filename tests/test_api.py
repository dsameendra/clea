import json
import time

import pytest

from clea.server import create_app

from .conftest import page


def make_client(settings, **overrides):
    for key, value in overrides.items():
        setattr(settings, key, value)
    app = create_app(settings, start_jobs=True)
    return app, app.test_client()


@pytest.fixture
def client(settings):
    app, c = make_client(settings)
    yield c
    app.extensions["clea_jobs"].stop()


def post(c, path, data=None, **kw):
    return c.post(path, data=json.dumps(data or {}), content_type="application/json", **kw)


def wait_for_job(c, job_id, headers=None, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = c.get(f"/api/jobs/{job_id}", headers=headers).get_json()["job"]
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_health_and_config(client):
    assert client.get("/api/health").get_json()["status"] == "ok"
    assert client.get("/api/config").get_json()["admin_token_required"] is False


def test_search_validates_input(client):
    res = client.get("/api/search?q=hello&page=abc")
    assert res.status_code == 400
    res = client.get("/api/search?q=hello&per_page=100000").get_json()
    assert res["per_page"] == 50


def test_search_has_no_calculator_or_eval(client):
    # v1 evaluated "math" queries with eval(); instant answers now run client-side with a real parser.
    res = client.get("/api/search", query_string={"q": "ln(1)+().__class__.__base__.__subclasses__().__len__()"}).get_json()
    assert "calculation" not in res
    assert client.post("/api/solve").status_code in (404, 405)


def test_full_crawl_job_through_api(client, site):
    site.raw("/robots.txt", "", "text/plain")
    site.html("/", page("Home", "Welcome home.", links=["/about"]))
    site.html("/about", page("About us", "We build a tiny search engine called Clea."))
    res = post(client, "/api/sites", {"url": site.base + "/"})
    assert res.status_code == 201
    site_id = res.get_json()["added"][0]["id"]

    job = post(client, "/api/crawl", {"site_ids": [site_id]}).get_json()["job"]
    assert post(client, "/api/crawl", {}).status_code in (202, 409)
    done = wait_for_job(client, job["id"])
    assert done["status"] == "done" and done["pages_indexed"] == 2

    results = client.get("/api/search?q=tiny+search+engine").get_json()
    assert results["results"][0]["url"] == site.base + "/about"
    assert client.get("/api/stats").get_json()["documents"] == 2
    sites_list = client.get("/api/sites").get_json()["sites"]
    assert sites_list[0]["documents"] == 2 and sites_list[0]["status"] == "ok"

    assert client.delete(f"/api/sites/{site_id}").status_code == 200
    assert client.get("/api/search?q=tiny").get_json()["total"] == 0


def test_cancel_job(client, site, settings):
    settings.min_delay = 5
    site.raw("/robots.txt", "", "text/plain")
    site.html("/", page("Home", "x", links=[f"/p{i}" for i in range(5)]))
    for i in range(5):
        site.html(f"/p{i}", page(f"P{i}", "y"))
    post(client, "/api/sites", {"url": site.base + "/"})
    job = post(client, "/api/crawl").get_json()["job"]
    time.sleep(0.3)
    post(client, f"/api/jobs/{job['id']}/cancel")
    assert wait_for_job(client, job["id"])["status"] == "cancelled"


def test_add_sites_reports_errors(client):
    res = post(client, "/api/sites", {"urls": ["https://example.com/", "not a url ::", "javascript:alert(1)"]})
    body = res.get_json()
    assert res.status_code == 201 and len(body["added"]) == 1 and len(body["errors"]) == 2


def test_cross_origin_writes_are_blocked(client):
    res = post(client, "/api/sites", {"url": "https://example.com/"}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403
    res = client.post("/api/sites", data="url=https://example.com/", content_type="application/x-www-form-urlencoded")
    assert res.status_code == 415


def test_dns_rebinding_host_is_rejected(client):
    assert client.get("/api/search?q=x", headers={"Host": "attacker.example:6942"}).status_code == 403


def test_cors_only_for_configured_origins(settings):
    app, c = make_client(settings, cors_origins=["http://localhost:5173"])
    ok = c.get("/api/health", headers={"Origin": "http://localhost:5173"})
    bad = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in bad.headers
    app.extensions["clea_jobs"].stop()


def test_admin_token(settings):
    app, c = make_client(settings, admin_token="s3cret", host="0.0.0.0")
    assert c.get("/api/config").get_json()["admin_token_required"] is True
    assert c.get("/api/sites").status_code == 401
    assert c.get("/api/sites", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/sites", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    # Public endpoints stay public; with a token, any Host is accepted (e.g. behind Docker / a LAN IP).
    assert c.get("/api/search?q=x", headers={"Host": "192.168.1.20:6942"}).status_code == 200
    app.extensions["clea_jobs"].stop()


def test_refuses_network_bind_without_token(settings):
    settings.host = "0.0.0.0"
    with pytest.raises(SystemExit):
        settings.validate()


def test_security_headers_and_opensearch(client):
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff" and res.headers["Referrer-Policy"] == "no-referrer"
    xml = client.get("/opensearch.xml").get_data(as_text=True)
    assert "{searchTerms}" in xml and "OpenSearchDescription" in xml
    assert client.get("/api/opensearch/suggest?q=te").get_json()[0] == "te"


def test_unknown_api_route_is_json_404(client):
    res = client.get("/api/nope")
    assert res.status_code == 404 and res.is_json


def test_interrupted_jobs_are_marked_on_startup(settings):
    from clea.db import connect, init_db, utcnow

    conn = connect(settings.db_path)
    init_db(conn)
    conn.execute("INSERT INTO jobs (kind, status, created_at) VALUES ('crawl', 'running', ?)", (utcnow(),))
    conn.commit()
    app, c = make_client(settings)
    assert c.get("/api/jobs").get_json()["jobs"][0]["status"] == "interrupted"
    app.extensions["clea_jobs"].stop()


def test_export(conn, tmp_path):
    from clea import classeur, sites
    from clea.db import utcnow
    from clea.export import export_static

    s = sites.add_site(conn, "https://example.com/")
    url_id = conn.execute("SELECT id FROM urls").fetchone()["id"]
    classeur.index_page(conn, url_id=url_id, site_id=s["id"], url="https://example.com/",
                        page=classeur.Page(title="Hello", body="world " * 5000))
    conn.commit()
    result = export_static(conn, tmp_path / "out", body_chars=100)
    data = json.loads((tmp_path / "out" / "index.json").read_text())
    assert result["documents"] == 1 and len(data["documents"][0]["body"]) == 100
    assert ["world", 1] in data["words"]
    assert json.loads((tmp_path / "out" / "stats.json").read_text())["documents"] == 1
    assert utcnow()


def test_crawl_settings_api(client):
    res = client.get("/api/crawl/settings").get_json()
    assert res["settings"]["workers"] >= 1 and res["limits"]["discover_minutes"]["min"] == 5
    assert res["schedule"]["discover"]["enabled"] is False

    saved = client.put("/api/crawl/settings", data=json.dumps({"discover_enabled": True, "discover_minutes": 30, "workers": 6}),
                       content_type="application/json")
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["settings"]["workers"] == 6 and body["schedule"]["discover"]["next_run_at"]

    bad = client.put("/api/crawl/settings", data=json.dumps({"discover_minutes": 1}), content_type="application/json")
    assert bad.status_code == 400 and "between" in bad.get_json()["error"]


def test_crawl_settings_require_admin_token(settings):
    app, c = make_client(settings, admin_token="tok", host="0.0.0.0")
    assert c.get("/api/crawl/settings").status_code == 401
    assert c.put("/api/crawl/settings", data="{}", content_type="application/json").status_code == 401
    app.extensions["clea_jobs"].stop()


def test_crawl_request_validation(client):
    assert post(client, "/api/crawl", {"site_ids": []}).status_code == 400
    assert post(client, "/api/crawl", {"site_ids": [True]}).status_code == 400
    assert post(client, "/api/crawl", {"mode": "sideways"}).status_code == 400


def test_site_auto_crawl_toggle(client):
    site = post(client, "/api/sites", {"url": "https://example.com/"}).get_json()["added"][0]
    assert site["auto_crawl"] is True and site["at_limit"] is False
    res = client.patch(f"/api/sites/{site['id']}", data=json.dumps({"auto_crawl": False}), content_type="application/json")
    assert res.get_json()["site"]["auto_crawl"] is False
    res = client.patch(f"/api/sites/{site['id']}", data=json.dumps({"auto_crawl": "no"}), content_type="application/json")
    assert res.status_code == 400
