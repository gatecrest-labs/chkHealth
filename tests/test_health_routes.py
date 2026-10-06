import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-ok!")


@pytest.fixture
def client():
    from app import create_app
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-minimum-32-chars-ok!",
        "WTF_CSRF_ENABLED": False,
    })
    return app.test_client()


def test_healthz_returns_200(client):
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_returns_ok_json(client):
    response = client.get("/healthz")
    data = response.get_json()
    assert data == {"status": "ok"}


def test_healthz_no_auth_required(client):
    # No session — bare unauthenticated request must still return 200.
    # This mirrors what the ALB health checker sends.
    with client.session_transaction() as sess:
        sess.clear()
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_has_security_headers(client):
    response = client.get("/healthz")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"


def test_healthz_app_starts_without_data_files(tmp_path, monkeypatch):
    """App must start and /healthz must respond 200 even when the EFS
    mount at /app/data is empty (first boot scenario)."""
    import app.auth as auth_mod
    import app.groups as groups_mod
    import app.app_settings as settings_mod
    import app.host_metrics as metrics_mod

    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    monkeypatch.setattr(settings_mod, "_SETTINGS_PATH", tmp_path / "app_settings.json")
    monkeypatch.setattr(metrics_mod, "_DB_PATH", tmp_path / "metrics.db")

    from app import create_app
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-minimum-32-chars-ok!",
        "WTF_CSRF_ENABLED": False,
    })
    response = app.test_client().get("/healthz")
    assert response.status_code == 200
