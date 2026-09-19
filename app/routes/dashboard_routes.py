import threading

from flask import Blueprint, jsonify, render_template

from app import registry
from app.decorators import login_required, tab_required
from app.host_metrics import get_history
from app.infra_health_cache import get_infra_health
from app.summary_job import get_summary_cache

registry.register("dashboard", "Dashboard", "dashboard.dashboard_page", icon="&#128202;")

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
@tab_required("dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@bp.route("/api/dashboard/summary")
@login_required
def api_summary():
    cache = get_summary_cache()
    return jsonify({
        "gw_count": cache["gw_count"],
        "rule_count": cache["rule_count"],
        "last_updated": cache["last_updated"],
        "history": get_history(days=30),
    })


@bp.route("/api/dashboard/health")
@login_required
def api_health():
    return jsonify(get_infra_health())


@bp.route("/api/dashboard/refresh", methods=["POST"])
@login_required
def api_refresh():
    from app.summary_job import run_summary_job
    t = threading.Thread(target=run_summary_job, daemon=True)
    t.start()
    return jsonify({"status": "accepted"}), 202


@bp.route("/api/dashboard/refresh-health", methods=["POST"])
@login_required
def api_refresh_health():
    from app.infra_health_cache import refresh_infra_health
    t = threading.Thread(target=refresh_infra_health, daemon=True)
    t.start()
    return jsonify({"status": "accepted"}), 202
