"""Command line interface: ``python -m clea <command>``."""

from __future__ import annotations

import argparse
import logging
import sys
import tomllib
from pathlib import Path

from . import __version__, glaneur, servir, sites
from .config import DEFAULT_DB, LEGACY_DB, Settings
from .db import open_database


def _conn(settings: Settings):
    legacy = LEGACY_DB if settings.db_path == DEFAULT_DB else None
    return open_database(settings.db_path, legacy)


def cmd_init(args, settings):
    _conn(settings).close()
    print(f"Database ready at {settings.db_path}")


def cmd_serve(args, settings):
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    settings.validate()
    from .server import create_app

    app = create_app(settings)
    url = f"http://{'localhost' if settings.is_loopback else settings.host}:{settings.port}"
    print(f"Clea {__version__} serving on {url}  (database: {settings.db_path})")
    if args.dev:
        app.run(host=settings.host, port=settings.port, debug=False, use_reloader=False, threaded=True)
    else:
        from waitress import serve

        serve(app, host=settings.host, port=settings.port, threads=8, ident="clea")


def _print_sites(rows):
    if not rows:
        print("No sites yet. Add one with: python -m clea sites add https://example.com/")
        return
    for s in rows:
        print(f"[{s['id']:>3}] {s['seed_url']}  scope={s['path_prefix']}  pages={s['documents']}/{s['max_pages']} "
              f"depth<={s['max_depth']}  queued={s['queued']}  failed={s['failed']}  status={s['status']}")


def cmd_sites(args, settings):
    conn = _conn(settings)
    if args.action == "list":
        _print_sites(sites.list_sites(conn))
    elif args.action == "add":
        for url in args.urls:
            try:
                site = sites.add_site(conn, url, max_pages=args.max_pages, max_depth=args.max_depth)
                print(f"Added [{site['id']}] {site['seed_url']} (scope {site['path_prefix']})")
            except ValueError as exc:
                print(f"Skipped {url}: {exc}", file=sys.stderr)
    elif args.action == "remove":
        for site_id in args.ids:
            print(("Removed" if sites.remove_site(conn, site_id) else "No such site") + f" [{site_id}]")
    elif args.action == "import":
        import_sites(conn, Path(args.file), prune=args.prune)


def import_sites(conn, path: Path, *, prune: bool = False) -> None:
    """Sync sites from a TOML file (see sites.toml)."""
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    defaults = config.get("defaults", {})
    wanted = set()
    for entry in config.get("site", []):
        site = sites.add_site(
            conn,
            entry["url"],
            max_pages=entry.get("max_pages", defaults.get("max_pages")),
            max_depth=entry.get("max_depth", defaults.get("max_depth")),
            path_prefix=entry.get("path_prefix"),
        )
        sites.update_site(
            conn, site["id"],
            max_pages=entry.get("max_pages", defaults.get("max_pages")),
            max_depth=entry.get("max_depth", defaults.get("max_depth")),
        )
        wanted.add(site["id"])
        print(f"  [{site['id']}] {site['seed_url']}")
    if prune:
        for site in sites.list_sites(conn):
            if site["id"] not in wanted:
                sites.remove_site(conn, site["id"])
                print(f"  removed [{site['id']}] {site['seed_url']} (not in {path.name})")


def cmd_crawl(args, settings):
    conn = _conn(settings)
    if args.min_delay is not None:
        settings.min_delay = args.min_delay

    def progress(update):
        if update.get("current_url"):
            print(f"  fetched={update['pages_fetched']} indexed={update['pages_indexed']} "
                  f"skipped={update['pages_skipped']} failed={update['pages_failed']}  {update['current_url']}", flush=True)

    try:
        counts = glaneur.crawl(conn, settings, site_ids=args.site or None, recrawl=args.recrawl,
                               progress=progress, max_seconds=args.max_seconds)
    except KeyboardInterrupt:
        conn.commit()
        print("\nInterrupted; progress so far is saved.")
        return 130
    print(f"Done: {counts}")


def cmd_export(args, settings):
    from .export import export_static

    conn = _conn(settings)
    result = export_static(conn, Path(args.out), body_chars=args.body_chars)
    print(f"Exported {result['documents']} documents, {result['words']} words, {result['bytes'] / 1024:.0f} KiB → {args.out}")
    if result["documents"] < args.min_documents:
        print(f"Refusing: fewer than {args.min_documents} documents exported", file=sys.stderr)
        return 1


def cmd_search(args, settings):
    conn = _conn(settings)
    res = servir.search(conn, " ".join(args.query), per_page=args.limit)
    flat = lambda segs: "".join(s["text"] for s in segs)  # noqa: E731
    print(f"{res['total']} results in {res['took_ms']} ms" + (" (showing pages matching any word)" if res["relaxed"] else ""))
    if res["suggestion"]:
        print(f"Did you mean: {res['suggestion']}")
    for i, r in enumerate(res["results"], 1):
        print(f"\n{i}. {flat(r['title'])}\n   {r['url']}\n   {flat(r['snippet'])[:200]}")


def cmd_stats(args, settings):
    for key, value in servir.stats(_conn(settings)).items():
        print(f"{key:>16}: {value}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m clea", description="Clea — a small, self-hosted search engine")
    p.add_argument("--version", action="version", version=f"clea {__version__}")
    p.add_argument("--db", help="database path (default: data/clea.db or $CLEA_DB)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)

    s = sub.add_parser("serve", help="run the web server")
    s.add_argument("--host", help="interface to bind (default 127.0.0.1)")
    s.add_argument("--port", type=int, help="port (default 6942)")
    s.add_argument("--dev", action="store_true", help="use Flask's development server instead of waitress")
    s.set_defaults(func=cmd_serve)

    st = sub.add_parser("sites", help="manage the sites to crawl")
    st_sub = st.add_subparsers(dest="action", required=True)
    st_sub.add_parser("list")
    add = st_sub.add_parser("add")
    add.add_argument("urls", nargs="+")
    add.add_argument("--max-pages", type=int)
    add.add_argument("--max-depth", type=int)
    rm = st_sub.add_parser("remove")
    rm.add_argument("ids", nargs="+", type=int)
    imp = st_sub.add_parser("import", help="sync sites from a TOML file")
    imp.add_argument("file")
    imp.add_argument("--prune", action="store_true", help="remove sites that are not in the file")
    st.set_defaults(func=cmd_sites)

    c = sub.add_parser("crawl", help="crawl and index sites")
    c.add_argument("--site", type=int, action="append", help="site id (repeatable; default: all)")
    c.add_argument("--recrawl", action="store_true", help="re-fetch pages already crawled (uses conditional requests)")
    c.add_argument("--max-seconds", type=float, help="stop gracefully after this many seconds")
    c.add_argument("--min-delay", type=float, help="seconds between requests to the same host")
    c.set_defaults(func=cmd_crawl)

    e = sub.add_parser("export", help="export a static index for the browser (GitHub Pages)")
    e.add_argument("out", help="output directory, e.g. frontend/public/data")
    e.add_argument("--body-chars", type=int, default=6000)
    e.add_argument("--min-documents", type=int, default=0, help="exit with an error if fewer documents")
    e.set_defaults(func=cmd_export)

    q = sub.add_parser("search", help="search from the command line")
    q.add_argument("query", nargs="+")
    q.add_argument("--limit", type=int, default=10)
    q.set_defaults(func=cmd_search)

    sub.add_parser("stats", help="index statistics").set_defaults(func=cmd_stats)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    if args.db:
        settings.db_path = Path(args.db)
    return args.func(args, settings) or 0
