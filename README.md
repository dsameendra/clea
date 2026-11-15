# Clea: A Search Engine

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![React](https://img.shields.io/badge/React-19-61dafb)
![License](https://img.shields.io/badge/License-MIT-green)
[![CI](https://github.com/dsameendra/clea/actions/workflows/ci.yml/badge.svg)](https://github.com/dsameendra/clea/actions/workflows/ci.yml)

> Cléa — from *clé* (key), unlocking answers.

Clea is a small, self-hosted search engine. Give it the sites you care about; it crawls them politely, builds a
full-text index and gives you a fast, clean search page for them. It also runs as a fully static demo on
GitHub Pages, with search happening in the browser.

![Clea Screenshot](clea_screenshot.png)

## Features

**Search**
- Full-text search with BM25 ranking (SQLite FTS5), stemming, and title/URL boosting
- Query-aware snippets with highlighted matches
- Search syntax: `"exact phrase"`, `-exclude`, `prefix*`, `site:example.com`, `intitle:word`
- Falls back to "any word" when nothing matches every word, and suggests spelling corrections ("Did you mean …")
- Autocomplete as you type
- Instant answers in the browser: a calculator (`15% of 240`, `sqrt(2)*10`, `5!`) and unit conversion
  (`10 km in miles`, `72 f to c`, `1.5 gib in mb`)
- Shareable result URLs (`?q=…&p=2`), pagination, `/` to focus search, light/dark theme
- OpenSearch, so you can add Clea as a search engine in your browser

**Crawling**
- Crawls each site breadth-first within its host and path (e.g. only `/docs/`), with page and depth limits
- Respects robots.txt (including `Crawl-delay` and `Sitemap`), `<meta name="robots">` and `rel="nofollow"`,
  waits between requests to the same host, and sends an identifying User-Agent
- Reads sitemaps, follows canonical URLs and same-site redirects, normalises URLs and skips duplicates and non-HTML files
- Recrawls use `ETag` / `Last-Modified`, so unchanged pages cost almost nothing; pages that disappear leave the index
- Crawls run in the background with live progress and can be cancelled. Optional scheduled recrawls

**Running it**
- One process: the Python server serves the API and the built web app
- An admin token protects site management whenever the server is reachable from the network
- Docker image and Compose file
- Static GitHub Pages build updated by a scheduled GitHub Action

## Quick start

Requirements: Python 3.11+ and Node.js 20+.

```bash
git clone https://github.com/dsameendra/clea.git
cd clea

# Backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install && npm run build && cd ..

# Run
python -m clea serve
```

Open <http://localhost:6942>, click the **sitemap** icon, add a site (for example
`https://docs.python.org/3/tutorial/`) and press **Crawl new pages**. Results become searchable as pages are indexed.

To load the demo's site list instead: `python -m clea sites import sites.toml`.

### Developing the frontend

Run the backend (`python -m clea serve`) and, in another terminal, the Vite dev server (it proxies `/api` to the
backend):

```bash
cd frontend
npm run dev        # http://localhost:5173
```

## Command line

```bash
python -m clea serve [--host 127.0.0.1] [--port 6942]
python -m clea sites add https://example.com/docs/ --max-pages 200 --max-depth 3
python -m clea sites list
python -m clea sites remove 3
python -m clea sites import sites.toml [--prune]
python -m clea crawl [--site 1] [--recrawl] [--max-seconds 600]
python -m clea search "flask blueprints"
python -m clea stats
python -m clea export frontend/public/data     # static index for the browser
```

## Configuration

All settings are environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `CLEA_DB` | `data/clea.db` | SQLite database path |
| `CLEA_HOST` / `CLEA_PORT` | `127.0.0.1` / `6942` | Where the server listens |
| `CLEA_ADMIN_TOKEN` | *(empty)* | Protects site management and crawling. **Required** when `CLEA_HOST` is not a loopback address |
| `CLEA_ALLOWED_HOSTS` | | Extra `Host` names to accept when no token is set (DNS-rebinding protection) |
| `CLEA_CORS_ORIGINS` | | Browser origins allowed to call the API from another site |
| `CLEA_CRAWLER_CONTACT` | | URL or email added to the crawler's User-Agent so site owners can reach you |
| `CLEA_MIN_DELAY` | `1.0` | Minimum seconds between requests to the same host |
| `CLEA_RECRAWL_HOURS` | `0` | Recrawl every site this often (0 = off) |
| `CLEA_REQUEST_TIMEOUT` | `15` | Per-request timeout in seconds |
| `CLEA_MAX_PAGE_BYTES` | `5242880` | Pages larger than this are skipped |
| `CLEA_STATIC_DIR` | `frontend/dist` | Built web app to serve |

## Docker

```bash
echo "CLEA_ADMIN_TOKEN=$(openssl rand -hex 24)" > .env
docker compose up -d
```

Open <http://localhost:6942> and enter the token under **Settings** (or when the admin panel asks). The index is
kept in the `clea-data` volume, and sites are recrawled weekly by default (`CLEA_RECRAWL_HOURS`).

## GitHub Pages demo

GitHub Pages only serves static files, so the demo works differently from a self-hosted Clea:

1. `.github/workflows/pages.yml` runs the Python crawler on the sites in [`sites.toml`](sites.toml) (on every push to
   `main`, weekly, or on demand).
2. `python -m clea export` writes the index as JSON next to the built frontend.
3. The frontend is built with `VITE_SEARCH_MODE=static`. It loads the index in a Web Worker and searches it in the
   browser with [MiniSearch](https://github.com/lucaong/minisearch): same query syntax, typo tolerance, snippets and
   suggestions. The admin panel is hidden.

To enable it, go to **Settings → Pages → Build and deployment** and set **Source** to **GitHub Actions**. Then push to
`main` or run the workflow from the **Actions** tab. Keep `sites.toml` small, because every visitor downloads the
index (a few hundred pages is a few MB).

To try the static build locally:

```bash
python -m clea export frontend/public/data
cd frontend && npm run dev:static
```

## How it works

```
clea/
  glaneur.py   crawler: frontier, robots.txt, politeness, redirects, sitemaps   (French: "gatherer")
  classeur.py  HTML → title/description/main text/links; writes documents       ("organiser")
  servir.py    query parsing, FTS5/BM25 search, snippets, suggestions, stats    ("to serve")
  sites.py     site management          jobs.py    background crawl jobs
  server.py    Flask API + web app      cli.py     command line
  db.py        schema & migrations      export.py  static index for GitHub Pages
frontend/src/
  lib/staticEngine.js   browser search engine (static mode)
  lib/instant/          calculator and unit converter (no eval)
  components/           search UI and admin panel
```

Documents are stored in SQLite and mirrored into an FTS5 index by triggers, so updates and deletions never leave
stale entries behind.

**Upgrading from Clea 1.x:** the database moved from `clea_db.db` to `data/clea.db`. The first time Clea 2 creates
its database it imports the sites from an existing `clea_db.db` in the project folder. Their pages are crawled again,
because the old index can't be converted. The old file is left untouched.

### API

| Method & path | |
|---|---|
| `GET /api/search?q=&page=&per_page=` | Search. Returns `results[{url, title, snippet, host}]`, where title and snippet are `[{text, match}]` segments, plus `total`, `suggestion` and `relaxed` |
| `GET /api/suggest?q=` | Autocomplete |
| `GET /api/stats` | Index statistics |
| `GET/POST /api/sites`, `PATCH/DELETE /api/sites/<id>` | Manage sites (admin) |
| `GET /api/sites/<id>/urls?status=failed` | Crawl problems for a site (admin) |
| `POST /api/crawl` `{site_ids?, recrawl?}` | Start a crawl job (admin) |
| `GET /api/jobs`, `GET /api/jobs/<id>`, `POST /api/jobs/<id>/cancel` | Job progress (admin) |

## Development

```bash
pip install -r requirements-dev.txt
pytest                      # backend tests (spins up a local test website)
ruff check clea tests
cd frontend && npm test && npm run lint
```

## Contributing

Contributions are welcome! Fork the repository, create a branch, and open a pull request. Please run the tests first.

## License

MIT, see [LICENSE](LICENSE).

## Acknowledgements

[Flask](https://flask.palletsprojects.com/) · [SQLite FTS5](https://www.sqlite.org/fts5.html) ·
[Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) · [Protego](https://github.com/scrapy/protego) ·
[React](https://react.dev/) · [Mantine](https://mantine.dev/) · [MiniSearch](https://github.com/lucaong/minisearch)
