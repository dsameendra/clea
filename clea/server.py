"""HTTP API (and, in production, the built frontend)."""

from __future__ import annotations

import hmac
import logging
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import __version__, servir, sites
from .config import LOOPBACK_HOSTS, Settings
from .db import connect, init_db
from .jobs import JobConflict, JobManager

log = logging.getLogger("clea.server")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def create_app(settings: Settings | None = None, *, start_jobs: bool = True) -> Flask:
    settings = settings or Settings()
    app = Flask(__name__, static_folder=None)
    app.config["CLEA_SETTINGS"] = settings
    app.json.sort_keys = False

    conn = connect(settings.db_path)
    init_db(conn)
    conn.close()

    jobs = JobManager(settings)
    app.extensions["clea_jobs"] = jobs
    if start_jobs:
        jobs.start()

    allowed_hosts = LOOPBACK_HOSTS | {h.lower() for h in settings.allowed_hosts}
    if settings.host not in ("0.0.0.0", "::"):
        allowed_hosts.add(settings.host.lower())

    def db():
        if "db" not in g:
            g.db = connect(settings.db_path)
        return g.db

    @app.teardown_appcontext
    def _close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def _origin_ok(origin: str) -> bool:
        if origin in settings.cors_origins:
            return True
        parts = urlsplit(origin)
        return parts.netloc.lower() == request.host.lower()

    @app.before_request
    def _guard():
        # DNS-rebinding protection: without a token, only answer to known host names.
        hostname = (request.host.rsplit(":", 1)[0] if not request.host.startswith("[") else request.host.split("]")[0][1:]).lower()
        if not settings.admin_token and hostname not in allowed_hosts:
            return jsonify(error=f"Host '{hostname}' is not allowed. Add it to CLEA_ALLOWED_HOSTS."), 403
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and not _origin_ok(origin):
                return jsonify(error="Cross-origin request blocked"), 403
            if request.method != "DELETE" and request.content_length and not request.is_json:
                return jsonify(error="Content-Type must be application/json"), 415

    @app.after_request
    def _headers(resp: Response):
        origin = request.headers.get("Origin")
        if origin and origin in settings.cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            resp.headers["Vary"] = "Origin"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if resp.mimetype == "text/html":
            resp.headers.setdefault("Content-Security-Policy", CSP)
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def admin(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if settings.admin_token:
                supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                if not hmac.compare_digest(supplied.encode(), settings.admin_token.encode()):
                    return jsonify(error="Admin token required"), 401
            return view(*args, **kwargs)

        return wrapper

    def body() -> dict:
        data = request.get_json(silent=True)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ApiError("Expected a JSON object")
        return data

    def int_arg(name: str, default: int, lo: int, hi: int) -> int:
        try:
            value = int(request.args.get(name, default))
        except ValueError:
            raise ApiError(f"'{name}' must be a number") from None
        return max(lo, min(hi, value))

    # -- public --------------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", version=__version__)

    @app.get("/api/config")
    def config():
        return jsonify(version=__version__, mode="api", admin_token_required=bool(settings.admin_token))

    @app.get("/api/search")
    def search():
        q = request.args.get("q", "")
        page = int_arg("page", 1, 1, 1000)
        per_page = int_arg("per_page", 10, 1, servir.MAX_PER_PAGE)
        return jsonify(servir.search(db(), q, page=page, per_page=per_page))

    @app.get("/api/suggest")
    def suggest():
        return jsonify(suggestions=servir.autocomplete(db(), request.args.get("q", "")))

    @app.get("/api/stats")
    def stats():
        return jsonify(servir.stats(db()))

    # -- admin ---------------------------------------------------------------------

    @app.get("/api/sites")
    @admin
    def list_sites():
        return jsonify(sites=sites.list_sites(db()))

    @app.post("/api/sites")
    @admin
    def add_sites():
        data = body()
        urls = data.get("urls") or ([data["url"]] if data.get("url") else [])
        if not isinstance(urls, list) or not urls:
            raise ApiError("Provide 'url' or a list of 'urls'")
        if len(urls) > 500:
            raise ApiError("At most 500 URLs per request")
        added, errors = [], []
        for url in urls:
            try:
                added.append(sites.add_site(db(), str(url), max_pages=data.get("max_pages"), max_depth=data.get("max_depth")))
            except ValueError as exc:
                errors.append({"url": url, "error": str(exc)})
        return jsonify(added=added, errors=errors), 201 if added else 400

    @app.patch("/api/sites/<int:site_id>")
    @admin
    def update_site(site_id: int):
        data = body()
        try:
            site = sites.update_site(db(), site_id, max_pages=data.get("max_pages"), max_depth=data.get("max_depth"))
        except ValueError as exc:
            raise ApiError(str(exc)) from None
        if site is None:
            raise ApiError("Site not found", 404)
        return jsonify(site=site)

    @app.delete("/api/sites/<int:site_id>")
    @admin
    def delete_site(site_id: int):
        if not sites.remove_site(db(), site_id):
            raise ApiError("Site not found", 404)
        return jsonify(removed=site_id)

    @app.get("/api/sites/<int:site_id>/urls")
    @admin
    def site_urls(site_id: int):
        status = request.args.get("status")
        limit = int_arg("limit", 100, 1, 1000)
        sql = "SELECT url, depth, status, reason, http_status, fetched_at FROM urls WHERE site_id = ?"
        params: list = [site_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        rows = db().execute(sql + " ORDER BY fetched_at DESC NULLS LAST, id LIMIT ?", [*params, limit]).fetchall()
        return jsonify(urls=[dict(r) for r in rows])

    @app.post("/api/crawl")
    @admin
    def start_crawl():
        data = body()
        site_ids = data.get("site_ids")
        if site_ids is not None and (not isinstance(site_ids, list) or not all(isinstance(i, int) for i in site_ids)):
            raise ApiError("'site_ids' must be a list of site ids")
        try:
            job = jobs.submit_crawl(site_ids=site_ids or None, recrawl=bool(data.get("recrawl")))
        except JobConflict as exc:
            raise ApiError(str(exc), 409) from None
        return jsonify(job=job), 202

    @app.get("/api/jobs")
    @admin
    def list_jobs():
        return jsonify(jobs=jobs.recent())

    @app.get("/api/jobs/<int:job_id>")
    @admin
    def get_job(job_id: int):
        job = jobs.get(job_id)
        if job is None:
            raise ApiError("Job not found", 404)
        return jsonify(job=job)

    @app.post("/api/jobs/<int:job_id>/cancel")
    @admin
    def cancel_job(job_id: int):
        job = jobs.cancel(job_id)
        if job is None:
            raise ApiError("Job not found", 404)
        return jsonify(job=job)

    # -- errors --------------------------------------------------------------------

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return jsonify(error=str(exc)), exc.status

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=exc.description), exc.code
        return exc

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        log.exception("unhandled error on %s", request.path)
        return jsonify(error="Internal server error"), 500

    # -- frontend --------------------------------------------------------------------

    @app.get("/opensearch.xml")
    def opensearch():
        base = request.host_url
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
  <ShortName>Clea</ShortName>
  <Description>Search the sites indexed by this Clea instance</Description>
  <InputEncoding>UTF-8</InputEncoding>
  <Image height="16" width="16" type="image/svg+xml">{escape(base)}favicon.svg</Image>
  <Url type="text/html" method="get" template="{escape(base)}?q={{searchTerms}}"/>
  <Url type="application/x-suggestions+json" template="{escape(base)}api/opensearch/suggest?q={{searchTerms}}"/>
</OpenSearchDescription>"""
        return Response(xml, mimetype="application/opensearchdescription+xml")

    @app.get("/api/opensearch/suggest")
    def opensearch_suggest():
        q = request.args.get("q", "")
        return jsonify([q, servir.autocomplete(db(), q)])

    static_dir = Path(settings.static_dir)

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path: str = ""):
        if path.startswith("api/"):
            raise ApiError("Not found", 404)
        if not (static_dir / "index.html").exists():
            return Response(
                "Clea API is running. Build the frontend (cd frontend && npm run build) "
                "or use the Vite dev server on http://localhost:5173.",
                mimetype="text/plain",
            )
        target = (static_dir / path).resolve()
        if path and target.is_file() and static_dir.resolve() in target.parents:
            resp = send_from_directory(static_dir, path)
            if path.startswith("assets/"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        resp = send_from_directory(static_dir, "index.html")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    return app
