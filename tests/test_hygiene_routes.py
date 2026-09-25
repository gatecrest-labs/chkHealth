import time
import pytest
from unittest.mock import MagicMock


def _make_cm(mock_client):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


@pytest.fixture
def hygiene_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    import app.groups as groups_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = ["rule_hygiene"]
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
        sess["_csrf_token"] = "test-token"
    return client


def test_hygiene_page_loads(hygiene_client, monkeypatch):
    import app.routes.hygiene_routes as hr
    mock_cp = MagicMock()
    monkeypatch.setattr(hr, "make_client", lambda **kw: _make_cm(mock_cp))
    r = hygiene_client.get("/hygiene")
    assert r.status_code == 200


def test_hygiene_packages(hygiene_client, monkeypatch):
    import app.routes.hygiene_routes as hr
    mock_cp = MagicMock()
    mock_cp.get_packages.return_value = [{"name": "Standard"}, {"name": "DMZ"}]
    monkeypatch.setattr(hr, "make_client", lambda **kw: _make_cm(mock_cp))
    r = hygiene_client.get("/api/hygiene/domains/corp/packages")
    assert r.status_code == 200
    names = [p["name"] for p in r.get_json()]
    assert "Standard" in names


def test_hygiene_run_returns_findings(hygiene_client, monkeypatch):
    import app.routes.hygiene_routes as hr
    mock_cp = MagicMock()
    mock_cp.get_access_layers.return_value = [{"name": "Network"}]
    mock_cp.call.return_value = {
        "rulebase": [{
            "type": "access-rule", "rule-number": 1,
            "name": "", "comments": "",
            "source": [{"name": "Any"}], "destination": [{"name": "Any"}],
            "service": [{"name": "Any"}], "action": {"name": "Accept"},
            "track": {"type": {"name": "Log"}}, "enabled": True,
        }],
        "total": 1,
    }
    monkeypatch.setattr(hr, "make_client", lambda **kw: _make_cm(mock_cp))
    r = hygiene_client.post(
        "/api/hygiene/run",
        json={"domain": "corp", "package": "Standard", "checks": ["unnamed"]},
        headers={"X-CSRF-Token": "test-token"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] >= 1
    assert data["findings"][0]["check"] == "unnamed"


def test_hygiene_run_includes_inline_global_layer_rules(hygiene_client, monkeypatch):
    """Rules nested inside an inline access-layer (global policy) must be analyzed by checks."""
    import app.routes.hygiene_routes as hr
    mock_cp = MagicMock()
    mock_cp.get_access_layers.return_value = [{"name": "Network"}]
    # Two unnamed rules: one nested inside an inline access-layer, one at top level.
    # The unnamed check should find both (2 findings), proving the nested rule is processed.
    mock_cp.call.return_value = {
        "rulebase": [
            {
                "type": "access-layer",
                "name": "GlobalLayer",
                "rulebase": [
                    {"type": "access-rule", "rule-number": 1,
                     "name": "", "comments": "",
                     "source": [{"name": "Any"}], "destination": [{"name": "Any"}],
                     "service": [{"name": "Any"}], "action": {"name": "Accept"},
                     "track": {"type": {"name": "Log"}}, "enabled": True},
                ],
            },
            {"type": "access-rule", "rule-number": 2,
             "name": "", "comments": "",
             "source": [{"name": "Any"}], "destination": [{"name": "Any"}],
             "service": [{"name": "Any"}], "action": {"name": "Accept"},
             "track": {"type": {"name": "Log"}}, "enabled": True},
        ],
        "total": 2,
    }
    monkeypatch.setattr(hr, "make_client", lambda **kw: _make_cm(mock_cp))
    r = hygiene_client.post(
        "/api/hygiene/run",
        json={"domain": "corp", "package": "Standard", "checks": ["unnamed"]},
        headers={"X-CSRF-Token": "test-token"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["policy_count"] == 2, "Both inline and regular rules must be counted"
    # After flattening, findings must come from the actual rules, not the inline layer wrapper.
    # GlobalLayer wrapper must NOT appear as a finding; nested rule #1 MUST be found.
    policy_names = {f["policy_name"] for f in data["findings"]}
    assert "GlobalLayer" not in policy_names, \
        "Inline access-layer wrapper must not be treated as a rule"
    assert "Rule #1" in policy_names, \
        "Nested global rule (rule-number 1) must be analyzed by hygiene checks"


def test_hygiene_run_missing_domain(hygiene_client):
    r = hygiene_client.post(
        "/api/hygiene/run",
        json={"package": "Standard", "checks": ["unnamed"]},
        headers={"X-CSRF-Token": "test-token"},
    )
    assert r.status_code == 400


def test_hygiene_run_invalid_check(hygiene_client, monkeypatch):
    import app.routes.hygiene_routes as hr
    mock_cp = MagicMock()
    mock_cp.get_access_layers.return_value = [{"name": "Network"}]
    mock_cp.call.return_value = {"rulebase": [], "total": 0}
    monkeypatch.setattr(hr, "make_client", lambda **kw: _make_cm(mock_cp))
    r = hygiene_client.post(
        "/api/hygiene/run",
        json={"domain": "corp", "package": "Standard", "checks": ["nonexistent_check"]},
        headers={"X-CSRF-Token": "test-token"},
    )
    assert r.status_code == 400


def test_bulk_hygiene_domain(monkeypatch):
    import app.routes.hygiene_routes as hr
    mock_cp = MagicMock()
    mock_cp.get_packages.return_value = [{"name": "Pkg1"}]
    mock_cp.get_access_layers.return_value = [{"name": "Layer1"}]
    mock_cp.call.return_value = {"rulebase": [], "total": 0}
    monkeypatch.setattr(hr, "make_client", lambda **kw: _make_cm(mock_cp))
    results = hr.bulk_hygiene_domain("corp", ["unnamed"])
    assert len(results) == 1
    assert results[0]["package"] == "Pkg1"
    assert results[0]["error"] is None
