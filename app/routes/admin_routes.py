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
        return jsonify(domain_cache.get_domains())
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
