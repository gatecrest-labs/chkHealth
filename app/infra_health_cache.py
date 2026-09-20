from __future__ import annotations

import socket
import threading
from datetime import datetime, timezone

from app.app_logger import app_log
from app.cp_client import CPClient

_lock = threading.Lock()
_cache: dict = {"servers": [], "last_updated": None}


def get_infra_health() -> dict:
    with _lock:
        return {"servers": list(_cache["servers"]), "last_updated": _cache["last_updated"]}


def _poll_mds(host: str, label: str) -> dict:
    entry: dict = {
        "label": label, "host": host, "type": "MDS", "status": "unreachable",
        "hostname": None, "version": None, "serial": None, "ha_role": None,
        "cpu_pct": None, "mem_pct": None,
    }
    try:
        from app.config import Config
        client = CPClient(host, Config.CP_API_KEY, Config.CP_VERIFY_SSL, Config.CP_TIMEOUT)
        client.login()
        try:
            ver = client.get_api_version()
            entry["version"] = ver.get("current-version")
            try:
                info = client.call("show-mdss", {})
                entry["ha_role"] = info.get("ha-role")
                entry["hostname"] = info.get("name")
            except Exception:
                pass
            entry["status"] = "healthy"
        finally:
            client.logout()
    except Exception as exc:
        app_log("WARN", "infra_health", f"MDS unreachable: {label}", exc=str(exc))
    return entry


def _poll_mls(host: str, label: str) -> dict:
    entry: dict = {
        "label": label, "host": host, "type": "MLS", "status": "unreachable",
        "hostname": None, "version": None, "serial": None, "ha_role": None,
        "cpu_pct": None, "mem_pct": None,
    }
    try:
        conn = socket.create_connection((host, 443), timeout=5)
        conn.close()
        entry["status"] = "healthy"
    except OSError as exc:
        app_log("WARN", "infra_health", f"MLS unreachable: {label}", exc=str(exc))
    return entry


def refresh_infra_health() -> None:
    from app.config import Config
    servers = []
    for host, label in [
        (Config.CP_MDS_PRIMARY, Config.CP_MDS_PRIMARY_LABEL),
        (Config.CP_MDS_SECONDARY, Config.CP_MDS_SECONDARY_LABEL),
    ]:
        if host:
            servers.append(_poll_mds(host, label))
    for host, label in [
        (Config.CP_MLS_1, Config.CP_MLS_1_LABEL),
        (Config.CP_MLS_2, Config.CP_MLS_2_LABEL),
    ]:
        if host:
            servers.append(_poll_mls(host, label))
    with _lock:
        _cache["servers"] = servers
        _cache["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    app_log("INFO", "infra_health", "Infrastructure health refreshed",
            healthy=sum(1 for s in servers if s["status"] == "healthy"),
            total=len(servers))
