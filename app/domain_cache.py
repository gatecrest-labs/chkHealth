from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.app_logger import app_log

_lock = threading.Lock()
_cache: dict = {"domains": [], "last_updated": None, "status": "empty"}


def get_cached_domains() -> dict:
    with _lock:
        return dict(_cache)


def refresh_domains() -> None:
    from app.config import Config
    from app.cp_client import CPClient

    # Try each configured MDS host in order.  The HQ MDS (CP_MDS_PRIMARY)
    # returns only the special "Global" policy domain — not actual CMAs — so
    # we skip any host whose result is only Global and fall through to the
    # Colo MDS (CP_MDS_3) which manages the real CMAs.
    candidates = [
        (Config.CP_MDS_PRIMARY,   Config.CP_MDS_PRIMARY_LABEL),
        (Config.CP_MDS_SECONDARY, Config.CP_MDS_SECONDARY_LABEL),
        (Config.CP_MDS_3,         Config.CP_MDS_3_LABEL),
        (Config.CP_MDS_4,         Config.CP_MDS_4_LABEL),
    ]
    domains: list[dict] = []
    for host, label in candidates:
        if not host:
            continue
        try:
            client = CPClient(host, Config.CP_API_KEY, Config.CP_VERIFY_SSL, Config.CP_TIMEOUT)
            client.login()
            try:
                all_domains = client.get_domains()
                cma_domains = [d for d in all_domains
                               if d.get("name", "").lower() != "global"]
                if cma_domains:
                    domains = cma_domains
                    break
                app_log("DEBUG", "domain_cache",
                        f"{label} returned no CMAs (Global only) — trying next host")
            finally:
                client.logout()
        except Exception as exc:
            app_log("WARN", "domain_cache",
                    f"Could not get domains from {label}", exc=str(exc))

    if not domains:
        app_log("ERROR", "domain_cache", "No CMA domains found on any configured host")
        with _lock:
            _cache["status"] = "error"
        return

    with _lock:
        _cache.update({
            "domains": domains,
            "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "ok",
        })
    app_log("INFO", "domain_cache", "Domain list refreshed", count=len(domains))
