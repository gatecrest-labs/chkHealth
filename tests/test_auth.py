import pytest


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


# ── Rate limiting (_is_rate_limited / _record_failure / _clear_failures) ─────

@pytest.fixture(autouse=False)
def clean_rate_state():
    import app.routes.auth_routes as ar
    ar._ip_failures.clear()
    ar._user_failures.clear()
    yield
    ar._ip_failures.clear()
    ar._user_failures.clear()


def test_no_limit_initially(clean_rate_state):
    from app.routes.auth_routes import _is_rate_limited
    assert _is_rate_limited("1.2.3.4", "alice") is False


def test_ip_blocked_after_max_failures(clean_rate_state):
    from app.routes.auth_routes import _is_rate_limited, _record_failure, _IP_MAX
    for _ in range(_IP_MAX):
        _record_failure("1.2.3.4", "alice")
    assert _is_rate_limited("1.2.3.4", "alice") is True


def test_user_blocked_after_max_failures(clean_rate_state):
    from app.routes.auth_routes import _is_rate_limited, _record_failure, _USER_MAX
    for _ in range(_USER_MAX):
        _record_failure("1.2.3.4", "alice")
    # Different IP — still blocked by username
    assert _is_rate_limited("5.6.7.8", "alice") is True


def test_block_is_per_ip_not_global(clean_rate_state):
    from app.routes.auth_routes import _is_rate_limited, _record_failure, _IP_MAX
    for _ in range(_IP_MAX):
        _record_failure("1.2.3.4", "alice")
    # Different IP, different user — not blocked
    assert _is_rate_limited("9.9.9.9", "bob") is False


def test_clear_failures_unblocks_ip_and_user(clean_rate_state):
    from app.routes.auth_routes import _is_rate_limited, _record_failure, _clear_failures, _IP_MAX
    for _ in range(_IP_MAX):
        _record_failure("1.2.3.4", "alice")
    assert _is_rate_limited("1.2.3.4", "alice") is True
    _clear_failures("1.2.3.4", "alice")
    assert _is_rate_limited("1.2.3.4", "alice") is False


def test_username_normalized_before_tracking(clean_rate_state):
    from app.routes.auth_routes import _is_rate_limited, _record_failure, _USER_MAX
    # Failures recorded with mixed case should block the lowercase variant too
    for _ in range(_USER_MAX):
        _record_failure("1.2.3.4", "Alice")
    assert _is_rate_limited("1.2.3.4", "alice") is True
    assert _is_rate_limited("1.2.3.4", "ALICE") is True


# ── Remote-provider dispatch ──────────────────────────────────────────────

def test_radius_dispatch_success(users_file, monkeypatch):
    """When RADIUS is enabled and succeeds, return its result without touching users.json."""
    import app.config as cfg
    monkeypatch.setattr(cfg.Config, "RADIUS_ENABLED", True)
    monkeypatch.setattr(cfg.Config, "LDAP_ENABLED", False)
    monkeypatch.setattr(cfg.Config, "TACACS_ENABLED", False)
    monkeypatch.setattr(cfg.Config, "RADIUS_HOST", "10.0.0.1")
    monkeypatch.setattr(cfg.Config, "RADIUS_PORT", 1812)
    monkeypatch.setattr(cfg.Config, "RADIUS_SECRET", "secret")
    monkeypatch.setattr(cfg.Config, "RADIUS_TIMEOUT", 5)
    monkeypatch.setattr(cfg.Config, "RADIUS_GROUP_ADMIN", "admins")
    monkeypatch.setattr(cfg.Config, "RADIUS_GROUP_VIEWER", "viewers")
    monkeypatch.setattr(cfg.Config, "RADIUS_HOST_2", "")
    monkeypatch.setattr(cfg.Config, "RADIUS_PORT_2", 1812)

    from unittest.mock import patch
    with patch("app.auth.radius_auth") as mock_radius:
        mock_radius.authenticate.return_value = {"role": "admin", "ad_groups": ["admins"]}
        from app.auth import authenticate
        result = authenticate("remoteuser", "pass")

    assert result == ("admin", ["admins"])


def test_remote_returns_none_falls_back_to_local(users_file, monkeypatch):
    """When remote returns None, local bcrypt still works."""
    import app.config as cfg
    from app.auth import add_user
    add_user("localuser", "localpass", "viewer")

    monkeypatch.setattr(cfg.Config, "RADIUS_ENABLED", True)
    monkeypatch.setattr(cfg.Config, "LDAP_ENABLED", False)
    monkeypatch.setattr(cfg.Config, "TACACS_ENABLED", False)
    monkeypatch.setattr(cfg.Config, "RADIUS_HOST", "10.0.0.1")
    monkeypatch.setattr(cfg.Config, "RADIUS_PORT", 1812)
    monkeypatch.setattr(cfg.Config, "RADIUS_SECRET", "secret")
    monkeypatch.setattr(cfg.Config, "RADIUS_TIMEOUT", 5)
    monkeypatch.setattr(cfg.Config, "RADIUS_GROUP_ADMIN", "")
    monkeypatch.setattr(cfg.Config, "RADIUS_GROUP_VIEWER", "")
    monkeypatch.setattr(cfg.Config, "RADIUS_HOST_2", "")
    monkeypatch.setattr(cfg.Config, "RADIUS_PORT_2", 1812)

    from unittest.mock import patch
    with patch("app.auth.radius_auth") as mock_radius:
        mock_radius.authenticate.return_value = None
        from app.auth import authenticate
        result = authenticate("localuser", "localpass")

    assert result is not None
    role, ad_groups = result
    assert role == "viewer"
    assert ad_groups == []


def test_ldap_enabled_skips_tacacs(users_file, monkeypatch):
    """When LDAP is enabled, TACACS must NOT be called even if also enabled."""
    import app.config as cfg
    monkeypatch.setattr(cfg.Config, "LDAP_ENABLED", True)
    monkeypatch.setattr(cfg.Config, "TACACS_ENABLED", True)
    monkeypatch.setattr(cfg.Config, "RADIUS_ENABLED", False)
    monkeypatch.setattr(cfg.Config, "LDAP_SERVER", "ldaps://dc01")
    monkeypatch.setattr(cfg.Config, "LDAP_BASE_DN", "DC=corp,DC=com")
    monkeypatch.setattr(cfg.Config, "LDAP_BIND_USER", "svc@corp")
    monkeypatch.setattr(cfg.Config, "LDAP_BIND_PASSWORD", "svc-pass")
    monkeypatch.setattr(cfg.Config, "LDAP_USER_SEARCH", "(sAMAccountName={username})")
    monkeypatch.setattr(cfg.Config, "LDAP_GROUP_ADMIN", "admins")
    monkeypatch.setattr(cfg.Config, "LDAP_GROUP_VIEWER", "viewers")
    monkeypatch.setattr(cfg.Config, "LDAP_VERIFY_SSL", False)

    from unittest.mock import patch
    with patch("app.auth.ldap_auth") as mock_ldap, \
         patch("app.auth.tacacs_auth") as mock_tacacs:
        mock_ldap.authenticate.return_value = {"role": "viewer", "ad_groups": []}
        from app.auth import authenticate
        authenticate("alice", "pass")

    mock_ldap.authenticate.assert_called_once()
    mock_tacacs.authenticate.assert_not_called()
