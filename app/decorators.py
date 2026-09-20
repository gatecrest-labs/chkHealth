from __future__ import annotations

import time as _time
from functools import wraps

from flask import abort, jsonify, redirect, request, session as flask_session, url_for
from flask import current_app


def _revalidate_session() -> tuple | None:
    login_at = flask_session.get("login_at")
    if login_at is None:
        flask_session.clear()
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify({"error": "Session expired — please reload and log in again"}), 401
        return redirect(url_for("auth.login")), 302

    lifetime = current_app.config.get("SESSION_ABSOLUTE_LIFETIME", 36000)
    if _time.time() - login_at > lifetime:
        flask_session.clear()
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify({"error": "Session expired"}), 401
        return redirect(url_for("auth.login")), 302

    username = flask_session.get("user", "")
    if username:
        from app.auth import _load_users
        from app.groups import get_allowed_tabs
        users = _load_users()
        entry = users.get(username)
        if entry is None and not flask_session.get("role"):
            flask_session.clear()
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("auth.login")), 302
        if entry is not None:
            flask_session["role"] = entry.get("role", "viewer")
        flask_session["allowed_tabs"] = list(
            get_allowed_tabs(username, ad_groups=flask_session.get("ad_groups", []), role=flask_session.get("role"))
        )
    return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in flask_session:
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("auth.login", next=request.path))
        err = _revalidate_session()
        if err is not None:
            return err
        return f(*args, **kwargs)
    return decorated


def tab_required(*tab_keys: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user" not in flask_session:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Not authenticated"}), 401
                return redirect(url_for("auth.login", next=request.path))
            err = _revalidate_session()
            if err is not None:
                return err
            allowed = set(flask_session.get("allowed_tabs", []))
            if flask_session.get("role") != "admin" and not (allowed & set(tab_keys)):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Access denied"}), 403
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in flask_session:
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("auth.login", next=request.path))
        err = _revalidate_session()
        if err is not None:
            return err
        if flask_session.get("role") != "admin":
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"error": "Admin role required"}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated


def check_domain_access(domain: str) -> tuple | None:
    if flask_session.get("role") == "admin":
        return None
    if domain == "Global":
        return None
    from app.groups import user_can_access_domain
    if not user_can_access_domain(
        flask_session.get("user", ""), domain,
        ad_groups=flask_session.get("ad_groups", []),
    ):
        return jsonify({"error": f"Access to domain '{domain}' is not permitted"}), 403
    return None
