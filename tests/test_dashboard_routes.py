import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.host_metrics._DB_PATH", tmp_path / "metrics.db")
    from app.host_metrics import init_db
    init_db()


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
