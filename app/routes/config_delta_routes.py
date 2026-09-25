from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid

from flask import Blueprint, jsonify, render_template, session

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.pending_changes_cache import get_cached_gateways
from app.domain_cache import get_cached_domains
from app.groups import get_allowed_domains
from app.security import upstream_api_error
from app.app_logger import app_log

registry.register("config_delta", "Config-Delta", "config_delta.config_delta_page", icon="🔄")

bp = Blueprint("config_delta", __name__, url_prefix="/")

_TASK_TTL = 600  # seconds
_TASK_DIR = os.path.join(
    tempfile.gettempdir(),
    f"chkhealth_cd_{os.getpid()}",
)


def _task_path(task_id: str) -> str:
    return os.path.join(_TASK_DIR, f"{task_id}.json")


def _write_task(task_id: str, data: dict) -> None:
    os.makedirs(_TASK_DIR, exist_ok=True)
    with open(_task_path(task_id), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_task(task_id: str) -> dict | None:
    try:
        with open(_task_path(task_id), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _cleanup_old_tasks() -> None:
    if not os.path.exists(_TASK_DIR):
        return
    cutoff = time.time() - _TASK_TTL
    for fname in os.listdir(_TASK_DIR):
        fpath = os.path.join(_TASK_DIR, fname)
        try:
            if os.path.getmtime(fpath) < cutoff:
                os.unlink(fpath)
        except OSError:
            pass


def _launch_changes_task(domain: str, gateway: str) -> str:
    task_id = str(uuid.uuid4())
    _write_task(task_id, {"status": "running", "step": "Starting…", "result": None, "error": None})

    def _run():
        try:
            _write_task(task_id, {"status": "running", "step": "Fetching gateway info…",
                                   "result": None, "error": None})
            with make_client(domain=domain) as client:
                gateways = client.get_gateways_with_status()
                gw_obj = next((g for g in gateways if g["name"] == gateway), None)
                if gw_obj is None:
                    _write_task(task_id, {"status": "error", "step": "Failed",
                                           "result": None, "error": f"Gateway '{gateway}' not found"})
                    return

                _write_task(task_id, {"status": "running", "step": "Loading pending changes…",
                                       "result": None, "error": None})
                changes_data = client.get_pending_changes()

            result = {
                "gateway": gw_obj["name"],
                "ip": gw_obj["ip"],
                "install_status": gw_obj["install_status"],
                "policy_package": gw_obj["policy_package"],
                "summary": changes_data["summary"],
                "changes": changes_data["changes"],
            }
            _write_task(task_id, {"status": "done", "step": "Done", "result": result, "error": None})
        except Exception as exc:
            app_log("WARN", "config_delta", "Change fetch task failed",
                    domain=domain, gateway=gateway, exc=str(exc))
            _write_task(task_id, {"status": "error", "step": "Failed",
                                   "result": None, "error": str(exc)})

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    _cleanup_old_tasks()
    return task_id


@bp.route("/config-delta")
@login_required
@tab_required("config_delta")
def config_delta_page():
    return render_template("config_delta.html")


@bp.route("/api/config-delta/domains")
@login_required
@tab_required("config_delta")
def api_cd_domains():
    cached = get_cached_domains()
    all_domains = [d["name"] for d in cached.get("domains", [])]
    cache_status = cached.get("status", "empty")
    role = session.get("role", "viewer")
    if role == "admin":
        return jsonify({"domains": ["Global"] + sorted(all_domains), "status": cache_status})
    allowed = get_allowed_domains(
        session.get("user", ""), ad_groups=session.get("ad_groups", [])
    )
    if allowed is None:
        domain_list = sorted(all_domains)
    else:
        domain_list = sorted(d for d in all_domains if d in allowed)
    return jsonify({"domains": ["Global"] + domain_list, "status": cache_status})


@bp.route("/api/config-delta/domains/<domain>/gateways")
@login_required
@tab_required("config_delta")
def api_cd_gateways(domain: str):
    err = check_domain_access(domain)
    if err:
        return err
    cached = get_cached_gateways(domain)
    if cached["status"] == "empty":
        try:
            with make_client(domain=domain) as client:
                gateways = client.get_gateways_with_status()
            return jsonify({"gateways": gateways, "domain": domain, "status": "ok"})
        except Exception as exc:
            return upstream_api_error("config_delta", exc)
    return jsonify({"gateways": cached["gateways"], "domain": domain,
                    "status": cached["status"], "last_updated": cached.get("last_updated")})


@bp.route("/api/config-delta/domains/<domain>/gateway/<gateway>/changes", methods=["POST"])
@login_required
@tab_required("config_delta")
def api_cd_start_changes(domain: str, gateway: str):
    err = check_domain_access(domain)
    if err:
        return err
    task_id = _launch_changes_task(domain, gateway)
    return jsonify({"task_id": task_id}), 202


@bp.route("/api/config-delta/task/<task_id>")
@login_required
@tab_required("config_delta")
def api_cd_task(task_id: str):
    data = _read_task(task_id)
    if data is None:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(data)
