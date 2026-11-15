"""Shared fixtures: a temporary database and a scriptable local website."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from clea.config import Settings
from clea.db import connect, init_db


def page(title: str, body: str, *, head: str = "", links: list[str] | tuple = ()) -> str:
    anchors = "".join(f'<a href="{href}">link</a>' if not href.startswith("<") else href for href in links)
    return (
        f"<!doctype html><html lang='en'><head><title>{title}</title>{head}</head>"
        f"<body><nav><a href='/'>Home</a> navigation menu</nav><main><h1>{title}</h1><p>{body}</p>{anchors}</main>"
        f"<footer>footer boilerplate text</footer></body></html>"
    )


class FixtureSite:
    """A tiny website whose routes can be edited by tests. Records every request path."""

    def __init__(self):
        self.routes: dict[str, tuple[int, dict, str]] = {}
        self.requests: list[tuple[str, dict]] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                site.requests.append((self.path, dict(self.headers)))
                status, headers, body = site.routes.get(self.path, (404, {"Content-Type": "text/html"}, "<h1>Not found</h1>"))
                etag = headers.get("ETag")
                if etag and self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    self.end_headers()
                    return
                data = body.encode("utf-8")
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value.replace("{base}", site.base))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def html(self, path: str, content: str, status: int = 200, **headers):
        self.routes[path] = (status, {"Content-Type": "text/html; charset=utf-8", **headers}, content)

    def raw(self, path: str, content: str, content_type: str, status: int = 200):
        self.routes[path] = (status, {"Content-Type": content_type}, content.replace("{base}", self.base))

    def redirect(self, path: str, location: str, status: int = 301):
        self.routes[path] = (status, {"Location": location, "Content-Type": "text/html"}, "")

    def paths(self) -> list[str]:
        return [p for p, _ in self.requests]

    def close(self):
        self.server.shutdown()


@pytest.fixture
def site():
    s = FixtureSite()
    yield s
    s.close()


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=tmp_path / "clea.db", min_delay=0.0, request_timeout=5, admin_token="", host="127.0.0.1")


@pytest.fixture
def conn(settings):
    c = connect(settings.db_path)
    init_db(c)
    yield c
    c.close()
