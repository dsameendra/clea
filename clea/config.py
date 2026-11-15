"""Runtime configuration, read from environment variables.

Every setting has a safe default so ``python -m clea serve`` works out of the box
on a developer machine (bound to 127.0.0.1, no token needed).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("CLEA_DB", ROOT_DIR / "data" / "clea.db")))
    host: str = field(default_factory=lambda: os.environ.get("CLEA_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("CLEA_PORT", "6942")))
    # Token protecting the admin API (sites, crawls, jobs). Required whenever the
    # server listens on a non-loopback interface.
    admin_token: str = field(default_factory=lambda: os.environ.get("CLEA_ADMIN_TOKEN", ""))
    # Extra browser origins allowed to call the API cross-origin (comma separated).
    cors_origins: list[str] = field(default_factory=lambda: _env_list("CLEA_CORS_ORIGINS", []))
    # Extra Host header values accepted (protects against DNS rebinding).
    allowed_hosts: list[str] = field(default_factory=lambda: _env_list("CLEA_ALLOWED_HOSTS", []))
    # Built frontend served at "/" in production / Docker.
    static_dir: Path = field(default_factory=lambda: Path(os.environ.get("CLEA_STATIC_DIR", ROOT_DIR / "frontend" / "dist")))
    # Crawler identity. Site owners use the contact URL to reach you.
    user_agent_contact: str = field(default_factory=lambda: os.environ.get("CLEA_CRAWLER_CONTACT", ""))
    request_timeout: float = field(default_factory=lambda: float(os.environ.get("CLEA_REQUEST_TIMEOUT", "15")))
    min_delay: float = field(default_factory=lambda: float(os.environ.get("CLEA_MIN_DELAY", "1.0")))
    max_page_bytes: int = field(default_factory=lambda: int(os.environ.get("CLEA_MAX_PAGE_BYTES", str(5 * 1024 * 1024))))
    # Automatically recrawl every site after this many hours (0 disables).
    recrawl_hours: float = field(default_factory=lambda: float(os.environ.get("CLEA_RECRAWL_HOURS", "0")))
    trust_proxy: bool = field(default_factory=lambda: _env_bool("CLEA_TRUST_PROXY", False))

    @property
    def user_agent(self) -> str:
        from . import __version__

        contact = f"; +{self.user_agent_contact}" if self.user_agent_contact else ""
        return f"CleaBot/{__version__} (self-hosted search engine{contact})"

    @property
    def is_loopback(self) -> bool:
        return self.host in LOOPBACK_HOSTS

    def validate(self) -> None:
        if not self.is_loopback and not self.admin_token:
            raise SystemExit(
                f"Refusing to listen on {self.host} without CLEA_ADMIN_TOKEN set: the admin API "
                "(adding sites, starting crawls) would be open to the network."
            )
