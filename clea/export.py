"""Export the index as static JSON for the browser-side search engine (GitHub Pages)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import __version__, servir
from .db import utcnow

FORMAT_VERSION = 1


def export_static(conn: sqlite3.Connection, out_dir: Path, *, body_chars: int = 6000, max_words: int = 30000) -> dict:
    """Write ``index.json`` (documents + vocabulary) and ``stats.json`` into ``out_dir``.

    Body text is truncated to ``body_chars`` characters per page to keep the
    download small; titles, descriptions and URLs are always complete.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    documents = [
        {
            "id": row["id"],
            "url": row["url"],
            "host": row["host"],
            "title": row["title"],
            "description": row["description"],
            "body": row["body"][:body_chars],
            "indexed_at": row["indexed_at"],
        }
        for row in conn.execute(
            "SELECT id, url, host, title, description, body, indexed_at FROM documents ORDER BY id"
        )
    ]
    words = [[r["word"], r["df"]] for r in conn.execute("SELECT word, df FROM words ORDER BY df DESC LIMIT ?", (max_words,))]
    index = {
        "format": FORMAT_VERSION,
        "generator": f"clea {__version__}",
        "generated_at": utcnow(),
        "documents": documents,
        "words": words,
    }
    stats = servir.stats(conn)
    stats["generated_at"] = index["generated_at"]

    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"documents": len(documents), "words": len(words), "bytes": index_path.stat().st_size}
