from unittest.mock import MagicMock, patch


def _make_tacacs_client(auth_valid: bool, av_pairs: list[bytes], authz_valid: bool = True) -> MagicMock:
    """Return a mock TACACSClient with the given auth/authz outcomes."""
    client = MagicMock()

    auth_reply = MagicMock()
    auth_reply.valid = auth_valid
    client.authenticate.return_value = auth_reply

    authz_reply = MagicMock()
    authz_reply.valid = authz_valid
    authz_reply.arguments = av_pairs
    client.authorize.return_value = authz_reply

    return client


def test_tacacs_admin_priv_lvl():
    from app.tacacs_auth import authenticate

    mock_client = _make_tacacs_client(True, [b"priv-lvl=15", b"service=shell"])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "alice", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="15",
            group_admin="", group_viewer="",
        )

    assert result is not None
    assert result["role"] == "admin"
    assert "priv-lvl=15" in result["ad_groups"]


def test_tacacs_viewer_priv_lvl():
    from app.tacacs_auth import authenticate

    mock_client = _make_tacacs_client(True, [b"priv-lvl=1"])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "bob", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="15",
            group_admin="", group_viewer="",
        )

    assert result is not None
    assert result["role"] == "viewer"


def test_tacacs_missing_priv_lvl_defaults_to_viewer():
    from app.tacacs_auth import authenticate

    mock_client = _make_tacacs_client(True, [b"service=shell"])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "carol", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="15",
            group_admin="", group_viewer="",
        )

    assert result is not None
    assert result["role"] == "viewer"


def test_tacacs_admin_group_av_pair():
    from app.tacacs_auth import authenticate

    mock_client = _make_tacacs_client(True, [b"groups=net-admins"])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "alice", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="",
            group_admin="net-admins",
            group_viewer="net-viewers",
        )

    assert result is not None
    assert result["role"] == "admin"


def test_tacacs_viewer_group_av_pair():
    from app.tacacs_auth import authenticate

    mock_client = _make_tacacs_client(True, [b"groups=net-viewers"])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "bob", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="",
            group_admin="net-admins",
            group_viewer="net-viewers",
        )

    assert result is not None
    assert result["role"] == "viewer"


def test_tacacs_unmatched_group_av_pair_returns_none():
    from app.tacacs_auth import authenticate

    mock_client = _make_tacacs_client(True, [b"groups=other-group"])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "alice", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="",
            group_admin="net-admins",
            group_viewer="net-viewers",
        )

    assert result is None


def test_tacacs_group_prefix_not_escalated():
    """AV-pair group matching must use exact equality on the value, not substring of the whole pair."""
    from app.tacacs_auth import authenticate

    # group_admin="net-adm" is a prefix of "net-admins"; substring match would grant admin incorrectly
    mock_client = _make_tacacs_client(True, [b"groups=net-admins"])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "alice", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="",
            group_admin="net-adm",   # prefix, not exact
            group_viewer="net-viewers",
        )

    assert result is None


def test_tacacs_wrong_password_returns_none():
    from app.tacacs_auth import authenticate

    mock_client = _make_tacacs_client(False, [])

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "alice", "wrongpass",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="15",
            group_admin="", group_viewer="",
        )

    assert result is None


def test_tacacs_network_failure_returns_none():
    from app.tacacs_auth import authenticate

    mock_client = MagicMock()
    mock_client.authenticate.side_effect = OSError("connection refused")

    with patch("app.tacacs_auth.TACACSClient", return_value=mock_client):
        result = authenticate(
            "alice", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="15",
            group_admin="", group_viewer="",
        )

    assert result is None


def test_tacacs_falls_back_to_secondary():
    from app.tacacs_auth import authenticate

    call_count = {"n": 0}

    def client_factory(host, port, secret, timeout):
        call_count["n"] += 1
        client = MagicMock()
        if call_count["n"] == 1:
            client.authenticate.side_effect = OSError("primary down")
        else:
            auth_reply = MagicMock()
            auth_reply.valid = True
            client.authenticate.return_value = auth_reply
            authz_reply = MagicMock()
            authz_reply.valid = True
            authz_reply.arguments = [b"priv-lvl=15"]
            client.authorize.return_value = authz_reply
        return client

    with patch("app.tacacs_auth.TACACSClient", side_effect=client_factory):
        result = authenticate(
            "alice", "password",
            host="10.0.0.1", port=49,
            secret="tac-secret", timeout=5,
            priv_admin="15",
            group_admin="", group_viewer="",
            host2="10.0.0.2", port2=49,
        )

    assert result is not None
    assert result["role"] == "admin"
    assert call_count["n"] == 2
