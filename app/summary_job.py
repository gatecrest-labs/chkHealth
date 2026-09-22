from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from app.app_logger import app_log
from app.cp_helpers import make_client
from app.domain_cache import get_cached_domains
from app.host_metrics import upsert_summary

_DOMAIN_QUERY_DELAY = 10

_lock = threading.Lock()
_cache: dict = {"gw_count": 0, "rule_count": 0, "last_updated": None, "domain_breakdown": [],
                 "gw_single": 0, "gw_cluster_members": 0}


def get_summary_cache() -> dict:
    from app.host_metrics import get_history
    rows = get_history(days=1)
    with _lock:
        ts = _cache.get("last_updated")
        breakdown = list(_cache.get("domain_breakdown", []))
        gw_single = _cache.get("gw_single", 0)
        gw_cluster_members = _cache.get("gw_cluster_members", 0)
    if rows:
        latest = rows[-1]
        return {
            "gw_count": latest["gw_count"],
            "rule_count": latest["rule_count"],
            "last_updated": ts or (latest["date"] + "T00:00:00+00:00"),
            "domain_breakdown": breakdown,
            "gw_single": gw_single,
            "gw_cluster_members": gw_cluster_members,
        }
    return {"gw_count": 0, "rule_count": 0, "last_updated": ts, "domain_breakdown": breakdown,
            "gw_single": gw_single, "gw_cluster_members": gw_cluster_members}


def run_summary_job() -> None:
    app_log("INFO", "summary_job", "Starting summary collection")
    domains = get_cached_domains().get("domains", [])
    total_gw = 0
    total_rules = 0
    total_single = 0
    total_cluster_members = 0
    domain_results: list[dict] = []

    _DOMAIN_TIMEOUT = 150  # seconds per domain; rule collection on large domains is slow

    for i, domain in enumerate(domains):
        domain_name = domain.get("name", "")
        if i > 0:
            time.sleep(_DOMAIN_QUERY_DELAY)

        _result: dict = {}

        def _collect(d=domain_name, r=_result):
            try:
                with make_client(domain=d) as client:
                    single_gws = client.get_gateways()
                    clusters = client.get_clusters(details_level="full")
                    r["gw"] = len(single_gws) + len(clusters)
                    r["gw_single"] = len(single_gws)
                    r["gw_cluster_members"] = sum(len(c.get("cluster-members", [])) for c in clusters)
                    r["gw_ok"] = True  # gateway count done; rules may still run
                    rules = 0
                    for pkg in client.get_packages():
                        for layer in client.get_access_layers(pkg["name"]):
                            rules += sum(
                                1 for rule in client.get_access_rulebase(layer["name"])
                                if rule.get("type") == "access-rule"
                            )
                    r["rules"] = rules
                    r["ok"] = True
            except Exception as exc:
                r["ok"] = False
                r["exc"] = str(exc)

        import threading as _t
        t = _t.Thread(target=_collect, daemon=True)
        t.start()
        t.join(timeout=_DOMAIN_TIMEOUT)

        if t.is_alive():
            app_log("WARN", "summary_job", "Timed out collecting from domain",
                    domain=domain_name, timeout=_DOMAIN_TIMEOUT)
            if _result.get("gw_ok"):
                total_gw += _result["gw"]
                total_single += _result.get("gw_single", 0)
                total_cluster_members += _result.get("gw_cluster_members", 0)
                domain_results.append({"name": domain_name, "gw_count": _result["gw"], "rule_count": None})
                app_log("INFO", "summary_job", "Used partial result (gateway count only)",
                        domain=domain_name, gw=_result["gw"])
        elif _result.get("ok"):
            total_gw += _result["gw"]
            total_single += _result.get("gw_single", 0)
            total_cluster_members += _result.get("gw_cluster_members", 0)
            total_rules += _result.get("rules", 0)
            domain_results.append({"name": domain_name, "gw_count": _result["gw"], "rule_count": _result.get("rules", 0)})
        else:
            app_log("WARN", "summary_job", "Failed to collect from domain",
                    domain=domain_name, exc=_result.get("exc", "unknown"))

    try:
        upsert_summary(datetime.now(timezone.utc).date().isoformat(), total_gw, total_rules)
    except Exception as exc:
        app_log("ERROR", "summary_job", "Failed to write to metrics DB", exc=str(exc))

    with _lock:
        _cache.update({
            "gw_count": total_gw,
            "rule_count": total_rules,
            "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "domain_breakdown": domain_results,
            "gw_single": total_single,
            "gw_cluster_members": total_cluster_members,
        })
    app_log("INFO", "summary_job", "Summary collection complete",
            gw_count=total_gw, rule_count=total_rules)
