from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.app_logger import app_log

_lock = threading.Lock()


def _flush(version_devices: dict, total: int, domain_count: int,
           domains_ok: int, final: bool) -> None:
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
            "status": "ok" if final and domains_ok else ("collecting" if not final else "error"),
            "total": total,
            "domain_count": domain_count,
            "domains_ok": domains_ok,
            "by_version": by_version,
        })


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


_DOMAIN_QUERY_DELAY = 5  # seconds between domain logins to avoid MDS rate-limiting


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

    import threading as _threading
    import time as _time

    _DOMAIN_TIMEOUT = 120  # seconds per domain; large domains can have many devices

    # Mark as in-progress so the UI shows something is happening
    with _lock:
        _cache.update({"status": "collecting", "domain_count": len(domains)})

    for i, domain in enumerate(domains):
        if i > 0:
            _time.sleep(_DOMAIN_QUERY_DELAY)
        _result: dict = {}

        def _collect(d=domain, r=_result):
            try:
                with make_client(domain=d) as client:
                    r["gws"] = client._fetch_all("show-simple-gateways", {"details-level": "standard"})
                    r["cls"] = client._fetch_all("show-simple-clusters", {"details-level": "standard"})
                r["ok"] = True
            except Exception as exc:
                r["ok"] = False
                r["exc"] = str(exc)

        t = _threading.Thread(target=_collect, daemon=True)
        t.start()
        t.join(timeout=_DOMAIN_TIMEOUT)

        if t.is_alive():
            app_log("WARN", "device_version_cache",
                    f"Timed out collecting from {domain} (>{_DOMAIN_TIMEOUT}s), skipping")
        elif _result.get("ok"):
            for obj in _result["gws"]:
                _record(obj, "Gateway", domain, version_devices)
                total += 1
            for obj in _result["cls"]:
                _record(obj, "Cluster", domain, version_devices)
                total += 1
            domains_ok += 1
        else:
            app_log("WARN", "device_version_cache", f"Failed to collect from {domain}",
                    exc=_result.get("exc", "unknown"))

        # Update incrementally after each domain so partial results appear
        _flush(version_devices, total, len(domains), domains_ok, final=False)

    _flush(version_devices, total, len(domains), domains_ok, final=True)
    app_log("INFO", "device_version_cache", "Device version collection complete",
            total=total, domains_ok=domains_ok)
