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
        "rulebase": [
            {
                "type": "access-rule",
                "rule-number": 1,
                "name": "",
                "comments": "",
                "source": [{"name": "Any"}],
                "destination": [{"name": "Any"}],
                "service": [{"name": "Any"}],
                "action": {"name": "Accept"},
                "track": {"type": {"name": "Log"}},
                "enabled": True,
            }
        ],
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
                    {
                        "type": "access-rule",
                        "rule-number": 1,
                        "name": "",
                        "comments": "",
                        "source": [{"name": "Any"}],
                        "destination": [{"name": "Any"}],
                        "service": [{"name": "Any"}],
                        "action": {"name": "Accept"},
                        "track": {"type": {"name": "Log"}},
                        "enabled": True,
                    },
                ],
            },
            {
                "type": "access-rule",
                "rule-number": 2,
                "name": "",
                "comments": "",
                "source": [{"name": "Any"}],
                "destination": [{"name": "Any"}],
                "service": [{"name": "Any"}],
                "action": {"name": "Accept"},
                "track": {"type": {"name": "Log"}},
                "enabled": True,
            },
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
    assert "GlobalLayer" not in policy_names, (
        "Inline access-layer wrapper must not be treated as a rule"
    )
    assert "Rule #1" in policy_names, (
        "Nested global rule (rule-number 1) must be analyzed by hygiene checks"
    )


def test_hygiene_run_includes_rules_inside_sections(hygiene_client, monkeypatch):
    """Rules nested inside access-section objects must be analyzed by checks."""
    import app.routes.hygiene_routes as hr

    mock_cp = MagicMock()
    mock_cp.get_access_layers.return_value = [{"name": "Network"}]
    mock_cp.call.return_value = {
        "rulebase": [
            {
                "type": "access-section",
                "name": "Corp Rules Section",
                "rulebase": [
                    {
                        "type": "access-rule",
                        "rule-number": 1,
                        "name": "",
                        "comments": "",
                        "source": [{"name": "Any"}],
                        "destination": [{"name": "Any"}],
                        "service": [{"name": "Any"}],
                        "action": {"name": "Accept"},
                        "track": {"type": {"name": "Log"}},
                        "enabled": True,
                    },
                ],
            },
            {
                "type": "access-rule",
                "rule-number": 2,
                "name": "",
                "comments": "",
                "source": [{"name": "Any"}],
                "destination": [{"name": "Any"}],
                "service": [{"name": "Any"}],
                "action": {"name": "Accept"},
                "track": {"type": {"name": "Log"}},
                "enabled": True,
            },
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
    assert data["policy_count"] == 2, (
        "Both section-nested and top-level rules must be counted"
    )
    policy_names = {f["policy_name"] for f in data["findings"]}
    assert "Corp Rules Section" not in policy_names, (
        "Section wrapper must not appear as a rule"
    )
    assert "Rule #1" in policy_names, "Rule nested inside section must be analyzed"


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


# ── _resolve_time_schedules ───────────────────────────────────────────────────


def _make_times_client(uid, name):
    """Mock client where show-times returns the schedule and show-time is unused."""
    client = MagicMock()
    client.call.side_effect = lambda cmd, payload=None: (
        {"objects": [{"uid": uid, "name": name}], "total": 1}
        if cmd == "show-times"
        else {}
    )
    return client


def test_resolve_time_schedules_plain_uid():
    """Plain UID strings resolved via show-times bulk lookup."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [{"type": "access-rule", "rule-number": 1, "name": "R1", "time": [uid]}]
    client = _make_times_client(uid, "Business Hours")
    _resolve_time_schedules(rules, client)
    assert rules[0]["time"][0] == {"uid": uid, "name": "Business Hours"}


def test_resolve_time_schedules_uid_equals_name():
    """Dicts where name == uid are resolved to the actual schedule name."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [
        {
            "type": "access-rule",
            "rule-number": 1,
            "name": "R1",
            "time": [{"uid": uid, "name": uid, "type": "time"}],
        }
    ]
    client = _make_times_client(uid, "Business Hours")
    _resolve_time_schedules(rules, client)
    assert rules[0]["time"][0]["name"] == "Business Hours"


def test_resolve_time_schedules_already_named():
    """Properly named time dicts skip all API calls."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [
        {
            "type": "access-rule",
            "rule-number": 1,
            "name": "R1",
            "time": [{"uid": uid, "name": "Business Hours", "type": "time"}],
        }
    ]
    client = MagicMock()
    _resolve_time_schedules(rules, client)
    client.call.assert_not_called()
    assert rules[0]["time"][0]["name"] == "Business Hours"


def test_resolve_time_schedules_fallback_show_object():
    """Falls back to show-object for global/predefined objects missed by show-times."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [{"type": "access-rule", "rule-number": 1, "name": "R1", "time": [uid]}]
    client = MagicMock()
    client.call.side_effect = lambda cmd, payload=None: (
        {"objects": [], "total": 0}  # show-times returns nothing for global objects
        if cmd == "show-times"
        else {"object": {"uid": uid, "name": "WorkHours", "type": "time"}}
        if cmd == "show-object"
        else {}
    )
    _resolve_time_schedules(rules, client)
    assert rules[0]["time"][0]["name"] == "WorkHours"


def test_resolve_time_schedules_fallback_to_show_time():
    """Falls back to show-time when show-times and show-object both fail."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [{"type": "access-rule", "rule-number": 1, "name": "R1", "time": [uid]}]
    client = MagicMock()
    client.call.side_effect = lambda cmd, payload=None: (
        (_ for _ in ()).throw(ConnectionError("show-times unavailable"))
        if cmd == "show-times"
        else (_ for _ in ()).throw(ConnectionError("show-object unavailable"))
        if cmd == "show-object"
        else {"name": "Business Hours", "uid": uid}
    )
    _resolve_time_schedules(rules, client)
    assert rules[0]["time"][0]["name"] == "Business Hours"


def test_resolve_time_schedules_api_failure():
    """Both show-times and show-time failure keeps UIDs unchanged without raising."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [{"type": "access-rule", "rule-number": 1, "name": "R1", "time": [uid]}]
    client = MagicMock()
    client.call.side_effect = ConnectionError("MDS down")
    _resolve_time_schedules(rules, client)  # must not raise
    assert rules[0]["time"] == [uid]  # unchanged


def test_resolve_time_schedules_deduplicates_api_calls():
    """Multiple rules sharing the same UID trigger only one show-times call."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [
        {"type": "access-rule", "rule-number": 1, "name": "R1", "time": [uid]},
        {"type": "access-rule", "rule-number": 2, "name": "R2", "time": [uid]},
    ]
    client = _make_times_client(uid, "Business Hours")
    _resolve_time_schedules(rules, client)
    # show-times called once; show-time not needed (uid already resolved)
    show_times_calls = [
        c for c in client.call.call_args_list if c[0][0] == "show-times"
    ]
    assert len(show_times_calls) == 1
    assert rules[0]["time"][0]["name"] == "Business Hours"
    assert rules[1]["time"][0]["name"] == "Business Hours"


def test_resolve_time_schedules_strips_any_object():
    """CpmiAnyObject ('Any') resolved via show-object is stripped from the time list."""
    from app.routes.hygiene_routes import _resolve_time_schedules

    uid = "97aeb369-9aea-11d5-bd16-0090272ccb30"
    rules = [{"type": "access-rule", "rule-number": 1, "name": "R1", "time": [uid]}]
    client = MagicMock()
    client.call.side_effect = lambda cmd, payload=None: (
        {"objects": [], "total": 0}
        if cmd == "show-times"
        else {"object": {"uid": uid, "name": "Any", "type": "CpmiAnyObject"}}
        if cmd == "show-object"
        else {}
    )
    _resolve_time_schedules(rules, client)
    assert rules[0]["time"] == [], (
        "CpmiAnyObject must be stripped — rule has no real time restriction"
    )
