from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.app_logger import app_log
from app.cp_helpers import make_client

_lock = threading.Lock()
_cache: dict = {"domains": [], "last_updated": None, "status": "empty"}


def get_cached_domains() -> dict:
    with _lock:
        return dict(_cache)


def refresh_domains() -> None:
    try:
        with make_client() as client:
            domains = client.get_domains()
        with _lock:
            _cache.update({
                "domains": domains,
                "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "ok",
            })
        app_log("INFO", "domain_cache", "Domain list refreshed", count=len(domains))
    except Exception as exc:
        app_log("ERROR", "domain_cache", "Failed to refresh domain list", exc=str(exc))
        with _lock:
            _cache["status"] = "error"
