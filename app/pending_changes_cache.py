from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.app_logger import app_log
from app.cp_helpers import make_client
from app.domain_cache import get_cached_domains

_lock = threading.Lock()
_cache: dict[str, dict] = {}


def get_cached_gateways(domain: str) -> dict:
    with _lock:
        entry = _cache.get(domain)
    if entry is None:
        return {"gateways": [], "status": "empty", "last_updated": None}
    return dict(entry)


def refresh_pending_status() -> None:

    domains = get_cached_domains().get("domains", [])
    if not domains:
        app_log("WARN", "pending_changes_cache", "No domains available for cache refresh")
        return

    for domain_obj in domains:
        domain = domain_obj.get("name", "") if isinstance(domain_obj, dict) else str(domain_obj)
        if not domain:
            continue
        try:
            with make_client(domain=domain) as client:
                gateways = client.get_gateways_with_status()
            with _lock:
                _cache[domain] = {
                    "gateways": gateways,
                    "status": "ok",
                    "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            app_log("INFO", "pending_changes_cache",
                    "Gateway status refreshed", domain=domain, count=len(gateways))
        except Exception as exc:
            app_log("WARN", "pending_changes_cache",
                    "Failed to refresh gateway status", domain=domain, exc=str(exc))
            with _lock:
                existing = _cache.get(domain, {})
                _cache[domain] = {**existing, "status": "error"}
