from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.app_logger import app_log

_lock = threading.Lock()


def _record(obj: dict, obj_type: str, domain: str, version_devices: dict) -> None:
    ver = obj.get("version") or "Unknown"
    if ver not in version_devices:
        version_devices[ver] = []
    version_devices[ver].append({
        "name": obj.get("name", ""),
        "type": obj_type,
        "domain": domain,
        "ip": obj.get("ipv4-address") or obj.get("ipv6-address") or "",
    })


_cache: dict = {
    "last_updated": None,
    "status": "empty",
    "total": 0,
    "domain_count": 0,
    "domains_ok": 0,
    "by_version": [],   # [{"version": str, "count": int, "pct": float}]
}


def get_device_versions() -> dict:
    with _lock:
        return dict(_cache)


def refresh_device_versions() -> None:
    from app.cp_helpers import make_client
    from app.domain_cache import get_cached_domains

    domains = [d["name"] for d in get_cached_domains().get("domains", [])]
    if not domains:
        app_log("WARN", "device_version_cache", "No domains available, skipping refresh")
        return

    app_log("INFO", "device_version_cache", "Starting device version collection",
            domain_count=len(domains))

    total = 0
    domains_ok = 0
    version_devices: dict[str, list[dict]] = {}

    for domain in domains:
        try:
            with make_client(domain=domain) as client:
                gateways = client._fetch_all(
                    "show-simple-gateways", {"details-level": "standard"}
                )
                clusters = client._fetch_all(
                    "show-simple-clusters", {"details-level": "standard"}
                )
            for obj in gateways:
                _record(obj, "Gateway", domain, version_devices)
                total += 1
            for obj in clusters:
                _record(obj, "Cluster", domain, version_devices)
                total += 1
            domains_ok += 1
        except Exception as exc:
            app_log("WARN", "device_version_cache", f"Failed to collect from {domain}",
                    exc=str(exc))

    by_version = sorted(
        [
            {
                "version": ver,
                "count": len(devs),
                "pct": round(len(devs) / total * 100, 1) if total else 0.0,
                "devices": sorted(devs, key=lambda d: (d["domain"], d["name"])),
            }
            for ver, devs in version_devices.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    with _lock:
        _cache.update({
            "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "ok" if domains_ok else "error",
            "total": total,
            "domain_count": len(domains),
            "domains_ok": domains_ok,
            "by_version": by_version,
        })

    app_log("INFO", "device_version_cache", "Device version collection complete",
            total=total, versions=len(by_version), domains_ok=domains_ok)
