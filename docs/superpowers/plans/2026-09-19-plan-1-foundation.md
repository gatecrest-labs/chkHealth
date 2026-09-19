# check.health Plan 1 — Project Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the check.health project with all core infrastructure modules, local auth, Flask app factory, admin tab, and public-repo documentation stubs — producing a fully working app (login, admin, nav) with no Check Point integration yet.

**Architecture:** Flask blueprint app with UV package management. Core modules (config, auth, registry, decorators, security, groups, app_logger, app_settings, atomic_io) are modeled directly after the 4thealth project. Domain-based access control replaces ADOM-based access control throughout. No RADIUS, no SNMP.

**Tech Stack:** Python ≥ 3.11, Flask ≥ 3.1, UV, bcrypt, python-dotenv, APScheduler (wired but no jobs yet in this plan)

**Spec:** `docs/superpowers/specs/2026-09-19-check-health-design.md`

## Global Constraints

- Python ≥ 3.11 (use `match`, walrus `:=`, union type hints `X | Y`)
- UV is the package/venv manager — never use `pip install` directly
- All secret/credential files (`.env`, `users.json`, `groups.json`, `*.db`, `app_settings.json`) are git-ignored; `.example` counterparts ship instead
- No real hostnames, IPs, or internal network details in any committed file
- CSRF protection on all state-changing POST endpoints
- Security headers set on every response
- This will be a public repo — no internal references anywhere in committed code
- `allowed_domains` / `domain_restrict` replace `allowed_adoms` / `adom_restrict` from 4thealth everywhere
- No RADIUS auth — local bcrypt only for this plan
- Test runner: `pytest` via `uv run pytest`
- Dev server: `uv run flask --app app run --debug`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | Create | UV project definition, all dependencies |
| `.gitignore` | Create | Exclude secrets, db files, caches |
| `.env.example` | Create | Template for environment variables |
| `users.example.json` | Create | Example user store shape |
| `groups.example.json` | Create | Example group store shape |
| `wsgi.py` | Create | Production WSGI entry point |
| `manage_users.py` | Create | CLI to add/delete/list users + generate SECRET_KEY |
| `app/__init__.py` | Create | Flask app factory, blueprint registration, security middleware |
| `app/config.py` | Create | Config class reading `.env` |
| `app/atomic_io.py` | Create | Atomic JSON/text file writes |
| `app/auth.py` | Create | Local bcrypt auth (authenticate, add_user, delete_user, list_users, generate_secret_key) |
| `app/registry.py` | Create | Nav tab registry (register, get_registry, known_tabs) |
| `app/decorators.py` | Create | login_required, tab_required, admin_required, check_domain_access |
| `app/security.py` | Create | CSRF helpers, internal_api_error, upstream_api_error |
| `app/groups.py` | Create | Group CRUD + allowed_tabs/domains resolution |
| `app/app_logger.py` | Create | In-memory ring-buffer logger |
| `app/app_settings.py` | Create | Persistent key/value settings (app_settings.json) |
| `app/routes/__init__.py` | Create | Empty package marker |
| `app/routes/auth_routes.py` | Create | /login, /logout with rate limiting |
| `app/routes/admin_routes.py` | Create | /admin page + all /admin/api/* endpoints |
| `app/templates/base.html` | Create | Nav bar, flash messages, CSRF meta tag |
| `app/templates/login.html` | Create | Login form |
| `app/templates/admin.html` | Create | Admin page (users, groups, logs, settings, tab registry) |
| `app/static/css/app.css` | Create | Base styles (light/dark mode, card, table, form components) |
| `app/static/js/admin.js` | Create | Admin page JS (user CRUD, group CRUD, log viewer, settings) |
| `README.md` | Create | Project overview + setup instructions |
| `CHANGELOG.md` | Create | `[Unreleased]` section |
| `CONTRIBUTING.md` | Create | Contribution guide |
| `SECURITY.md` | Create | Responsible disclosure policy |
| `CODE_OF_CONDUCT.md` | Create | Contributor Covenant |
| `tests/__init__.py` | Create | Empty |
| `tests/test_auth.py` | Create | Auth unit tests |
| `tests/test_groups.py` | Create | Groups unit tests |
| `tests/test_security.py` | Create | CSRF + error helper tests |
| `tests/test_app.py` | Create | App factory smoke tests |

---

### Task 1: Dev branch + pyproject.toml + .gitignore

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`

**Interfaces:**
- Produces: `uv sync` works; `uv run pytest` discovers tests; `uv run flask --app app run` starts server

- [ ] **Step 1: Create dev branch**

```bash
git checkout -b dev
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "check-health"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.1.3,<4",
    "python-dotenv>=1.2.3",
    "requests>=2.34.2",
    "bcrypt>=5.0.0",
    "apscheduler>=3.11.3",
    "openpyxl>=3.1.5",
    "cryptography>=50.0.1",
    "psutil>=7.2.2",
    "pyyaml>=6.0.3",
]

[project.optional-dependencies]
prod = ["gunicorn>=26.2.0"]

[tool.uv]
package = false

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F"]
ignore = ["BLE001", "S110", "S112"]

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "ruff>=0.16.6",
]
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
# Secrets and local config
.env
users.json
groups.json
app_settings.json
api_tokens.json

# Databases
*.db
*.db-shm
*.db-wal

# Python
__pycache__/
*.py[cod]
*.pyo
.Python

# UV / venv
.venv/
dist/
*.egg-info/
.eggs/

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Certificates (if generated locally)
certs/

# Temp / build
*.tmp
*.log
build/
```

- [ ] **Step 4: Run `uv sync`**

```bash
uv sync
```

Expected: `.venv` created, all dependencies installed, no errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore
git commit -m "feat: initialize project scaffold with pyproject.toml and .gitignore"
```

---

### Task 2: Example config files + wsgi.py + manage_users.py stub

**Files:**
- Create: `.env.example`
- Create: `users.example.json`
- Create: `groups.example.json`
- Create: `wsgi.py`

**Interfaces:**
- Produces: `.env.example` documents all required env vars; example JSON files show the expected shape

- [ ] **Step 1: Create `.env.example`**

```ini
# check.health environment configuration
# Copy this file to .env and fill in real values.
# NEVER commit .env to git.

# ── Flask ──────────────────────────────────────────────────────────────────
# Generate with: python manage_users.py secret
SECRET_KEY=change-me-in-production
FLASK_ENV=development

# Session lifetime (seconds). Default: 1 hour sliding, 10 hours absolute.
# PERMANENT_SESSION_LIFETIME=3600
# SESSION_ABSOLUTE_LIFETIME=36000

# ── Check Point MDS (HA pair — two datacenters) ────────────────────────────
CP_MDS_PRIMARY=10.x.x.x
CP_MDS_SECONDARY=10.x.x.x
CP_API_KEY=your-read-only-api-key-here
# Set to false for self-signed certificates (typical in lab/enterprise)
CP_VERIFY_SSL=false
# Timeout in seconds for MDS API calls
CP_TIMEOUT=30

# Display labels for infrastructure health cards (optional)
CP_MDS_PRIMARY_LABEL=MDS Primary (DC1)
CP_MDS_SECONDARY_LABEL=MDS Secondary (DC2)

# ── Log Servers (MLS) ──────────────────────────────────────────────────────
CP_MLS_1=10.x.x.x
CP_MLS_2=10.x.x.x
CP_MLS_1_LABEL=MLS Primary
CP_MLS_2_LABEL=MLS Secondary

# ── Health thresholds ──────────────────────────────────────────────────────
CPU_WARN=70
CPU_CRIT=90
MEM_WARN=75
MEM_CRIT=90
```

- [ ] **Step 2: Create `users.example.json`**

```json
{
  "admin": {
    "password_hash": "$2b$12$examplehashnotrealadminpassword",
    "role": "admin"
  },
  "viewer": {
    "password_hash": "$2b$12$examplehashnotrealviewerpassword",
    "role": "viewer"
  }
}
```

- [ ] **Step 3: Create `groups.example.json`**

```json
{
  "network-ops": {
    "members": ["viewer"],
    "allowed_tabs": ["dashboard", "firewalls", "rule_review"],
    "domain_restrict": false,
    "allowed_domains": []
  },
  "dc1-only": {
    "members": [],
    "allowed_tabs": ["dashboard", "firewalls"],
    "domain_restrict": true,
    "allowed_domains": ["domain-a", "domain-b"]
  }
}
```

- [ ] **Step 4: Create `wsgi.py`**

```python
from app import create_app

application = create_app()
```

- [ ] **Step 5: Commit**

```bash
git add .env.example users.example.json groups.example.json wsgi.py
git commit -m "feat: add example config files and wsgi entry point"
```

---

### Task 3: `app/atomic_io.py` + `app/app_logger.py`

**Files:**
- Create: `app/__init__.py` (empty for now — app factory comes in Task 8)
- Create: `app/atomic_io.py`
- Create: `app/app_logger.py`
- Create: `tests/__init__.py`
- Test: `tests/test_app_logger.py`

**Interfaces:**
- Produces:
  - `atomic_write_text(path, text: str) -> None`
  - `atomic_write_json(path, data, *, indent: int = 2) -> None`
  - `app_log(level: str, component: str, message: str, **extra) -> None`
  - `set_log_level(level: str) -> None`
  - `get_log_level() -> str`
  - `get_log_levels() -> list[str]`
  - `get_log_entries(level: str | None, component: str | None, limit: int) -> list[dict]`
  - `clear_log_entries() -> None`

- [ ] **Step 1: Create `app/__init__.py`** (empty placeholder — replaced in Task 8)

```python
```

- [ ] **Step 2: Create `tests/__init__.py`**

```python
```

- [ ] **Step 3: Write failing test for app_logger**

Create `tests/test_app_logger.py`:

```python
import pytest
from app.app_logger import app_log, get_log_entries, clear_log_entries, set_log_level, get_log_level


def setup_function():
    clear_log_entries()
    set_log_level("INFO")


def test_log_entry_stored():
    app_log("INFO", "test", "hello world")
    entries = get_log_entries(level=None, component=None, limit=10)
    assert len(entries) == 1
    assert entries[0]["message"] == "hello world"
    assert entries[0]["level"] == "INFO"
    assert entries[0]["component"] == "test"


def test_log_filtered_by_level():
    app_log("DEBUG", "test", "debug msg")
    app_log("INFO", "test", "info msg")
    entries = get_log_entries(level="INFO", component=None, limit=10)
    assert all(e["level"] in ("INFO", "WARN", "ERROR") for e in entries)


def test_log_filtered_by_component():
    app_log("INFO", "auth", "login")
    app_log("INFO", "other", "other msg")
    entries = get_log_entries(level=None, component="auth", limit=10)
    assert all(e["component"] == "auth" for e in entries)


def test_clear_entries():
    app_log("INFO", "test", "msg")
    clear_log_entries()
    assert get_log_entries(level=None, component=None, limit=10) == []


def test_set_log_level_filters_below():
    set_log_level("WARN")
    app_log("INFO", "test", "should not appear")
    app_log("WARN", "test", "should appear")
    entries = get_log_entries(level=None, component=None, limit=10)
    assert len(entries) == 1
    assert entries[0]["level"] == "WARN"


def test_extra_fields_stored():
    app_log("INFO", "auth", "login", username="alice", remote="1.2.3.4")
    entries = get_log_entries(level=None, component=None, limit=10)
    assert entries[0]["extra"]["username"] == "alice"
```

- [ ] **Step 4: Run test to verify it fails**

```bash
uv run pytest tests/test_app_logger.py -v
```

Expected: ImportError or AttributeError — `app_logger` not yet implemented.

- [ ] **Step 5: Create `app/atomic_io.py`**

```python
"""Atomic file writes that degrade gracefully on Docker bind mounts."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path


def atomic_write_text(path, text: str) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.replace(tmp, path)
    except OSError as exc:
        if exc.errno != errno.EBUSY:
            raise
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def atomic_write_json(path, data, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent))
```

- [ ] **Step 6: Create `app/app_logger.py`**

```python
"""Application-level logging with an in-memory ring buffer.

Log levels (in ascending severity): TRACE DEBUG INFO WARN ERROR

Usage:
    from app.app_logger import app_log, set_log_level, get_log_entries
    app_log("INFO", "auth", "User logged in", username="admin")
"""

import threading
from collections import deque
from datetime import datetime, timezone

_LEVELS = ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]
_LEVEL_RANK = {lvl: i for i, lvl in enumerate(_LEVELS)}

_MAX_ENTRIES = 2000
_buffer: deque = deque(maxlen=_MAX_ENTRIES)
_lock = threading.Lock()
_current_level = "INFO"


def set_log_level(level: str) -> None:
    global _current_level
    level = level.upper()
    if level not in _LEVEL_RANK:
        raise ValueError(f"Invalid log level '{level}'. Choose from: {', '.join(_LEVELS)}")
    _current_level = level


def get_log_level() -> str:
    return _current_level


def get_log_levels() -> list[str]:
    return list(_LEVELS)


def app_log(level: str, component: str, message: str, **extra) -> None:
    level = level.upper()
    if _LEVEL_RANK.get(level, 0) < _LEVEL_RANK.get(_current_level, 0):
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": level,
        "component": component,
        "message": message,
    }
    if extra:
        entry["extra"] = extra
    with _lock:
        _buffer.append(entry)


def get_log_entries(
    level: str | None = None,
    component: str | None = None,
    limit: int = 500,
) -> list[dict]:
    min_rank = _LEVEL_RANK.get((level or "").upper(), 0)
    with _lock:
        entries = list(_buffer)
    if level:
        entries = [e for e in entries if _LEVEL_RANK.get(e["level"], 0) >= min_rank]
    if component:
        entries = [e for e in entries if e["component"] == component]
    return entries[-limit:]


def clear_log_entries() -> None:
    with _lock:
        _buffer.clear()
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/test_app_logger.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add app/__init__.py app/atomic_io.py app/app_logger.py tests/__init__.py tests/test_app_logger.py
git commit -m "feat: add atomic_io and app_logger modules"
```

---

### Task 4: `app/config.py` + `app/app_settings.py`

**Files:**
- Create: `app/config.py`
- Create: `app/app_settings.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Config` class with attributes: `SECRET_KEY`, `CP_MDS_PRIMARY`, `CP_MDS_SECONDARY`, `CP_API_KEY`, `CP_VERIFY_SSL`, `CP_TIMEOUT`, `CP_MDS_PRIMARY_LABEL`, `CP_MDS_SECONDARY_LABEL`, `CP_MLS_1`, `CP_MLS_2`, `CP_MLS_1_LABEL`, `CP_MLS_2_LABEL`, `CPU_WARN`, `CPU_CRIT`, `MEM_WARN`, `MEM_CRIT`, `SESSION_ABSOLUTE_LIFETIME`, `MAX_CONTENT_LENGTH`
  - `get_setting(key: str, default=None) -> Any`
  - `set_setting(key: str, value) -> None`
  - `get_all() -> dict`

- [ ] **Step 1: Write failing test**

Create `tests/test_config.py`:

```python
import os
import pytest


def test_config_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
    monkeypatch.setenv("CP_MDS_PRIMARY", "10.1.1.1")
    monkeypatch.setenv("CP_MDS_SECONDARY", "10.1.1.2")
    monkeypatch.setenv("CP_API_KEY", "test-key")
    monkeypatch.setenv("CP_VERIFY_SSL", "false")
    # Re-import to pick up monkeypatched env
    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.Config.CP_MDS_PRIMARY == "10.1.1.1"
    assert cfg_mod.Config.CP_VERIFY_SSL is False


def test_app_settings_get_set(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
    import app.app_settings as s_mod
    import importlib
    # Point settings file at a temp path
    monkeypatch.setattr(s_mod, "_SETTINGS_PATH", tmp_path / "app_settings.json")
    importlib.reload(s_mod)
    monkeypatch.setattr(s_mod, "_SETTINGS_PATH", tmp_path / "app_settings.json")
    s_mod.set_setting("test_key", "hello")
    assert s_mod.get_setting("test_key") == "hello"


def test_app_settings_default(tmp_path, monkeypatch):
    import app.app_settings as s_mod
    monkeypatch.setattr(s_mod, "_SETTINGS_PATH", tmp_path / "missing.json")
    result = s_mod.get_setting("nonexistent_key", default="fallback")
    assert result == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: ImportError — modules not yet created.

- [ ] **Step 3: Create `app/config.py`**

```python
"""Application configuration loaded from environment / .env file."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = Path(__file__).parent.parent


def _require_secret_key() -> str:
    val = os.environ.get("SECRET_KEY", "")
    if not val or val == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is not set or is the insecure default. "
            "Generate one with: python manage_users.py secret"
        )
    return val


class Config:
    SECRET_KEY = _require_secret_key()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("PERMANENT_SESSION_LIFETIME", "3600"))
    SESSION_ABSOLUTE_LIFETIME = int(os.environ.get("SESSION_ABSOLUTE_LIFETIME", str(10 * 3600)))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(4 * 1024 * 1024)))

    # Check Point MDS (HA pair)
    CP_MDS_PRIMARY = os.environ.get("CP_MDS_PRIMARY", "")
    CP_MDS_SECONDARY = os.environ.get("CP_MDS_SECONDARY", "")
    CP_API_KEY = os.environ.get("CP_API_KEY", "")
    CP_VERIFY_SSL = os.environ.get("CP_VERIFY_SSL", "false").lower() == "true"
    CP_TIMEOUT = int(os.environ.get("CP_TIMEOUT", "30"))

    # Display labels for infrastructure health cards
    CP_MDS_PRIMARY_LABEL = os.environ.get("CP_MDS_PRIMARY_LABEL", "MDS Primary")
    CP_MDS_SECONDARY_LABEL = os.environ.get("CP_MDS_SECONDARY_LABEL", "MDS Secondary")

    # Log servers (MLS)
    CP_MLS_1 = os.environ.get("CP_MLS_1", "")
    CP_MLS_2 = os.environ.get("CP_MLS_2", "")
    CP_MLS_1_LABEL = os.environ.get("CP_MLS_1_LABEL", "MLS Primary")
    CP_MLS_2_LABEL = os.environ.get("CP_MLS_2_LABEL", "MLS Secondary")

    # Health thresholds (yellow / red)
    CPU_WARN = int(os.environ.get("CPU_WARN", "70"))
    CPU_CRIT = int(os.environ.get("CPU_CRIT", "90"))
    MEM_WARN = int(os.environ.get("MEM_WARN", "75"))
    MEM_CRIT = int(os.environ.get("MEM_CRIT", "90"))
```

- [ ] **Step 4: Create `app/app_settings.py`**

```python
"""Application settings — persistent key/value store backed by app_settings.json."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from app.atomic_io import atomic_write_json

_SETTINGS_PATH = Path(__file__).parent.parent / "app_settings.json"
_DEFAULTS: dict = {}
_lock = threading.Lock()


def _load() -> dict:
    if not _SETTINGS_PATH.exists():
        return dict(_DEFAULTS)
    try:
        with open(_SETTINGS_PATH) as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def _save(data: dict) -> None:
    atomic_write_json(_SETTINGS_PATH, data)


def get_setting(key: str, default=None):
    with _lock:
        data = _load()
    return data.get(key, default)


def set_setting(key: str, value) -> None:
    with _lock:
        data = _load()
        data[key] = value
        _save(data)


def get_all() -> dict:
    with _lock:
        return _load()
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/app_settings.py tests/test_config.py
git commit -m "feat: add config and app_settings modules"
```

---

### Task 5: `app/auth.py`

**Files:**
- Create: `app/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces:
  - `authenticate(username: str, password: str) -> tuple[str, list] | None` — returns `(role, ad_groups)` on success, `None` on failure; `ad_groups` is always `[]` for local auth
  - `add_user(username: str, password: str, role: str) -> None`
  - `delete_user(username: str) -> bool`
  - `list_users() -> list[dict]` — each dict has `username` and `role`
  - `generate_secret_key() -> str`
  - `_load_users() -> dict` (used internally by decorators.py)

- [ ] **Step 1: Write failing tests**

Create `tests/test_auth.py`:

```python
import pytest
from pathlib import Path


@pytest.fixture
def users_file(tmp_path, monkeypatch):
    import app.auth as auth_mod
    path = tmp_path / "users.json"
    monkeypatch.setattr(auth_mod, "USERS_FILE", path)
    return path


def test_add_and_authenticate(users_file):
    from app.auth import add_user, authenticate
    add_user("alice", "s3cr3t!", "viewer")
    result = authenticate("alice", "s3cr3t!")
    assert result is not None
    role, ad_groups = result
    assert role == "viewer"
    assert ad_groups == []


def test_wrong_password_returns_none(users_file):
    from app.auth import add_user, authenticate
    add_user("bob", "correct", "viewer")
    assert authenticate("bob", "wrong") is None


def test_unknown_user_returns_none(users_file):
    from app.auth import authenticate
    assert authenticate("nobody", "password") is None


def test_delete_user(users_file):
    from app.auth import add_user, delete_user, authenticate
    add_user("carol", "pass", "admin")
    assert delete_user("carol") is True
    assert authenticate("carol", "pass") is None


def test_delete_nonexistent_user(users_file):
    from app.auth import delete_user
    assert delete_user("ghost") is False


def test_list_users(users_file):
    from app.auth import add_user, list_users
    add_user("dave", "pass", "viewer")
    add_user("eve", "pass", "admin")
    users = list_users()
    names = [u["username"] for u in users]
    assert "dave" in names
    assert "eve" in names
    assert all("password_hash" not in u for u in users)


def test_generate_secret_key():
    from app.auth import generate_secret_key
    key = generate_secret_key()
    assert len(key) >= 32


def test_add_duplicate_raises(users_file):
    from app.auth import add_user
    add_user("frank", "pass", "viewer")
    with pytest.raises(ValueError, match="already exists"):
        add_user("frank", "other", "viewer")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: ImportError — `app.auth` not yet implemented.

- [ ] **Step 3: Create `app/auth.py`**

```python
"""Local user authentication — bcrypt hashed passwords stored in users.json."""

import json
import secrets
import string
from pathlib import Path

import bcrypt

from app.atomic_io import atomic_write_json

USERS_FILE = Path(__file__).parent.parent / "users.json"


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    with USERS_FILE.open() as f:
        return json.load(f)


def _save_users(users: dict) -> None:
    atomic_write_json(USERS_FILE, users)


def authenticate(username: str, password: str) -> tuple[str, list] | None:
    """Return (role, ad_groups) on success, None on failure.

    ad_groups is always [] for local auth — present for interface compatibility
    with future auth backends.
    """
    users = _load_users()
    entry = users.get(username)
    if not entry:
        return None
    stored_hash = entry.get("password_hash", "")
    if not stored_hash:
        return None
    try:
        if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
            return None
    except Exception:
        return None
    return entry.get("role", "viewer"), []


def add_user(username: str, password: str, role: str = "viewer") -> None:
    """Add a new user. Raises ValueError if the username already exists."""
    users = _load_users()
    if username in users:
        raise ValueError(f"User '{username}' already exists.")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[username] = {"password_hash": hashed, "role": role}
    _save_users(users)


def update_password(username: str, password: str) -> None:
    """Update an existing user's password. Raises ValueError if not found."""
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found.")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[username]["password_hash"] = hashed
    _save_users(users)


def delete_user(username: str) -> bool:
    """Delete a user. Returns True if deleted, False if not found."""
    users = _load_users()
    if username not in users:
        return False
    del users[username]
    _save_users(users)
    return True


def list_users() -> list[dict]:
    """Return [{username, role}] — no password hashes."""
    users = _load_users()
    return [{"username": k, "role": v.get("role", "viewer")} for k, v in users.items()]


def generate_secret_key() -> str:
    """Generate a cryptographically secure SECRET_KEY."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(48))
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/auth.py tests/test_auth.py
git commit -m "feat: add local bcrypt auth module"
```

---

### Task 6: `app/registry.py` + `app/groups.py`

**Files:**
- Create: `app/registry.py`
- Create: `app/groups.py`
- Test: `tests/test_groups.py`

**Interfaces:**
- Produces:
  - `registry.register(key: str, name: str, endpoint: str, icon: str = "") -> None`
  - `registry.get_registry() -> dict[str, dict]`
  - `registry.known_tabs() -> dict[str, str]`
  - `groups.list_groups() -> list[dict]`
  - `groups.get_group(name: str) -> dict | None`
  - `groups.create_group(name: str, data: dict) -> None`
  - `groups.update_group(name: str, data: dict) -> None`
  - `groups.delete_group(name: str) -> bool`
  - `groups.get_allowed_tabs(username: str, ad_groups: list, role: str) -> set[str]`
  - `groups.get_allowed_domains(username: str, ad_groups: list) -> list[str] | None` — `None` = unrestricted
  - `groups.user_can_access_domain(username: str, domain: str, ad_groups: list) -> bool`
  - `groups.KNOWN_TABS: dict[str, str]` — populated by app factory from registry

- [ ] **Step 1: Write failing tests**

Create `tests/test_groups.py`:

```python
import pytest
import json


@pytest.fixture
def groups_file(tmp_path, monkeypatch):
    import app.groups as g_mod
    path = tmp_path / "groups.json"
    monkeypatch.setattr(g_mod, "GROUPS_FILE", path)
    return path


def test_create_and_list(groups_file):
    from app.groups import create_group, list_groups
    create_group("ops", {
        "members": ["alice"],
        "allowed_tabs": ["dashboard"],
        "domain_restrict": False,
        "allowed_domains": [],
    })
    groups = list_groups()
    assert len(groups) == 1
    assert groups[0]["name"] == "ops"


def test_get_group(groups_file):
    from app.groups import create_group, get_group
    create_group("team", {"members": ["bob"], "allowed_tabs": [], "domain_restrict": False, "allowed_domains": []})
    g = get_group("team")
    assert g is not None
    assert "bob" in g["members"]


def test_update_group(groups_file):
    from app.groups import create_group, update_group, get_group
    create_group("grp", {"members": [], "allowed_tabs": ["dashboard"], "domain_restrict": False, "allowed_domains": []})
    update_group("grp", {"members": ["carol"], "allowed_tabs": ["firewalls"], "domain_restrict": False, "allowed_domains": []})
    g = get_group("grp")
    assert "carol" in g["members"]
    assert "firewalls" in g["allowed_tabs"]


def test_delete_group(groups_file):
    from app.groups import create_group, delete_group, get_group
    create_group("temp", {"members": [], "allowed_tabs": [], "domain_restrict": False, "allowed_domains": []})
    assert delete_group("temp") is True
    assert get_group("temp") is None


def test_delete_nonexistent(groups_file):
    from app.groups import delete_group
    assert delete_group("ghost") is False


def test_get_allowed_tabs_via_membership(groups_file):
    from app.groups import create_group, get_allowed_tabs, KNOWN_TABS
    KNOWN_TABS.update({"dashboard": "Dashboard", "firewalls": "Firewalls"})
    create_group("net", {"members": ["dave"], "allowed_tabs": ["dashboard"], "domain_restrict": False, "allowed_domains": []})
    tabs = get_allowed_tabs("dave", ad_groups=[], role="viewer")
    assert "dashboard" in tabs


def test_admin_gets_all_tabs(groups_file):
    from app.groups import get_allowed_tabs, KNOWN_TABS
    KNOWN_TABS.update({"dashboard": "Dashboard", "firewalls": "Firewalls"})
    tabs = get_allowed_tabs("admin", ad_groups=[], role="admin")
    assert "dashboard" in tabs
    assert "firewalls" in tabs


def test_domain_unrestricted(groups_file):
    from app.groups import create_group, get_allowed_domains
    create_group("open", {"members": ["eve"], "allowed_tabs": [], "domain_restrict": False, "allowed_domains": []})
    result = get_allowed_domains("eve", ad_groups=[])
    assert result is None  # None = unrestricted


def test_domain_restricted(groups_file):
    from app.groups import create_group, get_allowed_domains
    create_group("restricted", {
        "members": ["frank"],
        "allowed_tabs": [],
        "domain_restrict": True,
        "allowed_domains": ["domain-a"],
    })
    result = get_allowed_domains("frank", ad_groups=[])
    assert result == ["domain-a"]


def test_user_can_access_domain(groups_file):
    from app.groups import create_group, user_can_access_domain
    create_group("dc1", {
        "members": ["grace"],
        "allowed_tabs": [],
        "domain_restrict": True,
        "allowed_domains": ["domain-a"],
    })
    assert user_can_access_domain("grace", "domain-a", ad_groups=[]) is True
    assert user_can_access_domain("grace", "domain-b", ad_groups=[]) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_groups.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create `app/registry.py`**

```python
"""Navigation tab registry — single source of truth for nav metadata.

Each blueprint self-registers at import time:

    from app import registry
    registry.register("my_tab", "My Tab", "myblueprint.myview")
"""

from __future__ import annotations

_registry: dict[str, dict] = {}


def register(key: str, name: str, endpoint: str, icon: str = "") -> None:
    _registry[key] = {"name": name, "endpoint": endpoint, "icon": icon}


def get_registry() -> dict[str, dict]:
    return dict(_registry)


def known_tabs() -> dict[str, str]:
    return {k: v["name"] for k, v in _registry.items()}
```

- [ ] **Step 4: Create `app/groups.py`**

```python
"""Group management — local store backed by groups.json.

A group has:
  name             str   unique identifier
  members          list  of local username strings
  allowed_tabs     list  of tab keys (see KNOWN_TABS)
  domain_restrict  bool  when True, only domains in allowed_domains are accessible
  allowed_domains  list  of domain name strings (only used when domain_restrict=True)

Domain access rules:
  - Admin users always have unrestricted access to all domains.
  - For non-admin users the effective allowed domain set is the UNION of
    allowed_domains across all groups where domain_restrict=True that they
    belong to, PLUS all domains if they belong to any group where
    domain_restrict=False.
  - A single unrestricted group grants full domain access.
  - If a user belongs to no group, they have no domain access.
"""

import json
import threading
from pathlib import Path

GROUPS_FILE = Path(__file__).parent.parent / "groups.json"
_lock = threading.Lock()

KNOWN_TABS: dict[str, str] = {}


def _load() -> dict:
    if not GROUPS_FILE.exists():
        return {}
    with GROUPS_FILE.open() as f:
        return json.load(f)


def _save(data: dict) -> None:
    from app.atomic_io import atomic_write_json
    atomic_write_json(GROUPS_FILE, data)


def _group_to_dict(name: str, g: dict) -> dict:
    return {
        "name": name,
        "members": g.get("members", []),
        "allowed_tabs": g.get("allowed_tabs", []),
        "domain_restrict": bool(g.get("domain_restrict", False)),
        "allowed_domains": g.get("allowed_domains", []),
    }


def list_groups() -> list[dict]:
    with _lock:
        groups = _load()
    return [_group_to_dict(name, g) for name, g in groups.items()]


def get_group(name: str) -> dict | None:
    with _lock:
        groups = _load()
    g = groups.get(name)
    return _group_to_dict(name, g) if g is not None else None


def create_group(name: str, data: dict) -> None:
    with _lock:
        groups = _load()
        groups[name] = {
            "members": data.get("members", []),
            "allowed_tabs": data.get("allowed_tabs", []),
            "domain_restrict": bool(data.get("domain_restrict", False)),
            "allowed_domains": data.get("allowed_domains", []),
        }
        _save(groups)


def update_group(name: str, data: dict) -> None:
    with _lock:
        groups = _load()
        existing = groups.get(name, {})
        existing.update({
            "members": data.get("members", existing.get("members", [])),
            "allowed_tabs": data.get("allowed_tabs", existing.get("allowed_tabs", [])),
            "domain_restrict": bool(data.get("domain_restrict", existing.get("domain_restrict", False))),
            "allowed_domains": data.get("allowed_domains", existing.get("allowed_domains", [])),
        })
        groups[name] = existing
        _save(groups)


def delete_group(name: str) -> bool:
    with _lock:
        groups = _load()
        if name not in groups:
            return False
        del groups[name]
        _save(groups)
    return True


def _user_groups(username: str, ad_groups: list) -> list[dict]:
    """Return all groups the user belongs to (by username match)."""
    all_groups = _load()
    result = []
    for name, g in all_groups.items():
        if username in g.get("members", []):
            result.append(_group_to_dict(name, g))
    return result


def get_allowed_tabs(username: str, ad_groups: list = [], role: str = "viewer") -> set[str]:
    if role == "admin":
        return set(KNOWN_TABS.keys())
    with _lock:
        user_grps = _user_groups(username, ad_groups)
    tabs: set[str] = set()
    for g in user_grps:
        tabs.update(g["allowed_tabs"])
    return tabs


def get_allowed_domains(username: str, ad_groups: list = []) -> list[str] | None:
    """Return the list of allowed domain names, or None for unrestricted."""
    with _lock:
        user_grps = _user_groups(username, ad_groups)
    if not user_grps:
        return []
    if any(not g["domain_restrict"] for g in user_grps):
        return None  # at least one unrestricted group → full access
    domains: set[str] = set()
    for g in user_grps:
        domains.update(g["allowed_domains"])
    return sorted(domains)


def user_can_access_domain(username: str, domain: str, ad_groups: list = []) -> bool:
    allowed = get_allowed_domains(username, ad_groups)
    if allowed is None:
        return True
    return domain in allowed
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_groups.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/registry.py app/groups.py tests/test_groups.py
git commit -m "feat: add registry and groups modules with domain access control"
```

---

### Task 7: `app/security.py` + `app/decorators.py`

**Files:**
- Create: `app/security.py`
- Create: `app/decorators.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Produces:
  - `ensure_csrf_token() -> str`
  - `validate_csrf_request() -> bool`
  - `csrf_error_response() -> tuple`
  - `internal_api_error(component: str, exc: Exception, status: int = 500) -> tuple`
  - `upstream_api_error(component: str, exc: Exception) -> tuple`
  - `login_required` decorator
  - `tab_required(*tab_keys: str)` decorator factory
  - `admin_required` decorator
  - `check_domain_access(domain: str) -> tuple | None`

- [ ] **Step 1: Write failing tests**

Create `tests/test_security.py`:

```python
import pytest


def test_internal_api_error_returns_500(app_ctx):
    from app.security import internal_api_error
    response, status = internal_api_error("test", ValueError("boom"))
    assert status == 500
    data = response.get_json()
    assert "error" in data
    assert "error_id" in data


def test_upstream_api_error_returns_502(app_ctx):
    from app.security import upstream_api_error
    response, status = upstream_api_error("test", ConnectionError("timeout"))
    assert status == 502


def test_csrf_token_generated(app_ctx):
    from app.security import ensure_csrf_token
    from flask import session
    with app_ctx.test_request_context("/"):
        from flask import Flask
        token = ensure_csrf_token()
        assert len(token) > 10


# conftest.py provides app_ctx fixture — see Task 8
```

- [ ] **Step 2: Create `tests/conftest.py`** (needed for app context — full version written in Task 8; create minimal stub now)

```python
import pytest
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-ok!")


@pytest.fixture
def app_ctx():
    """Minimal Flask app for tests that need an app context."""
    from flask import Flask
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok!"
    app.config["TESTING"] = True
    with app.app_context():
        yield app
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_security.py -v
```

Expected: ImportError — `app.security` not yet created.

- [ ] **Step 4: Create `app/security.py`**

```python
"""Security helpers for CSRF, correlation IDs, and safe API error responses."""

from __future__ import annotations

import hmac
import secrets
import uuid

from flask import jsonify, request, session

from app.app_logger import app_log


def ensure_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_request() -> bool:
    expected = session.get("_csrf_token", "")
    if not expected:
        return False
    provided = (
        request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    )
    return hmac.compare_digest(expected, provided)


def csrf_error_response():
    if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
        return jsonify({"error": "CSRF validation failed"}), 400
    return "CSRF validation failed", 400


def _error_id() -> str:
    return uuid.uuid4().hex[:12]


def internal_api_error(component: str, exc: Exception, status: int = 500):
    eid = _error_id()
    app_log(
        "ERROR", component, "Internal API error",
        error_id=eid, exc_type=type(exc).__name__, exc=str(exc),
        path=request.path, method=request.method,
    )
    return jsonify({"error": "Internal server error", "error_id": eid}), status


def upstream_api_error(component: str, exc: Exception):
    eid = _error_id()
    app_log(
        "WARN", component, "Upstream request failed",
        error_id=eid, exc_type=type(exc).__name__, exc=str(exc),
        path=request.path, method=request.method,
    )
    return jsonify({"error": "Upstream request failed", "error_id": eid}), 502
```

- [ ] **Step 5: Create `app/decorators.py`**

```python
"""Shared route decorators.

Usage::

    from app.decorators import login_required, tab_required, admin_required

    @bp.route("/my-page")
    @tab_required("my_tab")
    def my_page():
        ...
"""

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
    """Return a 403 JSON tuple if the current user cannot access ``domain``.

    Returns None when access is permitted. Always permits admin users.
    """
    if flask_session.get("role") == "admin":
        return None
    from app.groups import user_can_access_domain
    if not user_can_access_domain(
        flask_session.get("user", ""), domain,
        ad_groups=flask_session.get("ad_groups", []),
    ):
        return jsonify({"error": f"Access to domain '{domain}' is not permitted"}), 403
    return None
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_security.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/security.py app/decorators.py tests/test_security.py tests/conftest.py
git commit -m "feat: add security helpers and route decorators"
```

---

### Task 8: Flask app factory + `manage_users.py`

**Files:**
- Modify: `app/__init__.py` (replace empty stub with full factory)
- Create: `app/routes/__init__.py`
- Create: `app/routes/auth_routes.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Create: `app/static/css/app.css`
- Create: `manage_users.py`
- Modify: `tests/conftest.py` (replace stub with full fixture)
- Test: `tests/test_app.py`

**Interfaces:**
- Produces:
  - `create_app(test_config: dict | None = None) -> Flask`
  - `GET /login`, `POST /login`, `POST /logout` routes
  - Working `uv run flask --app app run --debug` startup

- [ ] **Step 1: Write failing smoke test**

Create `tests/test_app.py`:

```python
import pytest


def test_app_creates(app_ctx):
    assert app_ctx is not None


def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"login" in response.data.lower()


def test_root_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code in (302, 301)
    assert "/login" in response.headers.get("Location", "")


def test_login_bad_credentials(client):
    response = client.post("/login", data={"username": "nobody", "password": "wrong"})
    assert response.status_code == 401


def test_logout_clears_session(client, authed_client):
    response = authed_client.post("/logout")
    assert response.status_code in (302, 301)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_app.py -v
```

Expected: ImportError or missing fixtures.

- [ ] **Step 3: Create `app/routes/__init__.py`**

```python
```

- [ ] **Step 4: Create `app/routes/auth_routes.py`**

```python
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
```

- [ ] **Step 5: Replace `app/__init__.py` with the app factory**

```python
from flask import Flask, jsonify, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from app.config import Config
from app.security import csrf_error_response, ensure_csrf_token, validate_csrf_request

_BLUEPRINT_MODULES = [
    "app.routes.auth_routes",
    "app.routes.admin_routes",
    # dashboard_routes, firewall_routes, rule_review_routes added in Plans 2 and 3
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
            if not validate_csrf_request():
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
```

- [ ] **Step 6: Update `tests/conftest.py`**

```python
import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-ok!")


@pytest.fixture
def app_ctx():
    from app import create_app
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret-key-minimum-32-chars-ok!", "WTF_CSRF_ENABLED": False})
    with app.app_context():
        yield app


@pytest.fixture
def client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    auth_mod.add_user("testuser", "testpass", "viewer")
    return app_ctx.test_client()


@pytest.fixture
def authed_client(client):
    with client.session_transaction() as sess:
        sess["user"] = "testuser"
        sess["role"] = "viewer"
        sess["allowed_tabs"] = []
        sess["ad_groups"] = []
        import time
        sess["login_at"] = int(time.time())
    return client
```

- [ ] **Step 7: Create minimal `app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <title>{% block title %}check.health{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
</head>
<body>
  {% if session.user %}
  <nav class="navbar">
    <div class="navbar-brand">check.health</div>
    <div class="navbar-tabs">
      {% for key, tab in nav_registry.items() %}
        {% if session.role == 'admin' or key in session.get('allowed_tabs', []) %}
        <a href="{{ url_for(tab.endpoint) }}"
           class="nav-tab {% if request.endpoint and request.endpoint.startswith(key) %}active{% endif %}">
          {{ tab.icon }} {{ tab.name }}
        </a>
        {% endif %}
      {% endfor %}
      {% if session.role == 'admin' %}
      <a href="{{ url_for('admin.admin_page') }}" class="nav-tab nav-tab-admin
         {% if request.endpoint and request.endpoint.startswith('admin') %}active{% endif %}">
        &#9881; Admin
      </a>
      {% endif %}
    </div>
    <div class="navbar-right">
      <span class="nav-user">{{ session.user }}</span>
      <form method="post" action="{{ url_for('auth.logout') }}" style="display:inline">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        <button type="submit" class="btn btn-sm btn-secondary">Logout</button>
      </form>
    </div>
  </nav>
  {% endif %}

  <main class="main-content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for category, message in messages %}
      <div class="alert alert-{{ category }}">{{ message }}</div>
      {% endfor %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>

  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 8: Create `app/templates/login.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Login — check.health</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
</head>
<body class="login-body">
  <div class="login-container">
    <div class="login-card">
      <h1 class="login-title">check.health</h1>
      <p class="login-subtitle">Check Point Provider-1 Dashboard</p>

      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, message in messages %}
        <div class="alert alert-{{ category }}">{{ message }}</div>
        {% endfor %}
      {% endwith %}

      <form method="post" action="{{ url_for('auth.login') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        <div class="form-group">
          <label for="username" class="form-label">Username</label>
          <input type="text" id="username" name="username" class="form-control"
                 autocomplete="username" required autofocus>
        </div>
        <div class="form-group">
          <label for="password" class="form-label">Password</label>
          <input type="password" id="password" name="password" class="form-control"
                 autocomplete="current-password" required>
        </div>
        <button type="submit" class="btn btn-primary btn-block">Sign In</button>
      </form>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 9: Create `app/static/css/app.css`** (essential base styles)

```css
/* ── CSS Variables (light theme) ────────────────────────────────────────── */
:root {
  --bg: #f5f6fa;
  --surface: #ffffff;
  --border: #e2e6ea;
  --text: #1a1d23;
  --text-muted: #6c757d;
  --primary: #0d6efd;
  --primary-hover: #0a58ca;
  --danger: #dc3545;
  --success: #198754;
  --warning: #ffc107;
  --nav-bg: #1a1d23;
  --nav-text: #e2e6ea;
  --nav-active: #ffffff;
}

/* ── Reset ──────────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); font-size: 14px; }

/* ── Navbar ─────────────────────────────────────────────────────────────── */
.navbar { background: var(--nav-bg); color: var(--nav-text); display: flex; align-items: center; padding: 0 1rem; height: 48px; gap: 1rem; }
.navbar-brand { font-weight: 700; font-size: 1.1rem; color: var(--nav-active); white-space: nowrap; }
.navbar-tabs { display: flex; gap: .25rem; flex: 1; }
.nav-tab { color: var(--nav-text); text-decoration: none; padding: .35rem .75rem; border-radius: 4px; font-size: .875rem; }
.nav-tab:hover, .nav-tab.active { background: rgba(255,255,255,.12); color: var(--nav-active); }
.navbar-right { display: flex; align-items: center; gap: .75rem; margin-left: auto; }
.nav-user { font-size: .82rem; color: var(--nav-text); }

/* ── Main content ───────────────────────────────────────────────────────── */
.main-content { padding: 1.5rem 2rem; max-width: 1400px; margin: 0 auto; }

/* ── Buttons ────────────────────────────────────────────────────────────── */
.btn { display: inline-flex; align-items: center; gap: .35rem; padding: .375rem .75rem; border: 1px solid transparent; border-radius: 4px; font-size: .875rem; cursor: pointer; text-decoration: none; background: none; }
.btn-primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.btn-primary:hover { background: var(--primary-hover); }
.btn-secondary { background: var(--surface); color: var(--text); border-color: var(--border); }
.btn-secondary:hover { background: var(--bg); }
.btn-sm { padding: .2rem .5rem; font-size: .8rem; }
.btn-block { width: 100%; justify-content: center; }

/* ── Forms ──────────────────────────────────────────────────────────────── */
.form-group { margin-bottom: 1rem; }
.form-label { display: block; margin-bottom: .35rem; font-weight: 500; font-size: .875rem; }
.form-control, .form-select { width: 100%; padding: .4rem .65rem; border: 1px solid var(--border); border-radius: 4px; font-size: .875rem; background: var(--surface); color: var(--text); }
.form-control:focus, .form-select:focus { outline: 2px solid var(--primary); outline-offset: 1px; }

/* ── Cards ──────────────────────────────────────────────────────────────── */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1rem 1.25rem; }

/* ── Tables ─────────────────────────────────────────────────────────────── */
.table-wrapper { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: .875rem; }
.data-table th, .data-table td { padding: .5rem .75rem; text-align: left; border-bottom: 1px solid var(--border); }
.data-table th { font-weight: 600; background: var(--bg); font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); }
.data-table tbody tr:hover { background: #f8f9fa; }

/* ── Alerts ─────────────────────────────────────────────────────────────── */
.alert { padding: .65rem 1rem; border-radius: 4px; margin-bottom: 1rem; font-size: .875rem; }
.alert-danger { background: #f8d7da; color: #842029; border: 1px solid #f5c2c7; }
.alert-success { background: #d1e7dd; color: #0a3622; border: 1px solid #a3cfbb; }
.alert-secondary { background: #e2e3e5; color: #41464b; border: 1px solid #d3d6d8; }

/* ── Login page ─────────────────────────────────────────────────────────── */
.login-body { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
.login-container { width: 100%; max-width: 400px; padding: 1rem; }
.login-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 2rem; }
.login-title { margin: 0 0 .25rem; font-size: 1.5rem; text-align: center; }
.login-subtitle { margin: 0 0 1.5rem; color: var(--text-muted); font-size: .875rem; text-align: center; }

/* ── Page headers ───────────────────────────────────────────────────────── */
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; }
.page-header h2 { margin: 0; font-size: 1.3rem; }

/* ── Utility ────────────────────────────────────────────────────────────── */
.text-muted { color: var(--text-muted); }
.d-flex { display: flex; }
.gap-2 { gap: .5rem; }
.mb-3 { margin-bottom: 1rem; }

/* ── Status badges ──────────────────────────────────────────────────────── */
.badge { display: inline-block; padding: .15rem .5rem; border-radius: 3px; font-size: .75rem; font-weight: 600; }
.badge-success { background: #d1e7dd; color: #0a3622; }
.badge-danger { background: #f8d7da; color: #842029; }
.badge-warning { background: #fff3cd; color: #664d03; }
.badge-secondary { background: #e2e3e5; color: #41464b; }

/* ── Modal ──────────────────────────────────────────────────────────────── */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--surface); border-radius: 8px; width: 100%; max-width: 680px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,.18); }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: .85rem 1.25rem; border-bottom: 1px solid var(--border); }
.modal-title { font-weight: 600; font-size: 1rem; }
.modal-close { background: none; border: none; cursor: pointer; font-size: 1.1rem; color: var(--text-muted); }
.modal-body { padding: 1.25rem; overflow-y: auto; }

/* ── Infra health cards ─────────────────────────────────────────────────── */
.health-card { background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--border); border-radius: 6px; padding: .85rem 1.25rem; margin-bottom: .75rem; display: flex; align-items: center; gap: 1.5rem; }
.health-card.healthy { border-left-color: var(--success); }
.health-card.unhealthy { border-left-color: var(--danger); }
.health-card.degraded { border-left-color: var(--warning); }
.health-card-name { min-width: 200px; }
.health-card-name strong { display: block; font-size: .95rem; }
.health-card-name .health-ip { font-size: .78rem; color: var(--text-muted); }
.health-card-meta { display: flex; gap: 2rem; flex: 1; font-size: .82rem; }
.health-meta-item label { display: block; color: var(--text-muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }

/* ── Summary tiles ──────────────────────────────────────────────────────── */
.summary-tile-row { display: flex; gap: 1rem; margin-bottom: 1.25rem; }
.summary-tile { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1rem 1.5rem; flex: 1; }
.summary-tile .tile-value { font-size: 2.2rem; font-weight: 700; line-height: 1; margin-bottom: .25rem; }
.summary-tile .tile-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--text-muted); font-weight: 600; }
```

- [ ] **Step 10: Create `manage_users.py`**

```python
#!/usr/bin/env python3
"""CLI tool to manage local user accounts stored in users.json."""

import argparse
import os
import sys

os.environ.setdefault("SECRET_KEY", "manage-users-cli-no-server-needed")


def cmd_add(args):
    from app.auth import add_user, update_password
    import getpass

    password = args.password or getpass.getpass(f"Password for {args.username}: ")
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)
    try:
        add_user(args.username, password, args.role)
        print(f"User '{args.username}' added with role '{args.role}'.")
    except ValueError:
        # User exists — update password
        update_password(args.username, password)
        print(f"User '{args.username}' password updated.")


def cmd_delete(args):
    from app.auth import delete_user
    if delete_user(args.username):
        print(f"User '{args.username}' deleted.")
    else:
        print(f"User '{args.username}' not found.", file=sys.stderr)
        sys.exit(1)


def cmd_list(_):
    from app.auth import list_users
    users = list_users()
    if not users:
        print("No users configured.")
        return
    print(f"{'Username':<20} {'Role':<10}")
    print("-" * 30)
    for u in users:
        print(f"{u['username']:<20} {u['role']:<10}")


def cmd_secret(_):
    from app.auth import generate_secret_key
    key = generate_secret_key()
    print(f"Generated SECRET_KEY:\n{key}")
    print("\nAdd this to your .env file:\nSECRET_KEY=" + key)


parser = argparse.ArgumentParser(description="check.health user management")
sub = parser.add_subparsers(dest="command", required=True)

p_add = sub.add_parser("add", help="Add or update a user")
p_add.add_argument("username")
p_add.add_argument("--password", default=None, help="Password (prompted if omitted)")
p_add.add_argument("--role", default="viewer", choices=["admin", "viewer"])

p_del = sub.add_parser("delete", help="Delete a user")
p_del.add_argument("username")

sub.add_parser("list", help="List all users")
sub.add_parser("secret", help="Generate a SECRET_KEY value")

args = parser.parse_args()
{"add": cmd_add, "delete": cmd_delete, "list": cmd_list, "secret": cmd_secret}[args.command](args)
```

- [ ] **Step 11: Run tests**

```bash
uv run pytest tests/test_app.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 12: Commit**

```bash
git add app/__init__.py app/routes/__init__.py app/routes/auth_routes.py \
        app/templates/base.html app/templates/login.html app/static/css/app.css \
        manage_users.py tests/conftest.py tests/test_app.py
git commit -m "feat: add Flask app factory, auth routes, base templates, and manage_users CLI"
```

---

### Task 9: Admin routes + admin template

**Files:**
- Create: `app/routes/admin_routes.py`
- Create: `app/templates/admin.html`
- Create: `app/static/js/admin.js`
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: `admin_required` from `app.decorators`, `list_groups`, `create_group`, `update_group`, `delete_group` from `app.groups`, `list_users` from `app.auth`, `get_log_entries`, `set_log_level`, `clear_log_entries` from `app.app_logger`, `get_all`, `set_setting` from `app.app_settings`, `registry.get_registry()`
- Produces:
  - `GET /admin` — admin page
  - `GET /admin/api/groups` → `[{name, members, allowed_tabs, domain_restrict, allowed_domains}]`
  - `POST /admin/api/groups` `{"name", "members", "allowed_tabs", "domain_restrict", "allowed_domains"}`
  - `PUT /admin/api/groups/<name>`
  - `DELETE /admin/api/groups/<name>`
  - `GET /admin/api/users` → `[{username, role}]`
  - `GET /admin/api/domains` → `[]` (stub — populated in Plan 2)
  - `GET /admin/api/logs?level=&component=&limit=` → `[{ts, level, component, message, extra?}]`
  - `POST /admin/api/logs/level` `{"level": "DEBUG"}`
  - `DELETE /admin/api/logs`
  - `GET /admin/api/tabs` → `{key: name}`
  - `GET /admin/api/settings` → `{}`
  - `PUT /admin/api/settings` `{key: value}`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin.py`:

```python
import json
import time
import pytest


@pytest.fixture
def admin_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    import app.groups as groups_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = []
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
    return client


def _csrf(client):
    with client.session_transaction() as sess:
        return sess.get("_csrf_token", "")


def test_admin_page_loads(admin_client):
    r = admin_client.get("/admin")
    assert r.status_code == 200


def test_viewer_cannot_access_admin(client):
    r = client.get("/admin")
    assert r.status_code in (302, 403)


def test_list_users(admin_client):
    r = admin_client.get("/admin/api/users")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)


def test_create_and_list_group(admin_client):
    token = _csrf(admin_client)
    r = admin_client.post(
        "/admin/api/groups",
        json={"name": "ops", "members": [], "allowed_tabs": ["dashboard"], "domain_restrict": False, "allowed_domains": []},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 201
    r2 = admin_client.get("/admin/api/groups")
    names = [g["name"] for g in r2.get_json()]
    assert "ops" in names


def test_delete_group(admin_client):
    token = _csrf(admin_client)
    admin_client.post(
        "/admin/api/groups",
        json={"name": "temp", "members": [], "allowed_tabs": [], "domain_restrict": False, "allowed_domains": []},
        headers={"X-CSRF-Token": token},
    )
    r = admin_client.delete("/admin/api/groups/temp", headers={"X-CSRF-Token": token})
    assert r.status_code == 200


def test_get_logs(admin_client):
    from app.app_logger import app_log
    app_log("INFO", "test", "test message")
    r = admin_client.get("/admin/api/logs")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_get_tabs(admin_client):
    r = admin_client.get("/admin/api/tabs")
    assert r.status_code == 200
    assert isinstance(r.get_json(), dict)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_admin.py -v
```

Expected: ImportError or 404 — admin routes not yet registered.

- [ ] **Step 3: Create `app/routes/admin_routes.py`**

```python
"""Admin-only routes.

Page:  GET  /admin

Groups API:
  GET    /admin/api/groups
  POST   /admin/api/groups           {name, members, allowed_tabs, domain_restrict, allowed_domains}
  PUT    /admin/api/groups/<name>
  DELETE /admin/api/groups/<name>
  GET    /admin/api/users

Domains cache (stub — populated in Plan 2):
  GET    /admin/api/domains

Logs API:
  GET    /admin/api/logs?level=&component=&limit=
  POST   /admin/api/logs/level       {level}
  DELETE /admin/api/logs

Tab registry:
  GET    /admin/api/tabs

Settings:
  GET    /admin/api/settings
  PUT    /admin/api/settings
"""

from flask import Blueprint, jsonify, render_template, request, session

from app.decorators import admin_required
from app.groups import (
    create_group, delete_group, get_group, list_groups, update_group, KNOWN_TABS,
)
from app.auth import list_users
from app.app_logger import (
    app_log, clear_log_entries, get_log_entries, get_log_level,
    get_log_levels, set_log_level,
)
from app.app_settings import get_all as get_all_settings, set_setting
from app import registry
from app.security import internal_api_error

bp = Blueprint("admin", __name__)


@bp.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html", user=session["user"])


# ── Users ─────────────────────────────────────────────────────────────────


@bp.route("/admin/api/users")
@admin_required
def api_users():
    return jsonify(list_users())


# ── Groups ────────────────────────────────────────────────────────────────


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


# ── Domains cache (stub) ──────────────────────────────────────────────────


@bp.route("/admin/api/domains")
@admin_required
def api_domains():
    try:
        from app import domain_cache
        return jsonify(domain_cache.get_domains())
    except Exception:
        return jsonify([])


# ── Logs ──────────────────────────────────────────────────────────────────


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


# ── Tabs ──────────────────────────────────────────────────────────────────


@bp.route("/admin/api/tabs")
@admin_required
def api_tabs():
    return jsonify(registry.known_tabs())


# ── Settings ──────────────────────────────────────────────────────────────


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
```

- [ ] **Step 4: Register admin blueprint** — add `"app.routes.admin_routes"` to `_BLUEPRINT_MODULES` in `app/__init__.py` (it is already included in Task 8's factory code; verify it's present)

- [ ] **Step 5: Create minimal `app/templates/admin.html`**

```html
{% extends "base.html" %}
{% block title %}Admin — check.health{% endblock %}

{% block content %}
<div class="page-header">
  <h2>&#9881; Admin</h2>
</div>

<!-- ── Tab bar ──────────────────────────────────────────────────────────── -->
<div class="admin-tabs" id="adminTabBar">
  <button class="admin-tab active" data-tab="users">Users</button>
  <button class="admin-tab" data-tab="groups">Groups</button>
  <button class="admin-tab" data-tab="logs">Logs</button>
  <button class="admin-tab" data-tab="settings">Settings</button>
  <button class="admin-tab" data-tab="tabs">Tab Registry</button>
</div>

<!-- ── Users panel ──────────────────────────────────────────────────────── -->
<div class="admin-panel" id="panel-users">
  <div class="card" style="margin-top:1rem">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
      <strong>Local Users</strong>
      <a href="#" class="btn btn-sm btn-primary" id="addUserBtn">+ Add User</a>
    </div>
    <div class="table-wrapper">
      <table class="data-table" id="usersTable">
        <thead><tr><th>Username</th><th>Role</th><th></th></tr></thead>
        <tbody id="usersTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── Groups panel ─────────────────────────────────────────────────────── -->
<div class="admin-panel" id="panel-groups" style="display:none">
  <div class="card" style="margin-top:1rem">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
      <strong>Groups</strong>
      <button class="btn btn-sm btn-primary" id="addGroupBtn">+ Add Group</button>
    </div>
    <div class="table-wrapper">
      <table class="data-table" id="groupsTable">
        <thead><tr><th>Name</th><th>Members</th><th>Allowed Tabs</th><th>Domain Restrict</th><th></th></tr></thead>
        <tbody id="groupsTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── Logs panel ───────────────────────────────────────────────────────── -->
<div class="admin-panel" id="panel-logs" style="display:none">
  <div class="card" style="margin-top:1rem">
    <div style="display:flex;gap:.5rem;align-items:center;margin-bottom:.75rem;flex-wrap:wrap">
      <strong>Application Logs</strong>
      <select id="logLevelFilter" class="form-select" style="width:auto">
        <option value="">All levels</option>
        <option value="DEBUG">DEBUG+</option>
        <option value="INFO">INFO+</option>
        <option value="WARN">WARN+</option>
        <option value="ERROR">ERROR</option>
      </select>
      <input type="text" id="logComponentFilter" class="form-control" style="width:160px" placeholder="Component filter">
      <button class="btn btn-sm btn-secondary" id="logRefreshBtn">&#8635; Refresh</button>
      <button class="btn btn-sm btn-secondary" id="logClearBtn">&#10005; Clear</button>
    </div>
    <div class="table-wrapper" style="max-height:500px;overflow-y:auto">
      <table class="data-table" id="logsTable">
        <thead><tr><th>Time</th><th>Level</th><th>Component</th><th>Message</th></tr></thead>
        <tbody id="logsTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── Settings panel ───────────────────────────────────────────────────── -->
<div class="admin-panel" id="panel-settings" style="display:none">
  <div class="card" style="margin-top:1rem">
    <strong>Application Settings</strong>
    <div id="settingsBody" style="margin-top:.75rem"></div>
  </div>
</div>

<!-- ── Tab Registry panel ───────────────────────────────────────────────── -->
<div class="admin-panel" id="panel-tabs" style="display:none">
  <div class="card" style="margin-top:1rem">
    <strong>Registered Tabs</strong>
    <div class="table-wrapper" style="margin-top:.75rem">
      <table class="data-table" id="tabsTable">
        <thead><tr><th>Key</th><th>Display Name</th></tr></thead>
        <tbody id="tabsTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── Group edit modal ──────────────────────────────────────────────────── -->
<div id="groupModal" class="modal-overlay" style="display:none">
  <div class="modal-box">
    <div class="modal-header">
      <span class="modal-title" id="groupModalTitle">Group</span>
      <button class="modal-close" id="groupModalClose">&#10005;</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label class="form-label">Name</label>
        <input type="text" id="groupName" class="form-control">
      </div>
      <div class="form-group">
        <label class="form-label">Members (usernames, one per line)</label>
        <textarea id="groupMembers" class="form-control" rows="3"></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Allowed Tabs</label>
        <div id="groupTabChecks"></div>
      </div>
      <div class="form-group">
        <label class="form-label">
          <input type="checkbox" id="groupDomainRestrict"> Domain Restriction
        </label>
      </div>
      <div class="form-group" id="groupDomainsRow" style="display:none">
        <label class="form-label">Allowed Domains (one per line)</label>
        <textarea id="groupDomains" class="form-control" rows="3"></textarea>
      </div>
      <div style="display:flex;gap:.5rem;justify-content:flex-end;margin-top:1rem">
        <button class="btn btn-secondary" id="groupModalCancel">Cancel</button>
        <button class="btn btn-primary" id="groupModalSave">Save</button>
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/admin.js') }}?v=1"></script>
{% endblock %}
```

- [ ] **Step 6: Create `app/static/js/admin.js`** (core functionality)

```javascript
const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

// ── Tab switching ─────────────────────────────────────────────────────────
document.querySelectorAll('.admin-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.admin-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.admin-panel').forEach(p => p.style.display = 'none');
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.tab).style.display = '';
    loadTab(btn.dataset.tab);
  });
});

function loadTab(tab) {
  if (tab === 'users') loadUsers();
  else if (tab === 'groups') loadGroups();
  else if (tab === 'logs') loadLogs();
  else if (tab === 'settings') loadSettings();
  else if (tab === 'tabs') loadTabs();
}

// ── CSS for admin tabs ────────────────────────────────────────────────────
const style = document.createElement('style');
style.textContent = `
  .admin-tabs { display:flex; gap:.25rem; border-bottom:2px solid var(--border); margin-bottom:0; }
  .admin-tab { background:none; border:none; padding:.5rem 1rem; cursor:pointer; font-size:.875rem; color:var(--text-muted); border-bottom:2px solid transparent; margin-bottom:-2px; }
  .admin-tab.active { color:var(--primary); border-bottom-color:var(--primary); font-weight:600; }
`;
document.head.appendChild(style);

// ── Users ─────────────────────────────────────────────────────────────────
async function loadUsers() {
  const r = await fetch('/admin/api/users');
  const users = await r.json();
  const tbody = document.getElementById('usersTbody');
  tbody.innerHTML = users.map(u => `
    <tr>
      <td>${esc(u.username)}</td>
      <td><span class="badge badge-${u.role === 'admin' ? 'danger' : 'secondary'}">${esc(u.role)}</span></td>
      <td></td>
    </tr>
  `).join('');
}

// ── Groups ────────────────────────────────────────────────────────────────
let allTabs = {};
let editingGroup = null;

async function loadGroups() {
  const [gr, tr] = await Promise.all([
    fetch('/admin/api/groups').then(r => r.json()),
    fetch('/admin/api/tabs').then(r => r.json()),
  ]);
  allTabs = tr;
  const tbody = document.getElementById('groupsTbody');
  tbody.innerHTML = gr.map(g => `
    <tr>
      <td>${esc(g.name)}</td>
      <td>${esc((g.members || []).join(', '))}</td>
      <td>${esc((g.allowed_tabs || []).join(', '))}</td>
      <td>${g.domain_restrict ? 'Yes: ' + esc((g.allowed_domains || []).join(', ')) : 'No'}</td>
      <td>
        <button class="btn btn-sm btn-secondary" onclick="openGroupEdit(${JSON.stringify(g)})">Edit</button>
        <button class="btn btn-sm btn-secondary" onclick="deleteGroup('${esc(g.name)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

document.getElementById('addGroupBtn').addEventListener('click', () => openGroupEdit(null));
document.getElementById('groupModalClose').addEventListener('click', () => document.getElementById('groupModal').style.display = 'none');
document.getElementById('groupModalCancel').addEventListener('click', () => document.getElementById('groupModal').style.display = 'none');
document.getElementById('groupDomainRestrict').addEventListener('change', function() {
  document.getElementById('groupDomainsRow').style.display = this.checked ? '' : 'none';
});

function openGroupEdit(g) {
  editingGroup = g ? g.name : null;
  document.getElementById('groupModalTitle').textContent = g ? 'Edit Group' : 'New Group';
  document.getElementById('groupName').value = g ? g.name : '';
  document.getElementById('groupName').disabled = !!g;
  document.getElementById('groupMembers').value = g ? (g.members || []).join('\n') : '';
  document.getElementById('groupDomainRestrict').checked = g ? !!g.domain_restrict : false;
  document.getElementById('groupDomains').value = g ? (g.allowed_domains || []).join('\n') : '';
  document.getElementById('groupDomainsRow').style.display = (g && g.domain_restrict) ? '' : 'none';

  const checks = document.getElementById('groupTabChecks');
  checks.innerHTML = Object.entries(allTabs).map(([key, name]) => `
    <label style="display:inline-flex;align-items:center;gap:.35rem;margin-right:1rem">
      <input type="checkbox" value="${esc(key)}" ${g && (g.allowed_tabs || []).includes(key) ? 'checked' : ''}>
      ${esc(name)}
    </label>
  `).join('');
  document.getElementById('groupModal').style.display = 'flex';
}

document.getElementById('groupModalSave').addEventListener('click', async () => {
  const name = document.getElementById('groupName').value.trim();
  if (!name) { alert('Name is required'); return; }
  const members = document.getElementById('groupMembers').value.split('\n').map(s => s.trim()).filter(Boolean);
  const allowed_tabs = Array.from(document.querySelectorAll('#groupTabChecks input:checked')).map(el => el.value);
  const domain_restrict = document.getElementById('groupDomainRestrict').checked;
  const allowed_domains = document.getElementById('groupDomains').value.split('\n').map(s => s.trim()).filter(Boolean);

  const method = editingGroup ? 'PUT' : 'POST';
  const url = editingGroup ? `/admin/api/groups/${encodeURIComponent(editingGroup)}` : '/admin/api/groups';
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
    body: JSON.stringify({ name, members, allowed_tabs, domain_restrict, allowed_domains }),
  });
  if (r.ok) { document.getElementById('groupModal').style.display = 'none'; loadGroups(); }
  else { const e = await r.json(); alert(e.error || 'Error saving group'); }
});

async function deleteGroup(name) {
  if (!confirm(`Delete group '${name}'?`)) return;
  await fetch(`/admin/api/groups/${encodeURIComponent(name)}`, { method: 'DELETE', headers: { 'X-CSRF-Token': CSRF } });
  loadGroups();
}

// ── Logs ──────────────────────────────────────────────────────────────────
document.getElementById('logRefreshBtn').addEventListener('click', loadLogs);
document.getElementById('logClearBtn').addEventListener('click', async () => {
  await fetch('/admin/api/logs', { method: 'DELETE', headers: { 'X-CSRF-Token': CSRF } });
  loadLogs();
});

async function loadLogs() {
  const level = document.getElementById('logLevelFilter').value;
  const component = document.getElementById('logComponentFilter').value.trim();
  const params = new URLSearchParams({ limit: 500 });
  if (level) params.set('level', level);
  if (component) params.set('component', component);
  const entries = await fetch(`/admin/api/logs?${params}`).then(r => r.json());
  const LEVEL_CLASS = { ERROR: 'danger', WARN: 'warning', INFO: 'secondary', DEBUG: 'secondary', TRACE: 'secondary' };
  const tbody = document.getElementById('logsTbody');
  tbody.innerHTML = [...entries].reverse().map(e => `
    <tr>
      <td style="white-space:nowrap;font-size:.78rem">${esc(e.ts)}</td>
      <td><span class="badge badge-${LEVEL_CLASS[e.level] || 'secondary'}">${esc(e.level)}</span></td>
      <td style="font-size:.82rem">${esc(e.component)}</td>
      <td style="font-size:.82rem">${esc(e.message)}${e.extra ? ' <span class="text-muted">— ' + esc(JSON.stringify(e.extra)) + '</span>' : ''}</td>
    </tr>
  `).join('');
}

// ── Settings ──────────────────────────────────────────────────────────────
async function loadSettings() {
  const settings = await fetch('/admin/api/settings').then(r => r.json());
  const body = document.getElementById('settingsBody');
  if (Object.keys(settings).length === 0) {
    body.innerHTML = '<p class="text-muted" style="font-size:.875rem">No settings configured.</p>';
    return;
  }
  body.innerHTML = Object.entries(settings).map(([k, v]) => `
    <div style="display:flex;align-items:center;gap:1rem;padding:.5rem 0;border-bottom:1px solid var(--border)">
      <code style="flex:0 0 220px">${esc(k)}</code>
      <span>${esc(String(v))}</span>
    </div>
  `).join('');
}

// ── Tab Registry ──────────────────────────────────────────────────────────
async function loadTabs() {
  const tabs = await fetch('/admin/api/tabs').then(r => r.json());
  const tbody = document.getElementById('tabsTbody');
  tbody.innerHTML = Object.entries(tabs).map(([k, v]) => `
    <tr><td><code>${esc(k)}</code></td><td>${esc(v)}</td></tr>
  `).join('');
}

// ── Helpers ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────
loadUsers();
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_admin.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 8: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS.

- [ ] **Step 9: Commit**

```bash
git add app/routes/admin_routes.py app/templates/admin.html app/static/js/admin.js tests/test_admin.py
git commit -m "feat: add admin tab with groups, users, logs, and settings management"
```

---

### Task 10: Public repo documentation + smoke test the app

**Files:**
- Create: `README.md`
- Create: `CHANGELOG.md`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `CODE_OF_CONDUCT.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# check.health

A read-only web dashboard for **Check Point Provider-1 (MDS)** environments.

## Features

- **Dashboard** — managed gateway counts, 30-day trend charts, infrastructure health (MDS HA pair + log servers)
- **Firewalls** — browse gateways and clusters by domain with full details
- **Rule Review** — view access rulebases, look up objects, interfaces, and NAT rules by domain
- **Admin** — local user management, group-based access control, application logs

## Requirements

- Python ≥ 3.11
- [UV](https://docs.astral.sh/uv/) package manager
- A Check Point Provider-1 (MDS) environment with a read-only API key

---

## Deployment

### macOS (local development)

```bash
# Install UV if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone <repo-url>
cd check.health
uv sync

cp .env.example .env
# Edit .env — set SECRET_KEY, CP_MDS_PRIMARY, CP_API_KEY, etc.
# Generate a SECRET_KEY: python manage_users.py secret

python manage_users.py add admin --role admin
uv run flask --app app run --debug
```

Open http://127.0.0.1:5000

### Red Hat Enterprise Linux / Rocky Linux / AlmaLinux

```bash
# Install Python 3.11+ (RHEL 9 ships with 3.11; RHEL 8 needs the module stream)
# RHEL 9:
sudo dnf install -y python3.11 python3.11-pip

# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # or open a new shell

# Clone and set up the project
git clone <repo-url>
cd check.health
uv sync

cp .env.example .env
# Edit .env — fill in all CP_* values and SECRET_KEY

python manage_users.py add admin --role admin

# Run under gunicorn for production use
uv run gunicorn --workers 2 --bind 0.0.0.0:8080 wsgi:application
```

To run as a systemd service, create `/etc/systemd/system/check-health.service`:

```ini
[Unit]
Description=check.health web application
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/check.health
EnvironmentFile=/opt/check.health/.env
ExecStart=/opt/check.health/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8080 wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now check-health
```

### Container (Docker / Podman)

Create a `Dockerfile` at the project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install uv && uv sync --no-dev

COPY app/ app/
COPY wsgi.py manage_users.py ./

# Runtime data lives in a mounted volume — not baked into the image
VOLUME ["/app/data"]
ENV USERS_FILE=/app/data/users.json
ENV GROUPS_FILE=/app/data/groups.json
ENV APP_SETTINGS_FILE=/app/data/app_settings.json

EXPOSE 8080
CMD ["uv", "run", "gunicorn", "--workers", "2", "--bind", "0.0.0.0:8080", "wsgi:application"]
```

```bash
# Build
docker build -t check-health .

# Run (pass .env file; mount a data volume for persistent users/groups)
docker run -d \
  --name check-health \
  --env-file .env \
  -v check-health-data:/app/data \
  -p 8080:8080 \
  check-health
```

> **Note:** The container image never contains `.env`, `users.json`, `groups.json`, or any credentials. Always pass secrets via `--env-file` or orchestrator secrets (Kubernetes Secrets, Podman secrets, etc.).

---

## Configuration

See `.env.example` for all available configuration options.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## License

[MIT](LICENSE)
```

- [ ] **Step 2: Create `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Project foundation: Flask app factory, local bcrypt auth, group-based access control
- Admin tab: user management, group management, application log viewer, settings
```

- [ ] **Step 3: Create `CONTRIBUTING.md`**

```markdown
# Contributing

Thank you for considering a contribution to check.health!

## Development Setup

```bash
git clone <repo-url>
cd check.health
uv sync
cp .env.example .env  # fill in values
python manage_users.py add dev --role admin
uv run flask --app app run --debug
```

## Running Tests

```bash
uv run pytest -v
```

## Branch Convention

- `main` — stable releases
- `dev` — active development; open PRs against this branch
- Feature branches: `feat/<short-description>`

## Pull Requests

1. Fork the repo and create a feature branch from `dev`
2. Write tests for new behaviour
3. Ensure all tests pass (`uv run pytest`)
4. Open a PR against the `dev` branch with a clear description
```

- [ ] **Step 4: Create `SECURITY.md`**

```markdown
# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | ✅ |

## Reporting a Vulnerability

Please do **not** open a public GitHub issue for security vulnerabilities.

Instead, report them via GitHub's private [Security Advisories](../../security/advisories/new) feature.

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You can expect an acknowledgement within 48 hours and a resolution timeline within 14 days for critical issues.
```

- [ ] **Step 5: Create `CODE_OF_CONDUCT.md`**

```markdown
# Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/) Code of Conduct, version 2.1.

In short: be respectful, be constructive, and focus on the work.

Instances of unacceptable behaviour may be reported to the project maintainers.
```

- [ ] **Step 6: Smoke test the app manually**

```bash
cp .env.example .env
# Edit .env: set SECRET_KEY to any 32+ char string (e.g. run: python manage_users.py secret)
# Leave CP_* settings as placeholders — the app starts without them
python manage_users.py add admin --role admin
uv run flask --app app run --debug
```

Open http://127.0.0.1:5000 in a browser. Verify:
- Login page loads
- Login with admin/yourpassword works
- Admin tab is visible and loads (users, groups, logs, settings, tab registry panels all render)
- Logout works

- [ ] **Step 7: Commit**

```bash
git add README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md
git commit -m "docs: add public repo documentation files"
```

---

## Plan Complete

**What this plan delivers:** A fully working Flask web application with login, session management, rate-limited auth, admin panel (user + group management, log viewer, settings), and all security infrastructure in place. No Check Point API calls yet.

**Next plans:**
- **Plan 2:** Check Point MDS client + background scheduler jobs + Dashboard tab (summary tiles, trend charts, infrastructure health cards)
- **Plan 3:** Firewalls tab + Rule Review tab (policy rules, object/interface/NAT lookups)
