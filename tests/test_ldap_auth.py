from unittest.mock import MagicMock, patch
from ldap3.core.exceptions import LDAPBindError


def _make_mock_entry(dn: str, member_of: list[str]) -> MagicMock:
    entry = MagicMock()
    entry.entry_dn = dn
    entry.__contains__ = lambda self, item: item == "memberOf" and bool(member_of)
    entry.memberOf = member_of
    return entry


def test_ldap_authenticate_admin():
    from app.ldap_auth import authenticate

    entry = _make_mock_entry(
        "CN=alice,OU=Users,DC=corp,DC=example,DC=com",
        ["CN=chkhealth-admins,OU=Groups,DC=corp,DC=example,DC=com"],
    )
    service_conn = MagicMock()
    service_conn.entries = [entry]
    user_conn = MagicMock()

    with patch("app.ldap_auth.Connection", side_effect=[service_conn, user_conn]):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "alice", "correct-password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="chkhealth-admins",
                group_viewer="chkhealth-viewers",
                verify_ssl=False,
            )

    assert result is not None
    assert result["role"] == "admin"
    assert "chkhealth-admins" in result["ad_groups"]


def test_ldap_authenticate_viewer():
    from app.ldap_auth import authenticate

    entry = _make_mock_entry(
        "CN=bob,OU=Users,DC=corp,DC=example,DC=com",
        ["CN=chkhealth-viewers,OU=Groups,DC=corp,DC=example,DC=com"],
    )
    service_conn = MagicMock()
    service_conn.entries = [entry]
    user_conn = MagicMock()

    with patch("app.ldap_auth.Connection", side_effect=[service_conn, user_conn]):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "bob", "password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="chkhealth-admins",
                group_viewer="chkhealth-viewers",
                verify_ssl=False,
            )

    assert result is not None
    assert result["role"] == "viewer"


def test_ldap_wrong_password_returns_none():
    from app.ldap_auth import authenticate

    entry = _make_mock_entry(
        "CN=alice,OU=Users,DC=corp,DC=example,DC=com",
        ["CN=chkhealth-admins,OU=Groups,DC=corp,DC=example,DC=com"],
    )
    service_conn = MagicMock()
    service_conn.entries = [entry]

    with patch("app.ldap_auth.Connection", side_effect=[service_conn, LDAPBindError("invalid credentials")]):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "alice", "wrong-password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="chkhealth-admins",
                group_viewer="chkhealth-viewers",
                verify_ssl=False,
            )

    assert result is None


def test_ldap_user_not_found_returns_none():
    from app.ldap_auth import authenticate

    service_conn = MagicMock()
    service_conn.entries = []

    with patch("app.ldap_auth.Connection", return_value=service_conn):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "nobody", "password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="chkhealth-admins",
                group_viewer="chkhealth-viewers",
                verify_ssl=False,
            )

    assert result is None


def test_ldap_unmatched_groups_returns_none():
    from app.ldap_auth import authenticate

    entry = _make_mock_entry(
        "CN=alice,OU=Users,DC=corp,DC=example,DC=com",
        ["CN=some-other-group,OU=Groups,DC=corp,DC=example,DC=com"],
    )
    service_conn = MagicMock()
    service_conn.entries = [entry]
    user_conn = MagicMock()

    with patch("app.ldap_auth.Connection", side_effect=[service_conn, user_conn]):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "alice", "password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="chkhealth-admins",
                group_viewer="chkhealth-viewers",
                verify_ssl=False,
            )

    assert result is None


def test_ldap_no_member_of_defaults_to_viewer():
    from app.ldap_auth import authenticate

    entry = _make_mock_entry(
        "CN=carol,OU=Users,DC=corp,DC=example,DC=com",
        [],
    )
    service_conn = MagicMock()
    service_conn.entries = [entry]
    user_conn = MagicMock()

    with patch("app.ldap_auth.Connection", side_effect=[service_conn, user_conn]):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "carol", "password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="",
                group_viewer="",
                verify_ssl=False,
            )

    assert result is not None
    assert result["role"] == "viewer"
    assert result["ad_groups"] == []


def test_ldap_filter_injection_escaped():
    """Special LDAP characters in username must be escaped before filter substitution."""
    from app.ldap_auth import authenticate

    service_conn = MagicMock()
    service_conn.entries = []

    with patch("app.ldap_auth.Connection", return_value=service_conn):
        with patch("app.ldap_auth.Server"):
            authenticate(
                "alice)(cn=*", "password",
                server_url="ldap://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="", group_viewer="",
                verify_ssl=False,
            )

    search_call_args = service_conn.search.call_args
    assert ")(cn=*" not in str(search_call_args)


def test_ldap_group_match_is_exact():
    """LDAP group CN matching must be exact, not substring — no privilege escalation via longer names."""
    from app.ldap_auth import authenticate

    entry = _make_mock_entry(
        "CN=dave,OU=Users,DC=corp,DC=example,DC=com",
        ["CN=chkhealth-admins-extended,OU=Groups,DC=corp,DC=example,DC=com"],
    )
    service_conn = MagicMock()
    service_conn.entries = [entry]
    user_conn = MagicMock()

    with patch("app.ldap_auth.Connection", side_effect=[service_conn, user_conn]):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "dave", "password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="chkhealth-admins",
                group_viewer="chkhealth-viewers",
                verify_ssl=False,
            )

    assert result is None


def test_ldap_network_error_returns_none():
    """OSError (network failure) must be caught and return None, not propagate."""
    from app.ldap_auth import authenticate

    with patch("app.ldap_auth.Connection", side_effect=OSError("network unreachable")):
        with patch("app.ldap_auth.Server"):
            result = authenticate(
                "alice", "password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="", group_viewer="",
                verify_ssl=False,
            )

    assert result is None


def test_ldap_timeout_passed_to_server():
    """Server must be created with the specified connect_timeout."""
    from app.ldap_auth import authenticate

    service_conn = MagicMock()
    service_conn.entries = []

    with patch("app.ldap_auth.Connection", return_value=service_conn):
        with patch("app.ldap_auth.Server") as mock_server:
            authenticate(
                "alice", "password",
                server_url="ldaps://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="", group_viewer="",
                verify_ssl=False,
                timeout=7,
            )

    mock_server.assert_called_once()
    call_kwargs = mock_server.call_args.kwargs
    assert call_kwargs.get("connect_timeout") == 7


def test_ldap_user_search_placeholder_substituted():
    from app.ldap_auth import authenticate

    service_conn = MagicMock()
    service_conn.entries = []

    with patch("app.ldap_auth.Connection", return_value=service_conn):
        with patch("app.ldap_auth.Server"):
            authenticate(
                "alice", "password",
                server_url="ldap://dc01.example.com",
                base_dn="DC=corp,DC=example,DC=com",
                bind_user="svc@example.com",
                bind_password="svc-pass",
                user_search="(sAMAccountName={username})",
                group_admin="", group_viewer="",
                verify_ssl=False,
            )

    search_call_args = service_conn.search.call_args
    assert "alice" in str(search_call_args)
