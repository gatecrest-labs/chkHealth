import hashlib
import struct
from unittest.mock import MagicMock, patch


def _make_accept_reply(request_bytes: bytes, secret: bytes, filter_ids: list[str]) -> bytes:
    """Build a valid RADIUS Access-Accept reply that matches the given request."""
    identifier = request_bytes[1]
    req_auth = request_bytes[4:20]

    attrs = b""
    for group in filter_ids:
        val = group.encode("utf-8")
        attrs += bytes([11, len(val) + 2]) + val  # Filter-Id attr type=11

    length = 20 + len(attrs)
    resp_auth = hashlib.md5(
        bytes([2, identifier])
        + struct.pack("!H", length)
        + req_auth
        + attrs
        + secret
    ).digest()
    return struct.pack("!BBH16s", 2, identifier, length, resp_auth) + attrs


def _make_reject_reply(request_bytes: bytes, secret: bytes) -> bytes:
    """Build a valid RADIUS Access-Reject reply."""
    identifier = request_bytes[1]
    req_auth = request_bytes[4:20]
    length = 20
    resp_auth = hashlib.md5(
        bytes([3, identifier])
        + struct.pack("!H", length)
        + req_auth
        + secret
    ).digest()
    return struct.pack("!BBH16s", 3, identifier, length, resp_auth)


def _mock_socket_returning(reply_builder):
    """Return a context-manager mock socket that calls reply_builder(sent_bytes) to craft the reply."""
    captured = {}

    mock_sock = MagicMock()

    def fake_sendto(data, addr):
        captured["sent"] = data
        captured["addr"] = addr

    def fake_recvfrom(bufsize):
        reply = reply_builder(captured["sent"])
        return reply, captured["addr"]

    mock_sock.sendto.side_effect = fake_sendto
    mock_sock.recvfrom.side_effect = fake_recvfrom
    mock_sock.__enter__ = lambda s: s
    mock_sock.__exit__ = MagicMock(return_value=False)
    return mock_sock


SECRET = "test-shared-secret"
SECRET_B = SECRET.encode("utf-8")


def test_radius_authenticate_admin():
    from app.radius_auth import authenticate

    mock_sock = _mock_socket_returning(
        lambda req: _make_accept_reply(req, SECRET_B, ["network-admins"])
    )
    with patch("app.radius_auth.socket.socket", return_value=mock_sock):
        result = authenticate(
            "alice", "password",
            host="127.0.0.1", port=1812,
            secret=SECRET, timeout=5,
            group_admin="network-admins", group_viewer="network-viewers",
        )

    assert result is not None
    assert result["role"] == "admin"
    assert "network-admins" in result["ad_groups"]


def test_radius_authenticate_viewer():
    from app.radius_auth import authenticate

    mock_sock = _mock_socket_returning(
        lambda req: _make_accept_reply(req, SECRET_B, ["network-viewers"])
    )
    with patch("app.radius_auth.socket.socket", return_value=mock_sock):
        result = authenticate(
            "bob", "password",
            host="127.0.0.1", port=1812,
            secret=SECRET, timeout=5,
            group_admin="network-admins", group_viewer="network-viewers",
        )

    assert result is not None
    assert result["role"] == "viewer"


def test_radius_reject_returns_none():
    from app.radius_auth import authenticate

    mock_sock = _mock_socket_returning(
        lambda req: _make_reject_reply(req, SECRET_B)
    )
    with patch("app.radius_auth.socket.socket", return_value=mock_sock):
        result = authenticate(
            "alice", "wrongpass",
            host="127.0.0.1", port=1812,
            secret=SECRET, timeout=5,
            group_admin="network-admins", group_viewer="network-viewers",
        )

    assert result is None


def test_radius_unmatched_groups_returns_none():
    from app.radius_auth import authenticate

    mock_sock = _mock_socket_returning(
        lambda req: _make_accept_reply(req, SECRET_B, ["some-other-group"])
    )
    with patch("app.radius_auth.socket.socket", return_value=mock_sock):
        result = authenticate(
            "alice", "password",
            host="127.0.0.1", port=1812,
            secret=SECRET, timeout=5,
            group_admin="network-admins", group_viewer="network-viewers",
        )

    assert result is None


def test_radius_no_group_attrs_defaults_to_viewer():
    from app.radius_auth import authenticate

    mock_sock = _mock_socket_returning(
        lambda req: _make_accept_reply(req, SECRET_B, [])
    )
    with patch("app.radius_auth.socket.socket", return_value=mock_sock):
        result = authenticate(
            "alice", "password",
            host="127.0.0.1", port=1812,
            secret=SECRET, timeout=5,
            group_admin="", group_viewer="",
        )

    assert result is not None
    assert result["role"] == "viewer"
    assert result["ad_groups"] == []


def test_radius_network_failure_returns_none():
    from app.radius_auth import authenticate

    mock_sock = MagicMock()
    mock_sock.sendto.side_effect = OSError("connection refused")
    mock_sock.__enter__ = lambda s: s
    mock_sock.__exit__ = MagicMock(return_value=False)

    with patch("app.radius_auth.socket.socket", return_value=mock_sock):
        result = authenticate(
            "alice", "password",
            host="127.0.0.1", port=1812,
            secret=SECRET, timeout=5,
            group_admin="network-admins", group_viewer="network-viewers",
        )

    assert result is None


def test_radius_falls_back_to_secondary_server():
    from app.radius_auth import authenticate

    call_count = {"n": 0}

    def sock_factory(*args, **kwargs):
        call_count["n"] += 1
        sock = MagicMock()
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        if call_count["n"] == 1:
            sock.sendto.side_effect = OSError("timeout")
        else:
            captured = {}

            def sendto(data, addr):
                captured["sent"] = data
                captured["addr"] = addr

            def recvfrom(n):
                return _make_accept_reply(captured["sent"], SECRET_B, ["network-viewers"]), captured["addr"]

            sock.sendto.side_effect = sendto
            sock.recvfrom.side_effect = recvfrom
        return sock

    with patch("app.radius_auth.socket.socket", sock_factory):
        result = authenticate(
            "alice", "password",
            host="10.0.0.1", port=1812,
            secret=SECRET, timeout=5,
            group_admin="network-admins", group_viewer="network-viewers",
            host2="10.0.0.2", port2=1812,
        )

    assert result is not None
    assert result["role"] == "viewer"
