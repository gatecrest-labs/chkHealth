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


def test_fetch_all_stops_on_empty_page(client):
    client._sid = "sid"
    page1 = {"objects": [{"name": "gw0"}], "total": 999, "success": True}
    page2 = {"objects": [], "total": 999, "success": True}
    with patch.object(client._session, "post") as mock_post:
        mock_post.side_effect = [_resp(page1), _resp(page2)]
        result = client.get_gateways()
    assert len(result) == 1
    assert mock_post.call_count == 2


def test_login_raises_on_success_false(client):
    from app.cp_client import CPAPIError
    with patch.object(client._session, "post",
                      return_value=_resp({"success": False, "message": "Invalid API key"})):
        with pytest.raises(CPAPIError) as exc_info:
            client.login()
    assert exc_info.value.command == "login"


def test_get_packages_uses_packages_key(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "packages": [{"name": "Pkg1"}, {"name": "Pkg2"}], "total": 2, "success": True,
    })):
        pkgs = client.get_packages()
    assert len(pkgs) == 2
    assert pkgs[0]["name"] == "Pkg1"


def test_get_access_rulebase_uses_rulebase_key(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "rulebase": [{"uid": "r1"}, {"uid": "r2"}], "total": 2, "success": True,
    })):
        rules = client.get_access_rulebase("Pkg1")
    assert len(rules) == 2


def test_get_nat_rulebase_uses_rulebase_key(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "rulebase": [{"uid": "n1"}], "total": 1, "success": True,
    })):
        rules = client.get_nat_rulebase("Pkg1")
    assert len(rules) == 1
    assert rules[0]["uid"] == "n1"


def test_get_objects_returns_objects(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "objects": [{"name": "host1", "type": "host"}], "total": 1, "success": True,
    })):
        objs = client.get_objects("host1")
    assert objs[0]["name"] == "host1"


def test_get_objects_uses_limit_200(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "objects": [], "total": 0, "success": True,
    })) as mock_post:
        client.get_objects("anything")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["limit"] == 200


def test_get_gateway_full_returns_dict(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "name": "gw1", "ipv4-address": "10.0.0.1", "success": True,
    })):
        gw = client.get_gateway_full("gw1")
    assert gw["name"] == "gw1"


def test_get_cluster_full_returns_dict(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "name": "cl1", "ipv4-address": "10.0.0.2", "success": True,
    })):
        cl = client.get_cluster_full("cl1")
    assert cl["name"] == "cl1"


def test_fetch_all_key_param_used(client):
    """_fetch_all stops when empty list returned for the given key."""
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "packages": [], "total": 0, "success": True,
    })):
        result = client._fetch_all("show-packages", key="packages")
    assert result == []


def test_gaia_call_constructs_proxy_url(client):
    client._sid = "sid"
    with patch.object(client._session, "post",
                      return_value=_resp({"objects": [], "total": 0, "success": True})) as mock_post:
        client.gaia_call("show-physical-interfaces", "gw1")
    url = mock_post.call_args.args[0]
    assert "gaia-api/v1.6/show-physical-interfaces" in url


def test_gaia_call_includes_target(client):
    client._sid = "sid"
    with patch.object(client._session, "post",
                      return_value=_resp({"objects": [], "total": 0, "success": True})) as mock_post:
        client.gaia_call("show-physical-interfaces", "gw1")
    payload = mock_post.call_args.kwargs["json"]
    assert payload.get("target") == "gw1"


def test_gaia_call_uses_custom_version(client):
    client._sid = "sid"
    with patch.object(client._session, "post",
                      return_value=_resp({"objects": [], "total": 0, "success": True})) as mock_post:
        client.gaia_call("show-bgp-groups", "gw1", api_version="1.7")
    url = mock_post.call_args.args[0]
    assert "gaia-api/v1.7/show-bgp-groups" in url


def test_get_gaia_interfaces_returns_grouped(client):
    client._sid = "sid"
    phys = [{"name": "eth0", "ipv4-address": "10.0.0.1", "ipv4-mask-length": 24,
              "mac-addr": "aa:bb:cc:dd:ee:ff", "enabled": True,
              "status": {"link-state": True, "speed": "1000M", "duplex": "full"}}]
    no_objs = {"objects": [], "total": 0, "success": True}
    phys_resp = {"objects": phys, "total": 1, "success": True}

    def side(url, **kw):
        if "show-physical-interfaces" in url:
            return _resp(phys_resp)
        return _resp(no_objs)

    with patch.object(client._session, "post", side_effect=side):
        result = client.get_gaia_interfaces("gw1")
    assert len(result["physical"]) == 1
    assert result["physical"][0]["name"] == "eth0"
    assert result["vlan"] == []
    assert result["bond"] == []
    assert result["loopback"] == []


def test_get_gaia_routing_returns_routes(client):
    client._sid = "sid"
    routes = [
        {"dest": "10.0.0.0", "mask-length": 24, "nexthop": [{"gateway": "192.168.1.1",
          "priority": 1}], "type": "S", "ifname": "eth0", "metric": 0, "rank": 60},
    ]
    with patch.object(client._session, "post",
                      return_value=_resp({"objects": routes, "total": 1, "success": True})):
        result = client.get_gaia_routing("gw1")
    assert len(result) == 1
    assert result[0]["dest"] == "10.0.0.0"


def test_get_gaia_bgp_returns_groups_and_peers(client):
    client._sid = "sid"
    groups = [{"as": 65000, "num-peers": 1, "num-peers-est": 1}]
    peer = {"peer": "10.0.0.2", "remote-as": 65001, "state": "Established",
            "uptime": "1d", "received": {"routes-received": 10, "routes-received-active": 8}}
    groups_resp = {"objects": groups, "total": 1, "success": True}
    peer_resp = {"success": True, "peer": peer["peer"], "remote-as": peer["remote-as"],
                 "state": peer["state"], "uptime": peer["uptime"],
                 "received": peer["received"]}

    call_count = {"n": 0}
    def side(url, **kw):
        if "show-bgp-groups" in url:
            return _resp(groups_resp)
        if "show-bgp-peer" in url:
            return _resp(peer_resp)
        return _resp({"success": True})
    call_count = {"n": 0}

    with patch.object(client._session, "post", side_effect=side):
        result = client.get_gaia_bgp("gw1")
    assert len(result["groups"]) == 1
    assert result["groups"][0]["as"] == 65000
