import threading as _threading
import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz

from flask import Blueprint, jsonify, render_template, request, session

from app.decorators import admin_required
from app.groups import create_group, delete_group, get_group, list_groups, update_group
from app.auth import list_users
from app.app_logger import app_log, clear_log_entries, get_log_entries, set_log_level
from app.app_settings import get_all as get_all_settings, set_setting
from app import registry
from app.security import internal_api_error

bp = Blueprint("admin", __name__)


@bp.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html", user=session["user"])


@bp.route("/admin/api/users")
@admin_required
def api_users():
    return jsonify(list_users())


@bp.route("/admin/api/groups", methods=["GET"])
@admin_required
def api_groups_list():
    return jsonify(list_groups())


@bp.route("/admin/api/groups", methods=["POST"])
@admin_required
def api_groups_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if get_group(name):
        return jsonify({"error": f"Group '{name}' already exists"}), 409
    try:
        create_group(name, data)
        app_log("INFO", "admin", "Group created", name=name, by=session.get("user"))
        return jsonify({"ok": True}), 201
    except Exception as exc:
        return internal_api_error("admin", exc)


@bp.route("/admin/api/groups/<name>", methods=["PUT"])
@admin_required
def api_groups_update(name: str):
    if not get_group(name):
        return jsonify({"error": "Group not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        update_group(name, data)
        app_log("INFO", "admin", "Group updated", name=name, by=session.get("user"))
        return jsonify({"ok": True})
    except Exception as exc:
        return internal_api_error("admin", exc)


@bp.route("/admin/api/groups/<name>", methods=["DELETE"])
@admin_required
def api_groups_delete(name: str):
    if not delete_group(name):
        return jsonify({"error": "Group not found"}), 404
    app_log("INFO", "admin", "Group deleted", name=name, by=session.get("user"))
    return jsonify({"ok": True})


@bp.route("/admin/api/domains")
@admin_required
def api_domains():
    try:
        from app import domain_cache
        cache = domain_cache.get_cached_domains()
        return jsonify(cache.get("domains", []))
    except Exception:
        return jsonify([])


@bp.route("/admin/api/logs")
@admin_required
def api_logs():
    level = request.args.get("level") or None
    component = request.args.get("component") or None
    limit = min(int(request.args.get("limit", "500")), 2000)
    return jsonify(get_log_entries(level=level, component=component, limit=limit))


@bp.route("/admin/api/logs/level", methods=["POST"])
@admin_required
def api_logs_level():
    data = request.get_json(silent=True) or {}
    level = (data.get("level") or "").upper()
    try:
        set_log_level(level)
        return jsonify({"ok": True, "level": level})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/admin/api/logs", methods=["DELETE"])
@admin_required
def api_logs_clear():
    clear_log_entries()
    return jsonify({"ok": True})


@bp.route("/admin/api/tabs")
@admin_required
def api_tabs():
    return jsonify(registry.known_tabs())


@bp.route("/admin/api/settings", methods=["GET"])
@admin_required
def api_settings_get():
    return jsonify(get_all_settings())


@bp.route("/admin/api/settings", methods=["PUT"])
@admin_required
def api_settings_put():
    data = request.get_json(silent=True) or {}
    for key, value in data.items():
        set_setting(key, value)
    return jsonify({"ok": True})


# ── Config-Delta Jobs ─────────────────────────────────────────────────────

_CD_RUNNING: dict[str, bool] = {}
_CD_LOCK = _threading.Lock()


@bp.route("/admin/api/config-delta/jobs", methods=["GET"])
@admin_required
def api_cd_jobs_list():
    from app.config_delta_scheduler import load_jobs
    return jsonify(load_jobs())


@bp.route("/admin/api/config-delta/jobs", methods=["POST"])
@admin_required
def api_cd_jobs_create():
    from app.config_delta_scheduler import load_jobs, save_jobs
    data = request.get_json(silent=True) or {}
    required = ("domain", "email", "format")
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"'{field}' is required"}), 400
    jobs = load_jobs()
    new_job = {
        "id": str(_uuid.uuid4()),
        "domain": data["domain"],
        "days_of_week": data.get("days_of_week", []),
        "time": data.get("time", "06:00"),
        "format": data["format"],
        "email": data["email"],
        "enabled": bool(data.get("enabled", True)),
        "created_at": _dt.now(_tz.utc).isoformat(timespec="seconds"),
        "runs": [],
    }
    jobs.append(new_job)
    save_jobs(jobs)
    app_log("INFO", "admin", "Config-Delta job created",
            job_id=new_job["id"], by=session.get("user"))
    return jsonify(new_job), 201


@bp.route("/admin/api/config-delta/jobs/<job_id>", methods=["PUT"])
@admin_required
def api_cd_jobs_update(job_id: str):
    from app.config_delta_scheduler import load_jobs, save_jobs
    jobs = load_jobs()
    for job in jobs:
        if job.get("id") == job_id:
            data = request.get_json(silent=True) or {}
            for field in ("domain", "days_of_week", "time", "format", "email", "enabled"):
                if field in data:
                    job[field] = data[field]
            save_jobs(jobs)
            app_log("INFO", "admin", "Config-Delta job updated",
                    job_id=job_id, by=session.get("user"))
            return jsonify({"ok": True})
    return jsonify({"error": "Job not found"}), 404


@bp.route("/admin/api/config-delta/jobs/<job_id>", methods=["DELETE"])
@admin_required
def api_cd_jobs_delete(job_id: str):
    from app.config_delta_scheduler import load_jobs, save_jobs
    jobs = load_jobs()
    new_jobs = [j for j in jobs if j.get("id") != job_id]
    if len(new_jobs) == len(jobs):
        return jsonify({"error": "Job not found"}), 404
    save_jobs(new_jobs)
    app_log("INFO", "admin", "Config-Delta job deleted",
            job_id=job_id, by=session.get("user"))
    return jsonify({"ok": True})


@bp.route("/admin/api/config-delta/jobs/<job_id>/run", methods=["POST"])
@admin_required
def api_cd_jobs_run(job_id: str):
    from app.config_delta_scheduler import load_jobs, execute_job
    jobs = load_jobs()
    job = next((j for j in jobs if j.get("id") == job_id), None)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    with _CD_LOCK:
        if _CD_RUNNING.get(job_id):
            return jsonify({"error": "Job is already running"}), 409
        _CD_RUNNING[job_id] = True

    def _run():
        try:
            execute_job(job)
        finally:
            with _CD_LOCK:
                _CD_RUNNING.pop(job_id, None)

    _threading.Thread(target=_run, daemon=True).start()
    app_log("INFO", "admin", "Config-Delta job triggered manually",
            job_id=job_id, by=session.get("user"))
    return jsonify({"ok": True}), 202


@bp.route("/admin/api/config-delta/jobs/<job_id>/status", methods=["GET"])
@admin_required
def api_cd_jobs_status(job_id: str):
    from app.config_delta_scheduler import load_jobs
    jobs = load_jobs()
    job = next((j for j in jobs if j.get("id") == job_id), None)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    runs = job.get("runs", [])
    last_run = runs[-1] if runs else None
    with _CD_LOCK:
        running = bool(_CD_RUNNING.get(job_id))
    return jsonify({"running": running, "last_run": last_run})


# ── Rule Hygiene Jobs ─────────────────────────────────────────────────────────

@bp.route("/admin/api/hygiene-jobs", methods=["GET"])
@admin_required
def api_rh_jobs_list():
    from app.rule_hygiene_scheduler import get_all_jobs
    return jsonify(get_all_jobs())


@bp.route("/admin/api/hygiene-jobs", methods=["POST"])
@admin_required
def api_rh_jobs_create():
    from app.rule_hygiene_scheduler import create_job
    data = request.get_json(silent=True) or {}
    try:
        job = create_job(data)
        app_log("INFO", "admin", "Rule Hygiene job created",
                job_id=job["id"], by=session.get("user"))
        return jsonify(job), 201
    except (ValueError, KeyError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/admin/api/hygiene-jobs/<job_id>", methods=["PUT"])
@admin_required
def api_rh_jobs_update(job_id: str):
    from app.rule_hygiene_scheduler import update_job
    data = request.get_json(silent=True) or {}
    try:
        job = update_job(job_id, data)
        app_log("INFO", "admin", "Rule Hygiene job updated",
                job_id=job_id, by=session.get("user"))
        return jsonify(job)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/admin/api/hygiene-jobs/<job_id>", methods=["DELETE"])
@admin_required
def api_rh_jobs_delete(job_id: str):
    from app.rule_hygiene_scheduler import delete_job
    try:
        delete_job(job_id)
        app_log("INFO", "admin", "Rule Hygiene job deleted",
                job_id=job_id, by=session.get("user"))
        return jsonify({"ok": True})
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404


@bp.route("/admin/api/hygiene-jobs/<job_id>/run", methods=["POST"])
@admin_required
def api_rh_jobs_run(job_id: str):
    from app.rule_hygiene_scheduler import get_all_jobs, run_job_now, is_job_running
    jobs = get_all_jobs()
    if not any(j["id"] == job_id for j in jobs):
        return jsonify({"error": "Job not found"}), 404
    if is_job_running(job_id):
        return jsonify({"error": "Job is already running"}), 409
    run_job_now(job_id)
    app_log("INFO", "admin", "Rule Hygiene job triggered manually",
            job_id=job_id, by=session.get("user"))
    return jsonify({"ok": True}), 202


@bp.route("/admin/api/hygiene-jobs/<job_id>/status", methods=["GET"])
@admin_required
def api_rh_jobs_status(job_id: str):
    from app.rule_hygiene_scheduler import get_all_jobs, is_job_running
    jobs = get_all_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    runs = job.get("runs", [])
    last_run = runs[0] if runs else None
    return jsonify({"running": is_job_running(job_id), "last_run": last_run})


@bp.route("/admin/api/diag/policy-layers", methods=["GET"])
@admin_required
def api_diag_policy_layers():
    """Diagnostic: expose raw show-package + show-access-rulebase structure.
    Query params: domain, package
    Remove this endpoint once the inline-layer bug is confirmed fixed.
    """
    from app.cp_helpers import make_client
    from app.decorators import check_domain_access
    domain = request.args.get("domain", "").strip()
    package = request.args.get("package", "").strip()
    if not domain or not package:
        return jsonify({"error": "domain and package are required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            pkg_resp = client.call("show-package", {"name": package})
            layers = pkg_resp.get("access-layers", [])
            layer_info = []
            for layer in layers:
                lname = layer.get("name", "")
                linfo: dict = {
                    "name": lname,
                    "uid": layer.get("uid"),
                    "domain": (layer.get("domain") or {}).get("name"),
                    "domain_type": (layer.get("domain") or {}).get("domain-type"),
                }
                try:
                    rb_resp = client.call("show-access-rulebase", {
                        "name": lname, "details-level": "standard",
                        "limit": 500, "offset": 0,
                    })
                    rb = rb_resp.get("rulebase", [])
                    inline_layers = [e for e in rb if e.get("type") == "access-layer"]
                    linfo["rulebase_total"] = rb_resp.get("total")
                    linfo["rulebase_top_level_count"] = len(rb)
                    linfo["top_level_types"] = {
                        t: sum(1 for e in rb if e.get("type") == t)
                        for t in {"access-rule", "access-section", "access-layer"}
                        if any(e.get("type") == t for e in rb)
                    }
                    linfo["inline_layers"] = [
                        {
                            "name": il.get("name"),
                            "uid": il.get("uid"),
                            "nested_rule_count": len([
                                e for e in il.get("rulebase", [])
                                if e.get("type") == "access-rule"
                            ]),
                        }
                        for il in inline_layers
                    ]
                except Exception as exc:
                    linfo["rulebase_error"] = str(exc)
                layer_info.append(linfo)
        return jsonify({"domain": domain, "package": package, "layers": layer_info})
    except Exception as exc:
        from app.security import upstream_api_error
        return upstream_api_error("admin_diag", exc)
