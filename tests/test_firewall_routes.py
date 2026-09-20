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


def _mock_cm(gateways=None, clusters=None):
    mock_client = MagicMock()
    gw_list = gateways or [{"name": "gw1", "ipv4-address": "10.0.0.1"}]
    cl_list = clusters or []

    def _fetch_all_side_effect(command, extra=None, key="objects"):
        if command == "show-simple-gateways":
            return gw_list
        if command == "show-simple-clusters":
            return cl_list
        return []

    mock_client._fetch_all.side_effect = _fetch_all_side_effect
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, mock_client


def test_firewalls_page_loads(fw_client):
    r = fw_client.get("/firewalls")
    assert r.status_code == 200


def test_firewalls_page_requires_login(client):
    r = client.get("/firewalls")
    assert r.status_code in (302, 401)


def test_domains_api_returns_list(fw_client, monkeypatch):
    monkeypatch.setattr(
        "app.domain_cache.get_cached_domains",
        lambda: {"domains": [{"name": "D1"}, {"name": "D2"}], "status": "ok"},
    )
    r = fw_client.get("/api/firewalls/domains")
    assert r.status_code == 200
    data = r.get_json()
    assert "domains" in data
    assert "D1" in data["domains"]


def test_gateways_api_returns_sorted(fw_client):
    cm, _ = _mock_cm(
        gateways=[{"name": "zGW"}, {"name": "aGW"}],
        clusters=[{"name": "cl1"}],
    )
    with patch("app.routes.firewall_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateways?domain=D1")
    assert r.status_code == 200
    data = r.get_json()
    assert data["gateways"][0]["name"] == "aGW"
    assert data["gateways"][1]["name"] == "zGW"
    assert data["clusters"][0]["name"] == "cl1"
    assert data["domain"] == "D1"


def test_gateways_api_requires_domain(fw_client):
    r = fw_client.get("/api/firewalls/gateways")
    assert r.status_code == 400


def test_gateway_detail_gateway_type(fw_client):
    mock_client = MagicMock()
    mock_client.get_gateway_full.return_value = {
        "name": "gw1", "ipv4-address": "10.0.0.1", "success": True
    }
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    with patch("app.routes.firewall_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    assert r.get_json()["name"] == "gw1"


def test_gateway_detail_cluster_type(fw_client):
    mock_client = MagicMock()
    mock_client.get_cluster_full.return_value = {
        "name": "cl1", "ipv4-address": "10.0.0.2", "success": True
    }
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    with patch("app.routes.firewall_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway?domain=D1&name=cl1&type=cluster")
    assert r.status_code == 200
    assert r.get_json()["name"] == "cl1"


def test_gateway_detail_invalid_type(fw_client):
    r = fw_client.get("/api/firewalls/gateway?domain=D1&name=gw1&type=unknown")
    assert r.status_code == 400


def test_gateways_api_upstream_error(fw_client):
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("MDS down")
    with patch("app.routes.firewall_routes.make_client", return_value=bad_cm):
        r = fw_client.get("/api/firewalls/gateways?domain=D1")
    assert r.status_code == 502
