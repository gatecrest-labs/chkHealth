from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.app_logger import app_log
from app.cp_helpers import make_client
from app.domain_cache import get_cached_domains
from app.host_metrics import upsert_summary

_lock = threading.Lock()
_cache: dict = {"gw_count": 0, "rule_count": 0, "last_updated": None}


def get_summary_cache() -> dict:
    with _lock:
        return dict(_cache)


def run_summary_job() -> None:
    app_log("INFO", "summary_job", "Starting summary collection")
    domains = get_cached_domains().get("domains", [])
    total_gw = 0
    total_rules = 0

    for domain in domains:
        domain_name = domain.get("name", "")
        try:
            with make_client(domain=domain_name) as client:
                total_gw += len(client.get_gateways()) + len(client.get_clusters())
                for pkg in client.get_packages():
                    total_rules += sum(
                        1 for r in client.get_access_rulebase(pkg["name"])
                        if r.get("type") == "access-rule"
                    )
        except Exception as exc:
            app_log("WARN", "summary_job", "Failed to collect from domain",
                    domain=domain_name, exc=str(exc))

    try:
        upsert_summary(datetime.now(timezone.utc).date().isoformat(), total_gw, total_rules)
    except Exception as exc:
        app_log("ERROR", "summary_job", "Failed to write to metrics DB", exc=str(exc))

    with _lock:
        _cache.update({
            "gw_count": total_gw,
            "rule_count": total_rules,
            "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    app_log("INFO", "summary_job", "Summary collection complete",
            gw_count=total_gw, rule_count=total_rules)
