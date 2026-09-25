from app.hygiene import (
    check_unnamed, check_unlogged, check_shadow, check_disabled,
    check_expired, check_unhit, check_redundant_rules, check_over_permissive,
    check_broken_refs, run_checks, CHECKS,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _rule(**kwargs):
    """Build a minimal valid CP access-rule dict."""
    base = {
        "type": "access-rule",
        "rule-number": kwargs.pop("rn", 1),
        "name": kwargs.pop("name", "Test Rule"),
        "comments": kwargs.pop("comments", "a comment"),
        "source": kwargs.pop("source", [{"name": "Any", "type": "CpmiAnyObject"}]),
        "destination": kwargs.pop("destination", [{"name": "Any", "type": "CpmiAnyObject"}]),
        "service": kwargs.pop("service", [{"name": "Any", "type": "CpmiAnyObject"}]),
        "action": kwargs.pop("action", {"name": "Accept"}),
        "track": kwargs.pop("track", {"type": {"name": "Log"}}),
        "enabled": kwargs.pop("enabled", True),
    }
    base.update(kwargs)
    return base

def _section():
    return {"type": "access-section", "name": "Section Header"}

def _src(name):
    return [{"name": name}]

def _dst(name):
    return [{"name": name}]

def _svc(name):
    return [{"name": name}]

# ── check_unnamed ─────────────────────────────────────────────────────────────

def test_unnamed_no_name_no_comment():
    r = _rule(name="", comments="")
    findings = check_unnamed([r])
    assert len(findings) == 1
    assert "no name and no comment" in findings[0]["detail"]

def test_unnamed_no_name_has_comment():
    r = _rule(name="", comments="some description")
    findings = check_unnamed([r])
    assert len(findings) == 1
    assert "only a comment" in findings[0]["detail"]

def test_unnamed_has_name_no_comment():
    r = _rule(name="MY-RULE", comments="")
    findings = check_unnamed([r])
    assert len(findings) == 1
    assert "no comment/description" in findings[0]["detail"]

def test_unnamed_has_both_name_and_comment():
    r = _rule(name="MY-RULE", comments="desc")
    assert check_unnamed([r]) == []

def test_unnamed_skips_sections():
    assert check_unnamed([_section()]) == []

# ── check_unlogged ────────────────────────────────────────────────────────────

def test_unlogged_track_none():
    r = _rule(track={"type": {"name": "None"}})
    findings = check_unlogged([r])
    assert len(findings) == 1
    assert findings[0]["check"] == "unlogged"

def test_unlogged_track_log():
    assert check_unlogged([_rule(track={"type": {"name": "Log"}})]) == []

def test_unlogged_track_detailed_log():
    assert check_unlogged([_rule(track={"type": {"name": "Detailed Log"}})]) == []

def test_unlogged_track_string_uid():
    # Standard details returns a UID string; unknown string != "none" → NOT flagged
    r = _rule(track={"type": "some-uid-string"})
    assert check_unlogged([r]) == []

def test_unlogged_track_none_lowercase():
    r = _rule(track={"type": {"name": "none"}})
    assert len(check_unlogged([r])) == 1

def test_unlogged_skips_sections():
    assert check_unlogged([_section()]) == []

# ── check_shadow ──────────────────────────────────────────────────────────────

def _any_rule(rn, action="Accept"):
    return _rule(rn=rn, source=_src("Any"), destination=_dst("Any"),
                 service=_svc("Any"), action={"name": action})

def test_shadow_b_shadowed_by_a():
    a = _any_rule(rn=1)
    b = _any_rule(rn=2)
    findings = check_shadow([a, b])
    assert len(findings) == 1
    assert findings[0]["policy_id"] == "2"

def test_shadow_action_diff_noted():
    a = _any_rule(rn=1, action="Accept")
    b = _any_rule(rn=2, action="Drop")
    findings = check_shadow([a, b])
    assert len(findings) == 1
    assert "actions differ" in findings[0]["detail"]

def test_shadow_different_src_not_shadowed():
    a = _rule(rn=1, source=_src("Host-A"), destination=_dst("Any"), service=_svc("Any"))
    b = _rule(rn=2, source=_src("Host-B"), destination=_dst("Any"), service=_svc("Any"))
    assert check_shadow([a, b]) == []

def test_shadow_disabled_rule_not_shadower():
    a = _rule(rn=1, source=_src("Any"), destination=_dst("Any"),
              service=_svc("Any"), enabled=False)
    b = _any_rule(rn=2)
    assert check_shadow([a, b]) == []

def test_shadow_only_first_shadower_reported():
    a1 = _any_rule(rn=1)
    a2 = _any_rule(rn=2)
    b = _any_rule(rn=3)
    findings = check_shadow([a1, a2, b])
    # a2 is also shadowed by a1; b is shadowed by a1 (break stops at first shadower)
    assert len(findings) == 2
    b_finding = next(f for f in findings if f["policy_id"] == "3")
    assert b_finding["shadowing_rule"]["id"] == "1"

def test_shadow_skips_sections():
    assert check_shadow([_section(), _section()]) == []

# ── check_disabled ────────────────────────────────────────────────────────────

def test_disabled_false():
    r = _rule(enabled=False)
    findings = check_disabled([r])
    assert len(findings) == 1

def test_disabled_true():
    assert check_disabled([_rule(enabled=True)]) == []

def test_disabled_string_false():
    assert len(check_disabled([_rule(enabled="false")])) == 1

def test_disabled_skips_sections():
    assert check_disabled([_section()]) == []

# ── check_expired ─────────────────────────────────────────────────────────────

def test_expired_time_object_present():
    r = _rule(time=[{"name": "Business Hours"}])
    findings = check_expired([r])
    assert len(findings) == 1
    assert "Business Hours" in findings[0]["detail"]

def test_expired_no_time():
    assert check_expired([_rule()]) == []

def test_expired_empty_time_list():
    assert check_expired([_rule(time=[])]) == []

def test_expired_skips_sections():
    assert check_expired([_section()]) == []

# ── check_unhit ───────────────────────────────────────────────────────────────

def test_unhit_zero():
    r = _rule(hits={"value": 0})
    findings = check_unhit([r])
    assert len(findings) == 1

def test_unhit_nonzero():
    assert check_unhit([_rule(hits={"value": 42})]) == []

def test_unhit_no_hits_field():
    # Must be silently skipped — not flagged
    r = _rule()
    assert "hits" not in r
    assert check_unhit([r]) == []

def test_unhit_skips_sections():
    assert check_unhit([_section()]) == []

# ── check_redundant_rules ─────────────────────────────────────────────────────

def test_redundant_mutual_coverage_same_action():
    a = _any_rule(rn=1)
    b = _any_rule(rn=2)
    findings = check_redundant_rules([a, b])
    assert len(findings) == 1
    assert findings[0]["policy_id"] == "2"

def test_redundant_different_action_not_redundant():
    a = _any_rule(rn=1, action="Accept")
    b = _any_rule(rn=2, action="Drop")
    assert check_redundant_rules([a, b]) == []

def test_redundant_one_way_coverage_not_redundant():
    a = _any_rule(rn=1)
    b = _rule(rn=2, source=_src("Host-A"), destination=_dst("Any"), service=_svc("Any"))
    assert check_redundant_rules([a, b]) == []

# ── check_over_permissive ─────────────────────────────────────────────────────

def test_over_permissive_all_3_critical():
    r = _any_rule(rn=1)
    findings = check_over_permissive([r])
    assert len(findings) == 1
    assert findings[0]["severity"] == "critical"

def test_over_permissive_2_dims_high():
    r = _rule(rn=1, source=_src("Any"), destination=_dst("Any"),
              service=_svc("HTTP"), action={"name": "Accept"})
    findings = check_over_permissive([r])
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"

def test_over_permissive_1_dim_not_flagged():
    r = _rule(rn=1, source=_src("Any"), destination=_dst("10.0.0.0/8"),
              service=_svc("HTTP"), action={"name": "Accept"})
    assert check_over_permissive([r]) == []

def test_over_permissive_drop_not_flagged():
    r = _rule(rn=1, source=_src("Any"), destination=_dst("Any"),
              service=_svc("Any"), action={"name": "Drop"})
    assert check_over_permissive([r]) == []

def test_over_permissive_disabled_not_flagged():
    r = _rule(rn=1, source=_src("Any"), destination=_dst("Any"),
              service=_svc("Any"), action={"name": "Accept"}, enabled=False)
    assert check_over_permissive([r]) == []

def test_over_permissive_skips_sections():
    assert check_over_permissive([_section()]) == []

# ── check_broken_refs ─────────────────────────────────────────────────────────

def test_broken_refs_deleted_object_type():
    r = _rule(source=[{"type": "deleted-object", "name": "old-host"}])
    findings = check_broken_refs([r])
    assert len(findings) == 1
    assert "old-host" in findings[0]["detail"]

def test_broken_refs_deleted_object_name():
    r = _rule(destination=[{"type": "host", "name": "deleted_object"}])
    findings = check_broken_refs([r])
    assert len(findings) == 1

def test_broken_refs_clean():
    assert check_broken_refs([_rule()]) == []

def test_broken_refs_skips_sections():
    assert check_broken_refs([_section()]) == []

# ── run_checks dispatcher ─────────────────────────────────────────────────────

def test_run_checks_dispatches():
    r = _rule(name="", comments="", enabled=False)
    findings = run_checks([r], ["unnamed", "disabled"])
    checks_found = {f["check"] for f in findings}
    assert checks_found == {"unnamed", "disabled"}

def test_run_checks_unknown_key_ignored():
    assert run_checks([_rule()], ["nonexistent"]) == []

def test_checks_registry_has_9_entries():
    assert len(CHECKS) == 9
