"""URL normalisation and crawl scoping."""

from __future__ import annotations

import posixpath
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

MAX_URL_LENGTH = 2048

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid", "igshid",
    "mc_cid", "mc_eid", "_ga", "_gl", "ref_src", "ref_url", "spm", "si",
}
TRACKING_PREFIXES = ("utm_", "pk_", "hsa_")

# File types that are never HTML; skipped before making a request.
NON_HTML_EXTENSIONS = {
    ".7z", ".apk", ".avi", ".bin", ".bmp", ".bz2", ".css", ".csv", ".deb", ".dmg", ".doc", ".docx",
    ".eot", ".epub", ".exe", ".flac", ".gif", ".gz", ".ico", ".iso", ".jar", ".jpeg", ".jpg", ".js",
    ".json", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".mpg", ".msi", ".odp", ".ods", ".odt",
    ".ogg", ".otf", ".pdf", ".pkg", ".png", ".ppt", ".pptx", ".rar", ".rpm", ".rss", ".svg", ".tar",
    ".tgz", ".tif", ".tiff", ".ttf", ".wasm", ".wav", ".webm", ".webp", ".whl", ".woff", ".woff2",
    ".xls", ".xlsx", ".xml", ".xz", ".zip",
}

DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Return a canonical form of ``url`` (resolved against ``base``), or None if unusable.

    Lower-cases scheme and host, drops default ports, credentials, fragments and
    tracking parameters, sorts the query string and resolves dot segments, so
    that trivially different spellings of a page map to one URL.
    """
    if not url:
        return None
    url = url.strip()
    if base:
        url = urljoin(base, url)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS or not parts.hostname:
        return None

    host = parts.hostname.lower().rstrip(".")
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    if ":" in host and not host.startswith("["):  # IPv6 literal
        netloc = f"[{host}]" if port in (None, DEFAULT_PORTS[scheme]) else f"[{host}]:{port}"

    path = parts.path or "/"
    if "/." in path:
        trailing = path.endswith("/")
        path = posixpath.normpath(path)
        if path.startswith("//"):
            path = "/" + path.lstrip("/")
        if trailing and not path.endswith("/"):
            path += "/"
    path = re.sub(r"/{2,}", "/", path)

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    query = urlencode(sorted(query_pairs), doseq=True)

    normalized = urlunsplit((scheme, netloc, path, query, ""))
    if len(normalized) > MAX_URL_LENGTH:
        return None
    return normalized


def bare_host(host: str) -> str:
    """Host without a leading ``www.`` so that www/non-www count as one site."""
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def default_path_prefix(seed_url: str) -> str:
    """Crawl scope derived from a seed: its directory.

    ``https://docs.python.org/3/tutorial/index.html`` → ``/3/tutorial/``;
    ``https://example.com`` → ``/``.
    """
    path = urlsplit(seed_url).path or "/"
    return path[: path.rfind("/") + 1] or "/"


def in_scope(url: str, site_host: str, path_prefix: str = "/") -> bool:
    parts = urlsplit(url)
    if not parts.hostname or bare_host(parts.hostname) != bare_host(site_host):
        return False
    return (parts.path or "/").startswith(path_prefix)


def looks_like_non_html(url: str) -> bool:
    path = urlsplit(url).path.lower()
    _, ext = posixpath.splitext(path)
    return ext in NON_HTML_EXTENSIONS


def url_terms(url: str) -> str:
    """Words from the host and path, indexed so ``flask quickstart`` matches /flask/quickstart/."""
    parts = urlsplit(url)
    host = bare_host(parts.hostname or "")
    host_words = host.split(".")[:-1] if "." in host else [host]
    path_words = re.split(r"[^0-9A-Za-z]+", parts.path)
    words = [w for w in host_words + path_words if w and w.lower() not in {"html", "htm", "php", "index", "aspx"}]
    return " ".join(words)
