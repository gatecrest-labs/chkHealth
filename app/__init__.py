from flask import Flask, jsonify, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from app.config import Config
from app.security import csrf_error_response, ensure_csrf_token, validate_csrf_request

_BLUEPRINT_MODULES = [
    "app.routes.auth_routes",
    "app.routes.admin_routes",
    "app.routes.dashboard_routes",
    # firewall_routes, rule_review_routes added in Plan 3
]


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def _security_filters():
        ensure_csrf_token()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.endpoint == "static":
                return None
            if app.config.get("WTF_CSRF_ENABLED", True) and not validate_csrf_request():
                return csrf_error_response()
        return None

    @app.after_request
    def _set_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        return resp

    @app.errorhandler(RequestEntityTooLarge)
    def _file_too_large(_exc):
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify({"error": "Uploaded file is too large"}), 413
        return "Uploaded file is too large", 413

    @app.errorhandler(Exception)
    def _unhandled_exception(exc):
        import traceback
        app.logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return "Internal server error", 500

    import importlib
    from app import registry, groups as _groups

    for module_path in _BLUEPRINT_MODULES:
        mod = importlib.import_module(module_path)
        app.register_blueprint(mod.bp)

    _groups.KNOWN_TABS.update(registry.known_tabs())

    if not app.testing:
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.host_metrics import init_db
        from app.summary_job import run_summary_job
        from app.infra_health_cache import refresh_infra_health
        from app.domain_cache import refresh_domains

        init_db()

        scheduler = BackgroundScheduler()
        scheduler.add_job(run_summary_job,      "interval", minutes=60, id="summary_job")
        scheduler.add_job(refresh_infra_health, "interval", minutes=15, id="infra_health")
        scheduler.add_job(refresh_domains,      "interval", minutes=30, id="domain_cache")
        scheduler.start()

        refresh_domains()
        refresh_infra_health()
        run_summary_job()

    @app.context_processor
    def _inject_nav():
        return {
            "nav_registry": registry.get_registry(),
            "csrf_token": session.get("_csrf_token", ""),
        }

    @app.route("/")
    def _root():
        from flask import redirect, url_for, session as s
        from app.routes.auth_routes import _first_allowed_url
        if "user" not in s:
            return redirect(url_for("auth.login"))
        return redirect(_first_allowed_url(s.get("allowed_tabs", [])))

    return app
