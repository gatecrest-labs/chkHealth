# Plan 2: CP Client, Background Jobs & Dashboard Tab

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Check Point MDS API client, three background scheduler jobs (domain cache, summary counts, infra health), and the Dashboard tab — delivering summary tiles, 30-day sparkline charts, and infrastructure health cards without blocking any request path.

**Architecture:** `CPClient` wraps the CP Management REST API via `requests`. `make_client()` provides an HA failover context manager (primary → secondary). Three `APScheduler BackgroundScheduler` jobs run on startup: `run_summary_job` (hourly), `refresh_infra_health` (15 min), `refresh_domains` (30 min). Dashboard routes read from in-memory caches and SQLite history — no CP API calls block the request path.

**Tech Stack:** Python ≥ 3.11, Flask ≥ 3.1, UV, requests, APScheduler BackgroundScheduler, SQLite (stdlib `sqlite3`), `unittest.mock` for tests

**Spec:** docs/superpowers/specs/2026-09-19-check-health-design.md

## Global Constraints

- Python ≥ 3.11 — use union type hints `X | Y`
- UV package manager — never `pip install` directly
- No real hostnames, IPs, API keys, or credentials in any committed file
- Public repo — no internal references anywhere in committed code
- No comments explaining what code does — only WHY comments if non-obvious
- TDD: write failing test first, then implement
- `requests` library for HTTP; `unittest.mock` to patch in tests (no live MDS needed)
- APScheduler `BackgroundScheduler` — already in pyproject.toml
- SQLite via stdlib `sqlite3` only
- Suppress urllib3 `InsecureRequestWarning` when `verify_ssl=False`; ensure warnings do not appear in test output
- Test runner: `uv run pytest`
- All new tests must pass alongside the existing Plan 1 test suite

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/cp_client.py` | Create | `CPClient` class, `CPAPIError`, all CP API methods |
| `app/cp_helpers.py` | Create | `_HAContext`, `make_client()` HA failover context manager |
| `app/domain_cache.py` | Create | In-memory domain list cache, `refresh_domains()` |
| `app/host_metrics.py` | Create | SQLite `summary_history` table, upsert, history query |
| `app/summary_job.py` | Create | APScheduler job — gateway + rule counts, in-memory cache |
| `app/infra_health_cache.py` | Create | MDS + MLS health polling, in-memory cache |
| `app/routes/dashboard_routes.py` | Create | Dashboard blueprint — page + API endpoints |
| `app/__init__.py` | Modify | Register dashboard blueprint, APScheduler wiring |
| `app/templates/dashboard.html` | Create | Summary tiles, sparklines, infra health cards |
| `app/static/js/dashboard.js` | Create | Fetch summary + health, draw sparklines, refresh controls |
| `app/static/css/app.css` | Modify | Add sparkline section + auto-refresh selector styles |
| `tests/test_cp_client.py` | Create | CPClient unit tests (mocked requests) |
| `tests/test_cp_helpers.py` | Create | HA failover + domain cache tests |
| `tests/test_host_metrics.py` | Create | SQLite store tests |
| `tests/test_summary_job.py` | Create | Summary job tests (mocked client) |
| `tests/test_infra_health_cache.py` | Create | Infra health cache tests (mocked socket + client) |
| `tests/test_dashboard_routes.py` | Create | Dashboard route tests |

---

### Task 1: `app/cp_client.py` — CPClient + CPAPIError

**Files:**
- Create: `app/cp_client.py`
- Create: `tests/test_cp_client.py`

**Interfaces:**
- `class CPAPIError(Exception)` — `__init__(self, message: str, command: str, data: dict)`
- `class CPClient.__init__(self, host, api_key, verify_ssl=False, timeout=30)`
- `CPClient.login(domain=None) -> None` — sets `self._sid`; domain-scoped login when domain is provided
- `CPClient.logout() -> None` — swallows its own exceptions
- `CPClient.call(command, payload=None) -> dict` — raises `CPAPIError` when `"success": false`
- `CPClient.get_domains() -> list[dict]`
- `CPClient.get_api_version() -> dict`
- `CPClient.get_gateways() -> list[dict]`
- `CPClient.get_clusters() -> list[dict]`
- `CPClient.get_packages() -> list[dict]`
- `CPClient.get_access_rulebase(package) -> list[dict]`
- `CPClient.__enter__() -> CPClient` — calls `login(domain=self._domain)`
- `CPClient.__exit__(*args) -> None` — calls `logout()`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cp_client.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


def _resp(data: dict):
    r = MagicMock()
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


@pytest.fixture
def client():
    from app.cp_client import CPClient
    return CPClient("10.0.0.1", "test-key", verify_ssl=False, timeout=10)


def test_login_stores_sid(client):
    with patch.object(client._session, "post", return_value=_resp({"sid": "abc123"})):
        client.login()
    assert client._sid == "abc123"


def test_login_with_domain_sends_domain(client):
    with patch.object(client._session, "post", return_value=_resp({"sid": "dSid"})) as mock_post:
        client.login(domain="MyDomain")
    payload = mock_post.call_args.kwargs["json"]
    assert payload.get("domain") == "MyDomain"


def test_call_sends_sid_header(client):
    client._sid = "my-sid"
    with patch.object(client._session, "post",
                      return_value=_resp({"total": 0, "objects": [], "success": True})) as mock_post:
        client.call("show-domains")
    headers = mock_post.call_args.kwargs.get("headers") or {}
    assert headers.get("X-chkp-sid") == "my-sid"


def test_call_raises_cp_api_error_on_failure(client):
    from app.cp_client import CPAPIError
    client._sid = "sid"
    with patch.object(client._session, "post",
                      return_value=_resp({"success": False, "message": "Not found"})):
        with pytest.raises(CPAPIError) as exc_info:
            client.call("show-objects", {"name": "bad"})
    assert exc_info.value.command == "show-objects"


def test_get_domains_returns_objects(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "objects": [{"name": "D1"}, {"name": "D2"}], "total": 2, "success": True,
    })):
        domains = client.get_domains()
    assert [d["name"] for d in domains] == ["D1", "D2"]


def test_get_gateways_paginates(client):
    client._sid = "sid"
    page1 = {"objects": [{"name": f"gw{i}"} for i in range(500)], "total": 501, "success": True}
    page2 = {"objects": [{"name": "gw500"}], "total": 501, "success": True}
    with patch.object(client._session, "post") as mock_post:
        mock_post.side_effect = [_resp(page1), _resp(page2)]
        gws = client.get_gateways()
    assert len(gws) == 501
    assert mock_post.call_count == 2


def test_context_manager_calls_login_logout(client):
    with patch.object(client, "login") as mock_login, \
         patch.object(client, "logout") as mock_logout:
        with client:
            pass
    mock_login.assert_called_once_with(domain=None)
    mock_logout.assert_called_once()


def test_context_manager_logs_out_on_body_exception(client):
    with patch.object(client, "login"), patch.object(client, "logout") as mock_logout:
        try:
            with client:
                raise ValueError("test error")
        except ValueError:
            pass
    mock_logout.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_cp_client.py -v
```

Expected: `ImportError` — `app.cp_client` does not exist yet.

- [ ] **Step 3: Create `app/cp_client.py`**

```python
from __future__ import annotations

import warnings

import requests
import urllib3


class CPAPIError(Exception):
    def __init__(self, message: str, command: str, data: dict):
        super().__init__(message)
        self.command = command
        self.data = data


class CPClient:
    def __init__(
        self,
        host: str,
        api_key: str,
        verify_ssl: bool = False,
        timeout: int = 30,
    ):
        self.host = host
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._sid: str | None = None
        self._domain: str | None = None
        self._session = requests.Session()
        if not verify_ssl:
            warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

    def _url(self, command: str) -> str:
        return f"https://{self.host}/web_api/{command}"

    def login(self, domain: str | None = None) -> None:
        self._domain = domain
        payload: dict = {"api-key": self._api_key}
        if domain:
            payload["domain"] = domain
        resp = self._session.post(
            self._url("login"),
            json=payload,
            headers={"Content-Type": "application/json"},
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        self._sid = resp.json()["sid"]

    def logout(self) -> None:
        if not self._sid:
            return
        try:
            self._session.post(
                self._url("logout"),
                json={},
                headers={"Content-Type": "application/json", "X-chkp-sid": self._sid},
                verify=self._verify_ssl,
                timeout=self._timeout,
            )
        except Exception:
            pass
        finally:
            self._sid = None

    def call(self, command: str, payload: dict | None = None) -> dict:
        resp = self._session.post(
            self._url(command),
            json=payload or {},
            headers={
                "Content-Type": "application/json",
                "X-chkp-sid": self._sid or "",
            },
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise CPAPIError(data.get("message", "API call failed"), command, data)
        return data

    def _fetch_all(self, command: str, extra: dict | None = None) -> list[dict]:
        results: list[dict] = []
        offset = 0
        limit = 500
        while True:
            data = self.call(command, {"limit": limit, "offset": offset, **(extra or {})})
            objects = data.get("objects", [])
            results.extend(objects)
            if len(results) >= data.get("total", len(results)):
                break
            offset += limit
        return results

    def get_domains(self) -> list[dict]:
        return self._fetch_all("show-domains")

    def get_api_version(self) -> dict:
        return self.call("show-api-versions")

    def get_gateways(self) -> list[dict]:
        return self._fetch_all("show-simple-gateways")

    def get_clusters(self) -> list[dict]:
        return self._fetch_all("show-simple-clusters")

    def get_packages(self) -> list[dict]:
        return self._fetch_all("show-packages")

    def get_access_rulebase(self, package: str) -> list[dict]:
        return self._fetch_all("show-access-rulebase", {"name": package})

    def __enter__(self) -> "CPClient":
        self.login(domain=self._domain)
        return self

    def __exit__(self, *args) -> None:
        self.logout()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_cp_client.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cp_client.py tests/test_cp_client.py
git commit -m "feat: add CPClient with CP Management API wrapper, pagination, and HA-ready interface

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: `app/cp_helpers.py` + `app/domain_cache.py`

**Files:**
- Create: `app/cp_helpers.py`
- Create: `app/domain_cache.py`
- Create: `tests/test_cp_helpers.py`

**Interfaces:**
- `class _HAContext` — internal; `__enter__` returns `CPClient`, `__exit__` calls logout
- `make_client(domain=None) -> _HAContext` — public factory; tries primary then secondary
- `get_cached_domains() -> dict` — `{"domains": [...], "last_updated": str|None, "status": "ok"|"error"|"empty"}`
- `refresh_domains() -> None` — calls `make_client()`, updates in-memory cache

- [ ] **Step 1: Write failing tests**

Create `tests/test_cp_helpers.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


def _patch_config(monkeypatch):
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "10.0.0.1")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY", "10.0.0.2")
    monkeypatch.setattr("app.config.Config.CP_API_KEY", "test-key")
    monkeypatch.setattr("app.config.Config.CP_VERIFY_SSL", False)
    monkeypatch.setattr("app.config.Config.CP_TIMEOUT", 10)
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY_LABEL", "Primary")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY_LABEL", "Secondary")


def test_make_client_connects_to_primary(monkeypatch):
    _patch_config(monkeypatch)
    mock_instance = MagicMock()
    mock_instance.login.return_value = None
    with patch("app.cp_helpers.CPClient", return_value=mock_instance):
        from app.cp_helpers import make_client
        with make_client() as client:
            pass
    mock_instance.login.assert_called_once()
    mock_instance.logout.assert_called_once()


def test_make_client_falls_back_to_secondary(monkeypatch):
    _patch_config(monkeypatch)
    primary = MagicMock()
    primary.login.side_effect = ConnectionError("primary down")
    secondary = MagicMock()
    secondary.login.return_value = None
    with patch("app.cp_helpers.CPClient", side_effect=[primary, secondary]):
        from app.cp_helpers import make_client
        with make_client() as client:
            result = client
    assert result is secondary


def test_make_client_raises_when_both_fail(monkeypatch):
    _patch_config(monkeypatch)
    bad = MagicMock()
    bad.login.side_effect = ConnectionError("down")
    with patch("app.cp_helpers.CPClient", side_effect=[bad, bad]):
        from app.cp_helpers import make_client
        with pytest.raises(ConnectionError):
            with make_client():
                pass


def test_make_client_skips_empty_primary(monkeypatch):
    _patch_config(monkeypatch)
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "")
    secondary = MagicMock()
    secondary.login.return_value = None
    with patch("app.cp_helpers.CPClient", return_value=secondary):
        from app.cp_helpers import make_client
        with make_client() as client:
            pass
    secondary.login.assert_called_once()


def test_get_cached_domains_initial_state():
    from app.domain_cache import get_cached_domains
    result = get_cached_domains()
    assert "domains" in result
    assert "status" in result


def test_refresh_domains_updates_cache(monkeypatch):
    _patch_config(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_domains.return_value = [{"name": "D1"}, {"name": "D2"}]
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_client)
    mock_cm.__exit__ = MagicMock(return_value=False)
    with patch("app.domain_cache.make_client", return_value=mock_cm):
        from app.domain_cache import refresh_domains, get_cached_domains
        refresh_domains()
    cache = get_cached_domains()
    assert cache["status"] == "ok"
    assert len(cache["domains"]) == 2


def test_refresh_domains_sets_error_on_failure():
    mock_cm = MagicMock()
    mock_cm.__enter__.side_effect = ConnectionError("all hosts down")
    with patch("app.domain_cache.make_client", return_value=mock_cm):
        from app.domain_cache import refresh_domains, get_cached_domains
        refresh_domains()
    assert get_cached_domains()["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_cp_helpers.py -v
```

Expected: `ImportError` — modules not yet created.

- [ ] **Step 3: Create `app/cp_helpers.py`**

```python
from __future__ import annotations

from app.app_logger import app_log
from app.cp_client import CPClient


class _HAContext:
    def __init__(self, domain: str | None = None):
        self._domain = domain
        self._client: CPClient | None = None

    def __enter__(self) -> CPClient:
        from app.config import Config
        candidates = [
            (Config.CP_MDS_PRIMARY, Config.CP_MDS_PRIMARY_LABEL),
            (Config.CP_MDS_SECONDARY, Config.CP_MDS_SECONDARY_LABEL),
        ]
        for host, label in candidates:
            if not host:
                continue
            try:
                client = CPClient(
                    host,
                    Config.CP_API_KEY,
                    Config.CP_VERIFY_SSL,
                    Config.CP_TIMEOUT,
                )
                client.login(domain=self._domain)
                self._client = client
                app_log("DEBUG", "cp_helpers", f"Connected via {label}")
                return client
            except Exception as exc:
                app_log("WARN", "cp_helpers", f"Failed to connect to {label}", exc=str(exc))
        raise ConnectionError("Could not connect to any configured MDS host")

    def __exit__(self, *args) -> None:
        if self._client:
            self._client.logout()


def make_client(domain: str | None = None) -> _HAContext:
    return _HAContext(domain)
```

- [ ] **Step 4: Create `app/domain_cache.py`**

```python
from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.app_logger import app_log

_lock = threading.Lock()
_cache: dict = {"domains": [], "last_updated": None, "status": "empty"}


def get_cached_domains() -> dict:
    with _lock:
        return dict(_cache)


def refresh_domains() -> None:
    from app.cp_helpers import make_client
    try:
        with make_client() as client:
            domains = client.get_domains()
        with _lock:
            _cache.update({
                "domains": domains,
                "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "ok",
            })
        app_log("INFO", "domain_cache", "Domain list refreshed", count=len(domains))
    except Exception as exc:
        app_log("ERROR", "domain_cache", "Failed to refresh domain list", exc=str(exc))
        with _lock:
            _cache["status"] = "error"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_cp_helpers.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/cp_helpers.py app/domain_cache.py tests/test_cp_helpers.py
git commit -m "feat: add HA failover client context manager and domain list cache

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: `app/host_metrics.py` — SQLite metrics store

**Files:**
- Create: `app/host_metrics.py`
- Create: `tests/test_host_metrics.py`

**Interfaces:**
- `init_db() -> None` — creates `summary_history` table if it does not exist
- `upsert_summary(date: str, gw_count: int, rule_count: int) -> None` — INSERT OR REPLACE
- `get_history(days: int = 30) -> list[dict]` — ordered by date ASC, last `days` rows

- [ ] **Step 1: Write failing tests**

Create `tests/test_host_metrics.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.host_metrics._DB_PATH", tmp_path / "metrics.db")
    from app.host_metrics import init_db
    init_db()


def test_upsert_and_retrieve():
    from app.host_metrics import upsert_summary, get_history
    upsert_summary("2026-01-01", 10, 500)
    rows = get_history(days=30)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["gw_count"] == 10
    assert rows[0]["rule_count"] == 500


def test_upsert_replaces_existing_row():
    from app.host_metrics import upsert_summary, get_history
    upsert_summary("2026-01-01", 10, 500)
    upsert_summary("2026-01-01", 12, 600)
    rows = get_history(days=30)
    assert len(rows) == 1
    assert rows[0]["gw_count"] == 12
    assert rows[0]["rule_count"] == 600


def test_get_history_limits_rows():
    from app.host_metrics import upsert_summary, get_history
    for i in range(35):
        upsert_summary(f"2026-01-{i + 1:02d}", i, i * 10)
    rows = get_history(days=30)
    assert len(rows) == 30


def test_get_history_ordered_asc():
    from app.host_metrics import upsert_summary, get_history
    upsert_summary("2026-01-03", 3, 30)
    upsert_summary("2026-01-01", 1, 10)
    upsert_summary("2026-01-02", 2, 20)
    rows = get_history(days=30)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


def test_get_history_empty():
    from app.host_metrics import get_history
    assert get_history() == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_host_metrics.py -v
```

Expected: `ImportError` — `app.host_metrics` does not exist yet.

- [ ] **Step 3: Create `app/host_metrics.py`**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "metrics.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS summary_history (
    date       TEXT PRIMARY KEY,
    gw_count   INTEGER NOT NULL,
    rule_count INTEGER NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_CREATE_SQL)


def upsert_summary(date: str, gw_count: int, rule_count: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO summary_history (date, gw_count, rule_count) VALUES (?, ?, ?)",
            (date, gw_count, rule_count),
        )


def get_history(days: int = 30) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date, gw_count, rule_count FROM summary_history "
            "ORDER BY date ASC LIMIT ?",
            (days,),
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_host_metrics.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/host_metrics.py tests/test_host_metrics.py
git commit -m "feat: add SQLite summary_history store for 30-day metric trends

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: `app/summary_job.py` — background summary job

**Files:**
- Create: `app/summary_job.py`
- Create: `tests/test_summary_job.py`

**Interfaces:**
- `run_summary_job() -> None` — iterates all domains, counts gateways + clusters + rules, writes to metrics.db and updates in-memory cache
- `get_summary_cache() -> dict` — returns copy of `{"gw_count": int, "rule_count": int, "last_updated": str|None}`

- [ ] **Step 1: Write failing tests**

Create `tests/test_summary_job.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.host_metrics._DB_PATH", tmp_path / "metrics.db")
    from app.host_metrics import init_db
    init_db()


def _make_mock_client(gw_count=2, cluster_count=1, package_names=None, rule_count=5):
    client = MagicMock()
    client.get_gateways.return_value = [{"name": f"gw{i}"} for i in range(gw_count)]
    client.get_clusters.return_value = [{"name": f"cl{i}"} for i in range(cluster_count)]
    pkgs = [{"name": p} for p in (package_names or ["Pkg1"])]
    client.get_packages.return_value = pkgs
    client.get_access_rulebase.return_value = [{"uid": f"r{i}"} for i in range(rule_count)]
    return client


def _mock_cm(mock_client):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_run_summary_job_updates_cache():
    mock_client = _make_mock_client(gw_count=3, cluster_count=1, rule_count=10)
    domain_data = {"domains": [{"name": "D1"}], "status": "ok"}
    with patch("app.summary_job.get_cached_domains", return_value=domain_data), \
         patch("app.summary_job.make_client", return_value=_mock_cm(mock_client)):
        from app.summary_job import run_summary_job, get_summary_cache
        run_summary_job()
    cache = get_summary_cache()
    assert cache["gw_count"] == 4
    assert cache["rule_count"] == 10
    assert cache["last_updated"] is not None


def test_get_summary_cache_returns_copy():
    from app.summary_job import get_summary_cache
    c1 = get_summary_cache()
    c2 = get_summary_cache()
    c1["gw_count"] = 9999
    assert c2["gw_count"] != 9999


def test_run_summary_job_writes_to_db():
    mock_client = _make_mock_client(gw_count=2, cluster_count=0, rule_count=7)
    domain_data = {"domains": [{"name": "D1"}], "status": "ok"}
    with patch("app.summary_job.get_cached_domains", return_value=domain_data), \
         patch("app.summary_job.make_client", return_value=_mock_cm(mock_client)):
        from app.summary_job import run_summary_job
        run_summary_job()
    from app.host_metrics import get_history
    rows = get_history()
    assert len(rows) == 1
    assert rows[0]["gw_count"] == 2


def test_run_summary_job_handles_no_domains():
    domain_data = {"domains": [], "status": "ok"}
    with patch("app.summary_job.get_cached_domains", return_value=domain_data):
        from app.summary_job import run_summary_job, get_summary_cache
        run_summary_job()
    assert get_summary_cache()["gw_count"] == 0


def test_run_summary_job_handles_domain_error():
    domain_data = {"domains": [{"name": "D1"}], "status": "ok"}
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("MDS down")
    with patch("app.summary_job.get_cached_domains", return_value=domain_data), \
         patch("app.summary_job.make_client", return_value=bad_cm):
        from app.summary_job import run_summary_job
        run_summary_job()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_summary_job.py -v
```

Expected: `ImportError` — `app.summary_job` does not exist yet.

- [ ] **Step 3: Create `app/summary_job.py`**

```python
from __future__ import annotations

import threading
from datetime import date, datetime, timezone

from app.app_logger import app_log

_lock = threading.Lock()
_cache: dict = {"gw_count": 0, "rule_count": 0, "last_updated": None}


def get_summary_cache() -> dict:
    with _lock:
        return dict(_cache)


def run_summary_job() -> None:
    from app.cp_helpers import make_client
    from app.domain_cache import get_cached_domains
    from app.host_metrics import upsert_summary

    app_log("INFO", "summary_job", "Starting summary collection")
    domains = get_cached_domains().get("domains", [])
    total_gw = 0
    total_rules = 0

    for domain in domains:
        domain_name = domain.get("name", "")
        try:
            with make_client(domain=domain_name) as client:
                total_gw += len(client.get_gateways()) + len(client.get_clusters())
                for pkg in client.get_packages():
                    total_rules += len(client.get_access_rulebase(pkg["name"]))
        except Exception as exc:
            app_log("WARN", "summary_job", "Failed to collect from domain",
                    domain=domain_name, exc=str(exc))

    try:
        upsert_summary(date.today().isoformat(), total_gw, total_rules)
    except Exception as exc:
        app_log("ERROR", "summary_job", "Failed to write to metrics DB", exc=str(exc))

    with _lock:
        _cache.update({
            "gw_count": total_gw,
            "rule_count": total_rules,
            "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    app_log("INFO", "summary_job", "Summary collection complete",
            gw_count=total_gw, rule_count=total_rules)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_summary_job.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/summary_job.py tests/test_summary_job.py
git commit -m "feat: add background summary job for gateway and rule counts

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: `app/infra_health_cache.py` — infrastructure health cache

**Files:**
- Create: `app/infra_health_cache.py`
- Create: `tests/test_infra_health_cache.py`

**Interfaces:**
- `refresh_infra_health() -> None` — polls MDS (via CP API) and MLS (TCP connect port 443), updates in-memory cache
- `get_infra_health() -> dict` — returns `{"servers": [...], "last_updated": str|None}`

Each server entry shape:
```python
{
    "label": str,
    "host": str,
    "type": "MDS" | "MLS",
    "status": "healthy" | "unreachable" | "degraded",
    "hostname": str | None,
    "version": str | None,
    "serial": str | None,
    "ha_role": str | None,
    "cpu_pct": float | None,
    "mem_pct": float | None,
}
```

- [ ] **Step 1: Write failing tests**

Create `tests/test_infra_health_cache.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


def _patch_config(monkeypatch):
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "10.0.0.1")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY", "10.0.0.2")
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY_LABEL", "MDS Primary")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY_LABEL", "MDS Secondary")
    monkeypatch.setattr("app.config.Config.CP_MLS_1", "10.0.1.1")
    monkeypatch.setattr("app.config.Config.CP_MLS_2", "10.0.1.2")
    monkeypatch.setattr("app.config.Config.CP_MLS_1_LABEL", "MLS 1")
    monkeypatch.setattr("app.config.Config.CP_MLS_2_LABEL", "MLS 2")
    monkeypatch.setattr("app.config.Config.CP_API_KEY", "key")
    monkeypatch.setattr("app.config.Config.CP_VERIFY_SSL", False)
    monkeypatch.setattr("app.config.Config.CP_TIMEOUT", 10)


def _mds_cm(version="R81.20"):
    client = MagicMock()
    client.get_api_version.return_value = {"current-version": version, "success": True}
    client.call.return_value = {"success": True}
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, client


def test_get_infra_health_initial_state():
    from app.infra_health_cache import get_infra_health
    result = get_infra_health()
    assert "servers" in result
    assert "last_updated" in result


def test_mds_healthy_on_successful_connect(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm("R81.20")
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection"):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mds = [s for s in get_infra_health()["servers"] if s["type"] == "MDS"]
    assert len(mds) == 2
    assert all(s["status"] == "healthy" for s in mds)
    assert mds[0]["version"] == "R81.20"


def test_mds_unreachable_on_connection_error(monkeypatch):
    _patch_config(monkeypatch)
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("down")
    with patch("app.infra_health_cache.make_client", return_value=bad_cm), \
         patch("app.infra_health_cache.socket.create_connection"):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mds = [s for s in get_infra_health()["servers"] if s["type"] == "MDS"]
    assert all(s["status"] == "unreachable" for s in mds)


def test_mls_healthy_on_tcp_connect(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm()
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection", return_value=MagicMock()):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mls = [s for s in get_infra_health()["servers"] if s["type"] == "MLS"]
    assert all(s["status"] == "healthy" for s in mls)


def test_mls_unreachable_on_tcp_failure(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm()
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection",
               side_effect=OSError("refused")):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mls = [s for s in get_infra_health()["servers"] if s["type"] == "MLS"]
    assert all(s["status"] == "unreachable" for s in mls)


def test_server_entry_has_required_fields(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm()
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection"):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    for s in get_infra_health()["servers"]:
        for field in ("label", "host", "type", "status", "hostname",
                      "version", "serial", "ha_role"):
            assert field in s, f"Missing field {field!r}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_infra_health_cache.py -v
```

Expected: `ImportError` — module not yet created.

- [ ] **Step 3: Create `app/infra_health_cache.py`**

```python
from __future__ import annotations

import socket
import threading
from datetime import datetime, timezone

from app.app_logger import app_log

_lock = threading.Lock()
_cache: dict = {"servers": [], "last_updated": None}


def get_infra_health() -> dict:
    with _lock:
        return {"servers": list(_cache["servers"]), "last_updated": _cache["last_updated"]}


def _poll_mds(host: str, label: str) -> dict:
    from app.cp_helpers import make_client
    entry: dict = {
        "label": label, "host": host, "type": "MDS", "status": "unreachable",
        "hostname": None, "version": None, "serial": None, "ha_role": None,
        "cpu_pct": None, "mem_pct": None,
    }
    try:
        with make_client() as client:
            ver = client.get_api_version()
            entry["version"] = ver.get("current-version")
            try:
                info = client.call("show-mdss", {})
                entry["ha_role"] = info.get("ha-role")
                entry["hostname"] = info.get("name")
            except Exception:
                pass
            entry["status"] = "healthy"
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
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_infra_health_cache.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infra_health_cache.py tests/test_infra_health_cache.py
git commit -m "feat: add infrastructure health cache for MDS and MLS polling

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: `app/routes/dashboard_routes.py` — dashboard blueprint + API

**Files:**
- Create: `app/routes/dashboard_routes.py`
- Create: `tests/test_dashboard_routes.py`
- Modify: `app/__init__.py` — add `"app.routes.dashboard_routes"` to `_BLUEPRINT_MODULES`

**Interfaces (Blueprint `dashboard`, url_prefix `/`):**
- `GET  /dashboard` — renders `dashboard.html` `[login_required]`
- `GET  /api/dashboard/summary` — `{"gw_count", "rule_count", "last_updated", "history": [...]}`
- `GET  /api/dashboard/health` — `{"servers": [...], "last_updated"}`
- `POST /api/dashboard/refresh` — fires `run_summary_job` in a thread, returns 202
- `POST /api/dashboard/refresh-health` — fires `refresh_infra_health` in a thread, returns 202

The blueprint self-registers "dashboard" in the nav registry on import.

- [ ] **Step 1: Write failing tests**

Create `tests/test_dashboard_routes.py`:

```python
import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def dashboard_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = ["dashboard"]
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
        sess["_csrf_token"] = "test-csrf-token"
    return client


def _csrf(client):
    with client.session_transaction() as sess:
        return sess.get("_csrf_token", "test-csrf-token")


def test_dashboard_page_requires_login(client):
    r = client.get("/dashboard")
    assert r.status_code in (302, 401)


def test_dashboard_page_loads(dashboard_client):
    r = dashboard_client.get("/dashboard")
    assert r.status_code == 200


def test_summary_api_returns_expected_keys(dashboard_client):
    r = dashboard_client.get("/api/dashboard/summary")
    assert r.status_code == 200
    data = r.get_json()
    for key in ("gw_count", "rule_count", "history"):
        assert key in data
    assert isinstance(data["history"], list)


def test_health_api_returns_expected_keys(dashboard_client):
    r = dashboard_client.get("/api/dashboard/health")
    assert r.status_code == 200
    data = r.get_json()
    assert "servers" in data
    assert isinstance(data["servers"], list)


def test_refresh_returns_202(dashboard_client):
    token = _csrf(dashboard_client)
    with patch("app.routes.dashboard_routes.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        r = dashboard_client.post("/api/dashboard/refresh",
                                  headers={"X-CSRF-Token": token})
    assert r.status_code == 202


def test_refresh_health_returns_202(dashboard_client):
    token = _csrf(dashboard_client)
    with patch("app.routes.dashboard_routes.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        r = dashboard_client.post("/api/dashboard/refresh-health",
                                  headers={"X-CSRF-Token": token})
    assert r.status_code == 202
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_dashboard_routes.py -v
```

Expected: `ImportError` or 404 — dashboard routes not yet registered.

- [ ] **Step 3: Create `app/routes/dashboard_routes.py`**

```python
import threading

from flask import Blueprint, jsonify, render_template

from app import registry
from app.decorators import login_required
from app.host_metrics import get_history
from app.infra_health_cache import get_infra_health
from app.summary_job import get_summary_cache

registry.register("dashboard", "Dashboard", "dashboard.dashboard_page", icon="&#9774;")

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
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
    return jsonify({"ok": True, "message": "Summary refresh started"}), 202


@bp.route("/api/dashboard/refresh-health", methods=["POST"])
@login_required
def api_refresh_health():
    from app.infra_health_cache import refresh_infra_health
    t = threading.Thread(target=refresh_infra_health, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Health refresh started"}), 202
```

- [ ] **Step 4: Add `"app.routes.dashboard_routes"` to `_BLUEPRINT_MODULES` in `app/__init__.py`**

Edit `app/__init__.py` — update `_BLUEPRINT_MODULES`:

```python
_BLUEPRINT_MODULES = [
    "app.routes.auth_routes",
    "app.routes.admin_routes",
    "app.routes.dashboard_routes",
]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_dashboard_routes.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/routes/dashboard_routes.py app/__init__.py tests/test_dashboard_routes.py
git commit -m "feat: add dashboard blueprint with summary and health API endpoints

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Dashboard template + `dashboard.js` + APScheduler wiring

**Files:**
- Create: `app/templates/dashboard.html`
- Create: `app/static/js/dashboard.js`
- Modify: `app/__init__.py` — add APScheduler wiring inside `create_app()`
- Modify: `app/static/css/app.css` — add sparkline canvas + auto-refresh selector styles

No automated tests for the template or JS. The full suite (`uv run pytest -v`) is the regression guard. APScheduler does not start when `app.testing` is `True`.

- [ ] **Step 1: Create `app/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Dashboard — check.health{% endblock %}

{% block content %}
<div class="page-header">
  <h2>&#9774; Dashboard</h2>
  <button class="btn btn-sm btn-secondary" id="refreshSummaryBtn">&#8635; Refresh Counts</button>
</div>

<!-- ── Summary tiles ─────────────────────────────────────────────────────── -->
<div class="summary-tile-row" id="summaryTiles">
  <div class="summary-tile">
    <div class="tile-value" id="gwCount">—</div>
    <div class="tile-label">Managed Gateways &amp; Clusters</div>
  </div>
  <div class="summary-tile">
    <div class="tile-value" id="ruleCount">—</div>
    <div class="tile-label">Policy Rules Managed</div>
  </div>
</div>
<p class="text-muted" id="summaryUpdated"
   style="font-size:.78rem;margin-top:-.5rem;margin-bottom:1.25rem"></p>

<!-- ── Sparklines ────────────────────────────────────────────────────────── -->
<div style="display:flex;gap:1rem;margin-bottom:1.5rem">
  <div class="card" style="flex:1">
    <div class="chart-label">Managed Gateways — 30 Days</div>
    <canvas id="gwChart" height="60" style="width:100%;display:block"></canvas>
  </div>
  <div class="card" style="flex:1">
    <div class="chart-label">Policy Rules — 30 Days</div>
    <canvas id="ruleChart" height="60" style="width:100%;display:block"></canvas>
  </div>
</div>

<!-- ── Infrastructure Health ─────────────────────────────────────────────── -->
<div class="page-header" style="margin-bottom:.75rem">
  <h3 style="margin:0;font-size:1rem;font-weight:600">Infrastructure Health</h3>
  <div class="d-flex gap-2" style="align-items:center">
    <span class="text-muted" style="font-size:.78rem" id="healthUpdated"></span>
    <select id="autoRefreshSelect" class="form-select" style="width:auto;font-size:.8rem">
      <option value="0">No auto-refresh</option>
      <option value="5">Every 5 min</option>
      <option value="15" selected>Every 15 min</option>
      <option value="30">Every 30 min</option>
    </select>
    <button class="btn btn-sm btn-secondary" id="refreshHealthBtn">&#8635; Refresh Health</button>
  </div>
</div>
<div id="healthCards"></div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/dashboard.js') }}?v=1"></script>
{% endblock %}
```

- [ ] **Step 2: Create `app/static/js/dashboard.js`**

```javascript
const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

// ── Summary ───────────────────────────────────────────────────────────────
async function loadSummary() {
  const r = await fetch('/api/dashboard/summary');
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById('gwCount').textContent = data.gw_count.toLocaleString();
  document.getElementById('ruleCount').textContent = data.rule_count.toLocaleString();
  document.getElementById('summaryUpdated').textContent =
    data.last_updated ? 'Counts as of ' + data.last_updated : '';
  drawSparkline('gwChart', data.history.map(h => h.gw_count), '#0d6efd');
  drawSparkline('ruleChart', data.history.map(h => h.rule_count), '#198754');
}

document.getElementById('refreshSummaryBtn').addEventListener('click', async () => {
  document.getElementById('refreshSummaryBtn').disabled = true;
  await fetch('/api/dashboard/refresh', { method: 'POST', headers: { 'X-CSRF-Token': CSRF } });
  setTimeout(() => {
    loadSummary();
    document.getElementById('refreshSummaryBtn').disabled = false;
  }, 2000);
});

// ── Sparkline (vanilla Canvas) ────────────────────────────────────────────
function drawSparkline(canvasId, values, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.offsetWidth;
  const h = canvas.offsetHeight || 60;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  if (!values || values.length < 2) {
    ctx.fillStyle = '#ccc';
    ctx.font = '11px system-ui';
    ctx.fillText('No data', 8, h / 2 + 4);
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pad = 4;
  const xStep = (w - pad * 2) / (values.length - 1);
  const yScale = (h - pad * 2) / range;
  const pts = values.map((v, i) => ({
    x: pad + i * xStep,
    y: h - pad - (v - min) * yScale,
  }));

  ctx.beginPath();
  ctx.moveTo(pts[0].x, h - pad);
  ctx.lineTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length - 1].x, h - pad);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + '55');
  grad.addColorStop(1, color + '08');
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ── Health cards ──────────────────────────────────────────────────────────
async function loadHealth() {
  const r = await fetch('/api/dashboard/health');
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById('healthUpdated').textContent =
    data.last_updated ? 'Updated ' + data.last_updated : '';
  const LABEL = {
    healthy: '&#9679; Healthy',
    unreachable: '&#9679; Unreachable',
    degraded: '&#9679; Degraded',
  };
  const container = document.getElementById('healthCards');
  container.innerHTML = (data.servers || []).map(s => {
    const cls = s.status === 'healthy' ? 'healthy'
              : s.status === 'degraded' ? 'degraded' : 'unhealthy';
    return `
      <div class="health-card ${cls}">
        <div class="health-card-name">
          <strong>${esc(s.label)}</strong>
          <span class="health-ip">${esc(s.host)}</span>
          <span class="badge badge-secondary" style="font-size:.7rem">${esc(s.type)}</span>
        </div>
        <div class="health-card-meta">
          <div class="health-meta-item">
            <label>Status</label>
            <span>${LABEL[s.status] || esc(s.status)}</span>
          </div>
          <div class="health-meta-item">
            <label>Hostname</label><span>${esc(s.hostname || 'N/A')}</span>
          </div>
          <div class="health-meta-item">
            <label>Version</label><span>${esc(s.version || 'N/A')}</span>
          </div>
          <div class="health-meta-item">
            <label>HA Role</label><span>${esc(s.ha_role || 'N/A')}</span>
          </div>
          ${s.cpu_pct != null
            ? `<div class="health-meta-item"><label>CPU</label><span>${s.cpu_pct}%</span></div>`
            : ''}
          ${s.mem_pct != null
            ? `<div class="health-meta-item"><label>MEM</label><span>${s.mem_pct}%</span></div>`
            : ''}
        </div>
      </div>`;
  }).join('') ||
    '<p class="text-muted" style="font-size:.875rem">No health data yet — click Refresh Health.</p>';
}

document.getElementById('refreshHealthBtn').addEventListener('click', async () => {
  document.getElementById('refreshHealthBtn').disabled = true;
  await fetch('/api/dashboard/refresh-health',
    { method: 'POST', headers: { 'X-CSRF-Token': CSRF } });
  setTimeout(() => {
    loadHealth();
    document.getElementById('refreshHealthBtn').disabled = false;
  }, 2000);
});

// ── Auto-refresh ──────────────────────────────────────────────────────────
let _autoTimer = null;
function setAutoRefresh(minutes) {
  clearInterval(_autoTimer);
  if (minutes > 0) _autoTimer = setInterval(loadHealth, minutes * 60 * 1000);
}
document.getElementById('autoRefreshSelect').addEventListener('change', function () {
  setAutoRefresh(parseInt(this.value, 10));
});

// ── Helpers ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────
loadSummary();
loadHealth();
setAutoRefresh(15);
```

- [ ] **Step 3: Add APScheduler wiring to `app/__init__.py`**

Inside `create_app()`, after the `_groups.KNOWN_TABS.update(...)` line and before `return app`, add:

```python
    if not app.testing:
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.host_metrics import init_db
        from app.summary_job import run_summary_job
        from app.infra_health_cache import refresh_infra_health
        from app.domain_cache import refresh_domains

        init_db()

        scheduler = BackgroundScheduler()
        scheduler.add_job(run_summary_job,     "interval", minutes=60, id="summary_job")
        scheduler.add_job(refresh_infra_health, "interval", minutes=15, id="infra_health")
        scheduler.add_job(refresh_domains,      "interval", minutes=30, id="domain_cache")
        scheduler.start()

        refresh_domains()
        refresh_infra_health()
        run_summary_job()
```

- [ ] **Step 4: Append sparkline + selector styles to `app/static/css/app.css`**

```css
/* ── Sparkline chart label ──────────────────────────────────────────────── */
.chart-label {
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: .5rem;
}

/* ── Canvas baseline ────────────────────────────────────────────────────── */
canvas { display: block; }
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS (APScheduler block is skipped when `app.testing` is `True`).

- [ ] **Step 6: Manual smoke test**

```bash
uv run flask --app app run --debug
```

Open http://127.0.0.1:5000 and verify:
- Login redirects to `/dashboard`
- Dashboard renders: two summary tiles (showing "0" or "—"), two canvas elements, infrastructure health section
- "Dashboard" tab appears in navbar
- Refresh Counts and Refresh Health buttons respond
- Admin tab still works
- Logout works

- [ ] **Step 7: Commit**

```bash
git add app/templates/dashboard.html app/static/js/dashboard.js \
        app/__init__.py app/static/css/app.css
git commit -m "feat: add dashboard template, sparklines, health cards, and APScheduler wiring

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Plan Complete

**What this plan delivers:**
- `CPClient` — full CP Management API wrapper with automatic pagination and context-manager session lifecycle
- `make_client()` — HA failover context manager (primary → secondary → `ConnectionError`)
- `domain_cache` — in-memory domain list refreshed every 30 min
- `host_metrics` — SQLite `summary_history` table with 30-day trend data
- `summary_job` — hourly background job counting gateways, clusters, and policy rules across all domains
- `infra_health_cache` — 15-min polling of MDS (via API) and MLS (via TCP socket) servers
- Dashboard tab — summary tiles, 30-day sparkline charts, infrastructure health cards; all data served from in-memory caches so no CP API call blocks a request

**Next plans:**
- **Plan 3:** Firewalls tab (domain selector, gateway + cluster table with details modal) + Rule Review tab (policy rules, object lookup, interface lookup, NAT lookup)
