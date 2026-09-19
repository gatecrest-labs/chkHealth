import pytest
from unittest.mock import MagicMock, patch


def _resp(data: dict):
    r = MagicMock()
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


@pytest.fixture
def client():
    from app.cp_client import CPClient
    return CPClient("10.0.0.1", "test-key", verify_ssl=False, timeout=10)


def test_login_stores_sid(client):
    with patch.object(client._session, "post", return_value=_resp({"sid": "abc123"})):
        client.login()
    assert client._sid == "abc123"


def test_login_with_domain_sends_domain(client):
    with patch.object(client._session, "post", return_value=_resp({"sid": "dSid"})) as mock_post:
        client.login(domain="MyDomain")
    payload = mock_post.call_args.kwargs["json"]
    assert payload.get("domain") == "MyDomain"


def test_call_sends_sid_header(client):
    client._sid = "my-sid"
    with patch.object(client._session, "post",
                      return_value=_resp({"total": 0, "objects": [], "success": True})) as mock_post:
        client.call("show-domains")
    headers = mock_post.call_args.kwargs.get("headers") or {}
    assert headers.get("X-chkp-sid") == "my-sid"


def test_call_raises_cp_api_error_on_failure(client):
    from app.cp_client import CPAPIError
    client._sid = "sid"
    with patch.object(client._session, "post",
                      return_value=_resp({"success": False, "message": "Not found"})):
        with pytest.raises(CPAPIError) as exc_info:
            client.call("show-objects", {"name": "bad"})
    assert exc_info.value.command == "show-objects"
    assert exc_info.value.data == {"success": False, "message": "Not found"}


def test_get_domains_returns_objects(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "objects": [{"name": "D1"}, {"name": "D2"}], "total": 2, "success": True,
    })):
        domains = client.get_domains()
    assert [d["name"] for d in domains] == ["D1", "D2"]


def test_get_gateways_paginates(client):
    client._sid = "sid"
    page1 = {"objects": [{"name": f"gw{i}"} for i in range(500)], "total": 501, "success": True}
    page2 = {"objects": [{"name": "gw500"}], "total": 501, "success": True}
    with patch.object(client._session, "post") as mock_post:
        mock_post.side_effect = [_resp(page1), _resp(page2)]
        gws = client.get_gateways()
    assert len(gws) == 501
    assert mock_post.call_count == 2


def test_context_manager_calls_login_logout(client):
    with patch.object(client, "login") as mock_login, \
         patch.object(client, "logout") as mock_logout:
        with client:
            pass
    mock_login.assert_called_once_with(domain=None)
    mock_logout.assert_called_once()


def test_context_manager_logs_out_on_body_exception(client):
    with patch.object(client, "login"), patch.object(client, "logout") as mock_logout:
        try:
            with client:
                raise ValueError("test error")
        except ValueError:
            pass
    mock_logout.assert_called_once()


def test_logout_swallows_exceptions(client):
    client._sid = "sid"
    with patch.object(client._session, "post", side_effect=Exception("network error")):
        client.logout()  # must not raise
    assert client._sid is None
