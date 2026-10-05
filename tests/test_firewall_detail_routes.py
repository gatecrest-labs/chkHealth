import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def fw_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    import app.groups as groups_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = ["firewalls"]
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
        sess["_csrf_token"] = "test-token"
    return client


def _mock_gw(name="gw1", version="R82", sic="Communicating",
             members=None):
    obj = {
        "name": name,
        "ipv4-address": "10.0.0.1",
        "version": version,
        "sic-state": sic,
        "os-name": "Gaia",
        "hardware": "5000",
        "platform": "x86",
        "interfaces": [],
    }
    if members is not None:
        obj["cluster-members"] = members
    return obj


def _make_cm(obj):
    mock_client = MagicMock()
    mock_client.get_gateway_full.return_value = obj
    mock_client.get_cluster_full.return_value = obj
    mock_client.get_gaia_interfaces.return_value = {
        "physical": [], "vlan": [], "bond": [], "loopback": []
    }
    mock_client.get_gaia_routing.return_value = []
    mock_client.get_gaia_bgp.return_value = {"groups": [], "peers": []}
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, mock_client


# ── Detail page ───────────────────────────────────────────────────────────────

def test_detail_page_gateway_renders(fw_client):
    cm, _ = _make_cm(_mock_gw())
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/firewalls/gateway?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    assert b"gw1" in r.data


def test_detail_page_missing_domain_returns_400(fw_client):
    r = fw_client.get("/firewalls/gateway?name=gw1&type=gateway")
    assert r.status_code == 400


def test_detail_page_missing_name_returns_400(fw_client):
    r = fw_client.get("/firewalls/gateway?domain=D1&type=gateway")
    assert r.status_code == 400


def test_detail_page_invalid_type_returns_400(fw_client):
    r = fw_client.get("/firewalls/gateway?domain=D1&name=gw1&type=router")
    assert r.status_code == 400


def test_detail_page_requires_login(client):
    r = client.get("/firewalls/gateway?domain=D1&name=gw1&type=gateway")
    assert r.status_code in (302, 401)


# ── Interfaces API ────────────────────────────────────────────────────────────

def test_interfaces_api_returns_grouped(fw_client):
    phys = [{"name": "eth0", "ipv4-address": "10.0.0.1", "ipv4-mask-length": 24,
             "mac-addr": "aa:bb:cc:dd:ee:ff", "enabled": True,
             "status": {"link-state": True, "speed": "1000M", "duplex": "full"}}]
    cm, mock_client = _make_cm(_mock_gw())
    mock_client.get_gaia_interfaces.return_value = {
        "physical": phys, "vlan": [], "bond": [], "loopback": []
    }
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/interfaces?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    data = r.get_json()
    assert data["available"] is True
    assert len(data["physical"]) == 1
    assert data["physical"][0]["name"] == "eth0"


def test_interfaces_api_requires_domain(fw_client):
    r = fw_client.get("/api/firewalls/gateway/interfaces?name=gw1&type=gateway")
    assert r.status_code == 400


def test_interfaces_api_gaia_error_returns_502(fw_client):
    cm, mock_client = _make_cm(_mock_gw())
    mock_client.get_gaia_interfaces.side_effect = ConnectionError("SIC down")
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/interfaces?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 502


# ── Routing API ───────────────────────────────────────────────────────────────

def test_routing_api_returns_routes(fw_client):
    routes = [
        {"dest": "10.0.0.0", "mask-length": 24,
         "nexthop": [{"gateway": "192.168.1.1"}],
         "type": "S", "ifname": "eth0", "metric": 0, "rank": 60},
        {"dest": "0.0.0.0", "mask-length": 0,
         "nexthop": [{"gateway": "10.1.0.1"}],
         "type": "O", "ifname": "eth1", "metric": 110, "rank": 110},
    ]
    cm, mock_client = _make_cm(_mock_gw(version="R82"))
    mock_client.get_gaia_routing.return_value = routes
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/routing?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    data = r.get_json()
    assert data["available"] is True
    assert data["total"] == 2
    # Protocol normalisation: "S" → "static", "O" → "ospf"
    protocols = {rt["protocol"] for rt in data["routes"]}
    assert "static" in protocols
    assert "ospf" in protocols


def test_routing_api_version_gate_r81_10(fw_client):
    cm, _ = _make_cm(_mock_gw(version="R81.10"))
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/routing?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    data = r.get_json()
    assert data["available"] is False
    assert data["reason"] == "requires_r81_20"


def test_routing_api_version_gate_r81_20_allowed(fw_client):
    cm, mock_client = _make_cm(_mock_gw(version="R81.20"))
    mock_client.get_gaia_routing.return_value = []
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/routing?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    assert r.get_json()["available"] is True


def test_routing_api_empty_table(fw_client):
    cm, mock_client = _make_cm(_mock_gw(version="R82"))
    mock_client.get_gaia_routing.return_value = []
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/routing?domain=D1&name=gw1&type=gateway")
    data = r.get_json()
    assert data["available"] is True
    assert data["routes"] == []
    assert data["total"] == 0


def test_routing_api_cluster_no_active_member(fw_client):
    members = [
        {"name": "m1", "priority": 1, "sic-state": "Unknown"},
        {"name": "m2", "priority": 2, "sic-state": "Unknown"},
    ]
    cm, _ = _make_cm(_mock_gw(version="R82", members=members))
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/routing?domain=D1&name=cl1&type=cluster")
    assert r.status_code == 200
    data = r.get_json()
    assert data["available"] is False
    assert data["reason"] == "no_active_member"


def test_routing_api_cluster_active_member(fw_client):
    members = [
        {"name": "m1", "priority": 1, "sic-state": "Communicating"},
        {"name": "m2", "priority": 2, "sic-state": "Communicating"},
    ]
    routes = [{"dest": "10.0.0.0", "mask-length": 24,
               "nexthop": [{"gateway": "10.1.0.1"}],
               "type": "S", "ifname": "eth0", "metric": 0, "rank": 60}]
    cm, mock_client = _make_cm(_mock_gw(version="R82", members=members))
    mock_client.get_gaia_routing.return_value = routes
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/routing?domain=D1&name=cl1&type=cluster")
    data = r.get_json()
    assert data["available"] is True
    assert data["target_member"] == "m1"  # priority 1 (lowest number = highest priority)
    mock_client.get_gaia_routing.assert_called_once_with("m1")


# ── Protocols API ─────────────────────────────────────────────────────────────

def test_protocols_api_bgp_r82(fw_client):
    cm, mock_client = _make_cm(_mock_gw(version="R82"))
    mock_client.get_gaia_bgp.return_value = {
        "groups": [{"as": 65000, "num-peers": 1}],
        "peers": [{"peer": "10.0.0.2", "remote-as": 65001,
                   "state": "Established", "uptime": "1d",
                   "received": {"routes-received": 10}}],
    }
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/protocols?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    data = r.get_json()
    assert data["bgp"]["available"] is True
    assert len(data["bgp"]["peers"]) == 1


def test_protocols_api_bgp_not_available_pre_r82(fw_client):
    cm, _ = _make_cm(_mock_gw(version="R81.20"))
    with patch("app.routes.firewall_detail_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway/protocols?domain=D1&name=gw1&type=gateway")
    data = r.get_json()
    assert data["bgp"]["available"] is False
    assert data["bgp"]["reason"] == "requires_r82"
