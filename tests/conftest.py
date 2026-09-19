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
