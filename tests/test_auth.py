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
