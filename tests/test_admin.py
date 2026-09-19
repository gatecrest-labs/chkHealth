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
