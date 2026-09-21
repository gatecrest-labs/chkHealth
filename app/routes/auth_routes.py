import threading
import time
from collections import defaultdict
from urllib.parse import urlparse

from flask import (
    Blueprint, current_app, flash, redirect, render_template,
    request, session, url_for,
)

from app.auth import authenticate
from app.groups import get_allowed_tabs
from app.app_logger import app_log
from app import registry

_WINDOW_SECONDS = 600
_IP_MAX = 10
_USER_MAX = 5
_USER_FAILURES_MAX_KEYS = 10_000

# In-memory per-process store. With multiple Gunicorn workers each worker
# tracks failures independently, so the effective limit is _IP_MAX × workers
# and _USER_MAX × workers across the fleet.
_lock = threading.Lock()
_ip_failures: dict[str, list[float]] = defaultdict(list)
_user_failures: dict[str, list[float]] = defaultdict(list)


def _norm(username: str) -> str:
    return username.strip().lower()


def _is_rate_limited(ip: str, username: str) -> bool:
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    norm = _norm(username)
    with _lock:
        _ip_failures[ip] = [t for t in _ip_failures[ip] if t > cutoff]
        _user_failures[norm] = [t for t in _user_failures[norm] if t > cutoff]
        return len(_ip_failures[ip]) >= _IP_MAX or len(_user_failures[norm]) >= _USER_MAX


def _record_failure(ip: str, username: str) -> None:
    now = time.monotonic()
    norm = _norm(username)
    with _lock:
        _ip_failures[ip].append(now)
        if len(_user_failures) >= _USER_FAILURES_MAX_KEYS and norm not in _user_failures:
            del _user_failures[next(iter(_user_failures))]
        _user_failures[norm].append(now)


def _clear_failures(ip: str, username: str) -> None:
    norm = _norm(username)
    with _lock:
        _ip_failures.pop(ip, None)
        _user_failures.pop(norm, None)


def _safe_redirect(url: str) -> bool:
    parsed = urlparse(url)
    return (
        not parsed.scheme and not parsed.netloc
        and parsed.path.startswith("/") and url != "/login"
    )


def _first_allowed_url(allowed_tabs: list) -> str:
    for key, meta in registry.get_registry().items():
        if key in allowed_tabs:
            return url_for(meta["endpoint"])
    return url_for("auth.login")


bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(_first_allowed_url(session.get("allowed_tabs", [])))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("login.html"), 400
        ip = request.remote_addr or ""
        if _is_rate_limited(ip, username):
            app_log("WARN", "auth", "Login rate-limited", username=username, remote=ip)
            flash("Too many failed attempts. Please wait before trying again.", "danger")
            return render_template("login.html"), 429
        try:
            auth_result = authenticate(username, password)
        except Exception:
            current_app.logger.exception("Unexpected error during authentication")
            flash("An unexpected error occurred. Please try again.", "error")
            return render_template("login.html"), 500
        if auth_result is not None:
            role, ad_groups = auth_result
            _clear_failures(ip, username)
            session.permanent = True
            session["user"] = username
            session["role"] = role
            session["ad_groups"] = ad_groups
            allowed = list(get_allowed_tabs(username, ad_groups=ad_groups, role=role))
            session["allowed_tabs"] = allowed
            session["login_at"] = int(time.time())
            app_log("INFO", "auth", "Login successful", username=username, role=role)
            next_url = request.args.get("next", "").strip()
            if next_url and _safe_redirect(next_url):
                return redirect(next_url)
            return redirect(_first_allowed_url(allowed))
        _record_failure(ip, username)
        app_log("WARN", "auth", "Failed login attempt", username=username, remote=ip)
        flash("Invalid credentials.", "danger")
        return render_template("login.html"), 401
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    app_log("INFO", "auth", "Logout", username=session.get("user", "unknown"))
    session.clear()
    return redirect(url_for("auth.login"))
