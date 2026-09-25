import pytest
import time
from unittest.mock import patch


@pytest.fixture
def admin_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    c = app_ctx.test_client()
    with c.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = ["config_delta"]
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
    return c


def test_config_delta_page_requires_login(client):
    resp = client.get("/config-delta")
    assert resp.status_code in (302, 401)


def test_config_delta_page_renders_for_admin(admin_client):
    resp = admin_client.get("/config-delta")
    assert resp.status_code == 200


def test_api_domains_returns_list(admin_client):
    with patch("app.routes.config_delta_routes.get_cached_domains",
               return_value={"domains": [{"name": "CORP"}], "status": "ok"}):
        resp = admin_client.get("/api/config-delta/domains")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "domains" in data


def test_api_gateways_returns_cached(admin_client):
    fake_gws = [{"name": "GW-01", "ip": "10.0.0.1",
                 "policy_package": "P", "install_status": "insync"}]
    with patch("app.routes.config_delta_routes.get_cached_gateways",
               return_value={"gateways": fake_gws, "status": "ok", "last_updated": None}):
        resp = admin_client.get("/api/config-delta/domains/CORP/gateways")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["gateways"] == fake_gws


def test_api_start_changes_task_returns_task_id(admin_client):
    with patch("app.routes.config_delta_routes._launch_changes_task",
               return_value="fake-uuid"):
        resp = admin_client.post(
            "/api/config-delta/domains/CORP/gateway/GW-01/changes",
            headers={"X-CSRF-Token": ""},
        )
    assert resp.status_code == 202
    assert "task_id" in resp.get_json()


def test_api_task_returns_404_for_unknown_id(admin_client):
    resp = admin_client.get("/api/config-delta/task/nonexistent-id")
    assert resp.status_code == 404
