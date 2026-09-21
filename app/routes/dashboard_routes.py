import threading

from flask import Blueprint, jsonify, render_template

from app import registry
from app.decorators import login_required, tab_required
from app.host_metrics import get_history
from app.infra_health_cache import get_infra_health
from app.summary_job import get_summary_cache

registry.register("dashboard", "Dashboard", "dashboard.dashboard_page", icon="📊")

bp = Blueprint("dashboard", __name__, url_prefix="/")

_summary_running = threading.Event()
_health_running = threading.Event()


@bp.route("/dashboard")
@login_required
@tab_required("dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@bp.route("/api/dashboard/summary")
@login_required
@tab_required("dashboard")
def api_summary():
    cache = get_summary_cache()
    return jsonify({
        "gw_count": cache["gw_count"],
        "rule_count": cache["rule_count"],
        "last_updated": cache["last_updated"],
        "domain_breakdown": cache.get("domain_breakdown", []),
        "history": get_history(days=30),
    })


@bp.route("/api/dashboard/health")
@login_required
@tab_required("dashboard")
def api_health():
    return jsonify(get_infra_health())


@bp.route("/api/dashboard/refresh", methods=["POST"])
@login_required
@tab_required("dashboard")
def api_refresh():
    if _summary_running.is_set():
        return jsonify({"status": "already_running"}), 202

    def _run():
        _summary_running.set()
        try:
            from app.summary_job import run_summary_job
            run_summary_job()
        finally:
            _summary_running.clear()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "accepted"}), 202


@bp.route("/api/dashboard/refresh-health", methods=["POST"])
@login_required
@tab_required("dashboard")
def api_refresh_health():
    if _health_running.is_set():
        return jsonify({"status": "already_running"}), 202

    def _run():
        _health_running.set()
        try:
            from app.infra_health_cache import refresh_infra_health
            refresh_infra_health()
        finally:
            _health_running.clear()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "accepted"}), 202
