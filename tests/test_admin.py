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


def test_cd_jobs_list_empty(admin_client, tmp_path, monkeypatch):
    import app.config_delta_scheduler as sched
    monkeypatch.setattr(sched, "_JOBS_PATH", tmp_path / "jobs.json")
    resp = admin_client.get("/admin/api/config-delta/jobs")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_cd_jobs_create_and_list(admin_client, tmp_path, monkeypatch):
    import app.config_delta_scheduler as sched
    monkeypatch.setattr(sched, "_JOBS_PATH", tmp_path / "jobs.json")
    payload = {
        "domain": "CORP", "days_of_week": ["MON", "WED"],
        "time": "06:00", "format": "csv", "email": "ops@x.com", "enabled": True,
    }
    resp = admin_client.post(
        "/admin/api/config-delta/jobs",
        json=payload,
        headers={"X-CSRF-Token": ""},
        content_type="application/json",
    )
    assert resp.status_code == 201
    jobs = admin_client.get("/admin/api/config-delta/jobs").get_json()
    assert len(jobs) == 1
    assert jobs[0]["domain"] == "CORP"


def test_cd_jobs_delete(admin_client, tmp_path, monkeypatch):
    import app.config_delta_scheduler as sched
    monkeypatch.setattr(sched, "_JOBS_PATH", tmp_path / "jobs.json")
    admin_client.post(
        "/admin/api/config-delta/jobs",
        json={"domain": "CORP", "days_of_week": [], "time": "06:00",
               "format": "csv", "email": "ops@x.com", "enabled": True},
        headers={"X-CSRF-Token": ""},
    )
    jobs = admin_client.get("/admin/api/config-delta/jobs").get_json()
    job_id = jobs[0]["id"]
    resp = admin_client.delete(
        f"/admin/api/config-delta/jobs/{job_id}",
        headers={"X-CSRF-Token": ""},
    )
    assert resp.status_code == 200
    assert admin_client.get("/admin/api/config-delta/jobs").get_json() == []


def test_rh_jobs_list_empty(admin_client, tmp_path, monkeypatch):
    import app.rule_hygiene_scheduler as rhs
    monkeypatch.setattr(rhs, "_JOBS_PATH", tmp_path / "rh_jobs.json")
    token = _csrf(admin_client)
    r = admin_client.get("/admin/api/hygiene-jobs")
    assert r.status_code == 200
    assert r.get_json() == []


def test_rh_jobs_create(admin_client, tmp_path, monkeypatch):
    import app.rule_hygiene_scheduler as rhs
    monkeypatch.setattr(rhs, "_JOBS_PATH", tmp_path / "rh_jobs.json")
    monkeypatch.setattr(rhs, "_scheduler", None)
    token = _csrf(admin_client)
    r = admin_client.post(
        "/admin/api/hygiene-jobs",
        json={
            "domain": "corp", "email": "a@b.com",
            "days_of_week": ["MON"], "time": "06:00",
            "checks": ["unnamed"], "format": "html",
            "enabled": True, "batch_size": 20, "include_unused_objects": False,
        },
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["domain"] == "corp"


def test_rh_jobs_delete(admin_client, tmp_path, monkeypatch):
    import app.rule_hygiene_scheduler as rhs
    monkeypatch.setattr(rhs, "_JOBS_PATH", tmp_path / "rh_jobs.json")
    monkeypatch.setattr(rhs, "_scheduler", None)
    token = _csrf(admin_client)
    create_r = admin_client.post(
        "/admin/api/hygiene-jobs",
        json={
            "domain": "corp", "email": "a@b.com",
            "days_of_week": ["MON"], "time": "06:00",
            "checks": [], "format": "html",
            "enabled": True, "batch_size": 20, "include_unused_objects": False,
        },
        headers={"X-CSRF-Token": token},
    )
    job_id = create_r.get_json()["id"]
    del_r = admin_client.delete(
        f"/admin/api/hygiene-jobs/{job_id}",
        headers={"X-CSRF-Token": token},
    )
    assert del_r.status_code == 200


def test_rh_jobs_delete_not_found(admin_client):
    token = _csrf(admin_client)
    r = admin_client.delete(
        "/admin/api/hygiene-jobs/nonexistent",
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 404
