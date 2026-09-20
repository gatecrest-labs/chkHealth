import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def rr_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    import app.groups as groups_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = ["rule_review"]
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
        sess["_csrf_token"] = "test-token"
    return client


def _make_cm(mock_client):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_rule_review_page_loads(rr_client):
    r = rr_client.get("/rule-review")
    assert r.status_code == 200


def test_rule_review_page_requires_login(client):
    r = client.get("/rule-review")
    assert r.status_code in (302, 401)


def test_packages_api(rr_client):
    mock_client = MagicMock()
    mock_client.get_packages.return_value = [
        {"name": "PkgB"}, {"name": "PkgA"},
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/packages?domain=D1")
    assert r.status_code == 200
    data = r.get_json()
    assert data["packages"] == ["PkgA", "PkgB"]


def test_packages_requires_domain(rr_client):
    r = rr_client.get("/api/rule-review/packages")
    assert r.status_code == 400


def test_rules_api_filters_access_rules(rr_client):
    mock_client = MagicMock()
    mock_client.get_access_rulebase.return_value = [
        {"type": "access-rule", "name": "Rule1", "rule-number": 1,
         "source": [], "destination": [], "service": [], "action": {"name": "Accept"},
         "track": {}, "enabled": True, "comments": ""},
        {"type": "section-title", "name": "Section"},
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/rules?domain=D1&package=Pkg1")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert len(data["rules"]) == 1
    assert data["rules"][0]["name"] == "Rule1"


def test_rules_requires_domain_and_package(rr_client):
    r = rr_client.get("/api/rule-review/rules?domain=D1")
    assert r.status_code == 400
    r2 = rr_client.get("/api/rule-review/rules?package=Pkg1")
    assert r2.status_code == 400


def test_objects_api(rr_client):
    mock_client = MagicMock()
    mock_client.get_objects.return_value = [
        {"name": "host1", "type": "host", "ipv4-address": "10.0.0.1"}
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/objects?domain=D1&name=host1")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["objects"]) == 1


def test_nat_api_filters_by_ip(rr_client):
    mock_client = MagicMock()
    mock_client.get_packages.return_value = [{"name": "Pkg1"}]
    mock_client.get_nat_rulebase.return_value = [
        {
            "type": "nat-rule",
            "rule-number": 1,
            "original-source": {"ip-address": "10.1.1.1"},
            "original-destination": {"ip-address": "any"},
            "translated-source": {"ip-address": "10.2.2.2"},
            "translated-destination": {"ip-address": "original"},
        },
        {
            "type": "nat-rule",
            "rule-number": 2,
            "original-source": {"ip-address": "192.168.1.1"},
            "original-destination": {"ip-address": "any"},
            "translated-source": {"ip-address": "original"},
            "translated-destination": {"ip-address": "original"},
        },
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/nat?domain=D1&ip=10.1.1.1")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["results"]) == 1
    assert data["results"][0]["rule-number"] == 1


def test_interfaces_api(rr_client):
    mock_client = MagicMock()
    mock_client.get_gateways.return_value = [{"name": "gw1"}]
    mock_client.get_clusters.return_value = []
    mock_client.get_gateway_full.return_value = {
        "name": "gw1",
        "interfaces": [
            {"name": "eth0", "ipv4-address": "10.0.0.1",
             "ipv4-network-mask": "255.255.255.0", "subnet4": "10.0.0.0"}
        ],
    }
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/interfaces?domain=D1&ips=10.0.0.1")
    assert r.status_code == 200
    data = r.get_json()
    assert any(res["ip"] == "10.0.0.1" for res in data["results"])


def test_rule_review_upstream_error(rr_client):
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("MDS down")
    with patch("app.routes.rule_review_routes.make_client", return_value=bad_cm):
        r = rr_client.get("/api/rule-review/packages?domain=D1")
    assert r.status_code == 502
