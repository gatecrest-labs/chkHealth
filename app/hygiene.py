"""Rule hygiene checks for Check Point policy packages.

Each check receives the full flat rule list and returns finding dicts:
  {"policy_id": str, "policy_name": str, "seq": int, "check": str, "detail": str}
"""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)

CHECKS: dict[str, str] = {
    "unnamed":         "Unnamed Rules (no name or comment)",
    "unlogged":        "Unlogged Rules (track = None)",
    "shadow":          "Shadow Rules (hidden by broader rule above)",
    "disabled":        "Disabled / Inactive Rules",
    "expired":         "Time-Restricted Rules (verify schedule expiry)",
    "unhit":           "Unused / Un-Hit Rules (zero hit count)",
    "redundant":       "Redundant Rules (duplicate scope of an earlier rule)",
    "over_permissive": "Over-Permissive Rules (accept rules with 2+ unrestricted dimensions)",
    "broken_refs":     "Broken References (deleted objects in rules)",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_section(r: dict) -> bool:
    return r.get("type") == "access-section"

def _is_enabled(r: dict) -> bool:
    enabled = r.get("enabled", True)
    return enabled not in (False, "false", "False", 0)

def _action_name(r: dict) -> str:
    action = r.get("action") or {}
    if isinstance(action, dict):
        return str(action.get("name") or "").lower()
    return str(action).lower()

def _track_type(r: dict) -> str:
    track = r.get("track") or {}
    tt = track.get("type") or {}
    if isinstance(tt, dict):
        return str(tt.get("name") or "none").lower()
    return str(tt or "none").lower()

def _obj_names(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val]
    result = []
    for item in val:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(item.get("name", str(item)))
    return result

def _is_any(names: list[str]) -> bool:
    return any(n.lower() == "any" for n in names)

def _rule_number(r: dict, idx: int) -> int:
    rn = r.get("rule-number")
    return int(rn) if rn is not None else idx + 1

def _rule_name(r: dict, idx: int = 0) -> str:
    n = str(r.get("name") or "").strip()
    return n if n else f"Rule #{_rule_number(r, idx)}"

def _finding(r: dict, idx: int, check: str, detail: str, **extra) -> dict:
    return {
        "policy_id": str(_rule_number(r, idx)),
        "policy_name": _rule_name(r, idx),
        "seq": _rule_number(r, idx),
        "check": check,
        "detail": detail,
        **extra,
    }

def _rule_summary(r: dict) -> dict:
    return {
        "id": str(r.get("rule-number", "?")),
        "name": str(r.get("name") or ""),
        "enabled": _is_enabled(r),
        "action": _action_name(r),
        "source": _obj_names(r.get("source")),
        "destination": _obj_names(r.get("destination")),
        "service": _obj_names(r.get("service")),
        "comment": str(r.get("comments") or ""),
    }

def _covers(a_names: set[str], b_names: set[str]) -> bool:
    if not b_names:
        return True
    if any(n.lower() == "any" for n in a_names):
        return True
    return b_names <= a_names

# ── Check functions ───────────────────────────────────────────────────────────

def check_unnamed(rules: list[dict]) -> list[dict]:
    findings = []
    for idx, r in enumerate(rules):
        if _is_section(r):
            continue
        name = str(r.get("name") or "").strip()
        comment = str(r.get("comments") or "").strip()
        if not name and not comment:
            findings.append(_finding(r, idx, "unnamed", "Rule has no name and no comment."))
        elif not name:
            findings.append(_finding(r, idx, "unnamed",
                f"Rule has no name (only a comment: '{comment[:80]}')."))
        elif not comment:
            findings.append(_finding(r, idx, "unnamed",
                "Rule has a name but no comment/description."))
    return findings

def check_unlogged(rules: list[dict]) -> list[dict]:
    findings = []
    for idx, r in enumerate(rules):
        if _is_section(r):
            continue
        tt = _track_type(r)
        if tt in ("none", ""):
            findings.append(_finding(r, idx, "unlogged",
                f"track type = '{tt or 'not set'}' — no traffic logging."))
    return findings

def check_shadow(rules: list[dict]) -> list[dict]:
    findings = []
    enabled = [r for r in rules if _is_enabled(r) and not _is_section(r)]
    for j, b in enumerate(enabled):
        b_src = set(_obj_names(b.get("source")))
        b_dst = set(_obj_names(b.get("destination")))
        b_svc = set(_obj_names(b.get("service")))
        b_action = _action_name(b)
        for a in enabled[:j]:
            a_src = set(_obj_names(a.get("source")))
            a_dst = set(_obj_names(a.get("destination")))
            a_svc = set(_obj_names(a.get("service")))
            if not (_covers(a_src, b_src) and _covers(a_dst, b_dst) and _covers(a_svc, b_svc)):
                continue
            a_action = _action_name(a)
            action_note = (
                f" Note: actions differ (shadowing={a_action}, shadowed={b_action})"
                " — possible policy ordering mistake."
                if a_action != b_action else ""
            )
            findings.append({
                **_finding(b, j, "shadow",
                    f"Fully shadowed by rule '{_rule_name(a)}' (rule #{_rule_number(a, 0)}) "
                    f"which appears earlier and covers the same src/dst/service scope.{action_note}"),
                "shadow_rule": _rule_summary(b),
                "shadowing_rule": _rule_summary(a),
            })
            break
    return findings

def check_disabled(rules: list[dict]) -> list[dict]:
    findings = []
    for idx, r in enumerate(rules):
        if _is_section(r):
            continue
        if not _is_enabled(r):
            findings.append(_finding(r, idx, "disabled", "Rule is disabled."))
    return findings

def check_expired(rules: list[dict]) -> list[dict]:
    findings = []
    for idx, r in enumerate(rules):
        if _is_section(r):
            continue
        time_val = r.get("time")
        if not time_val:
            continue
        if isinstance(time_val, list):
            if not time_val:
                continue
            time_obj = time_val[0]
        else:
            time_obj = time_val
        name = time_obj.get("name", "unknown") if isinstance(time_obj, dict) else str(time_obj)
        findings.append(_finding(r, idx, "expired",
            f"References time-based schedule '{name}' — verify it has not expired."))
    return findings

def check_unhit(rules: list[dict]) -> list[dict]:
    findings = []
    for idx, r in enumerate(rules):
        if _is_section(r):
            continue
        hits = r.get("hits")
        if hits is None:
            continue
        value = hits.get("value") if isinstance(hits, dict) else hits
        if value is None:
            continue
        try:
            if int(value) == 0:
                findings.append(_finding(r, idx, "unhit",
                    "Hit count is 0 — rule has never matched traffic."))
        except (TypeError, ValueError):
            pass
    return findings

def check_redundant_rules(rules: list[dict]) -> list[dict]:
    findings = []
    enabled = [r for r in rules if _is_enabled(r) and not _is_section(r)]
    for j, b in enumerate(enabled):
        b_src = set(_obj_names(b.get("source")))
        b_dst = set(_obj_names(b.get("destination")))
        b_svc = set(_obj_names(b.get("service")))
        b_action = _action_name(b)
        for a in enabled[:j]:
            if _action_name(a) != b_action:
                continue
            a_src = set(_obj_names(a.get("source")))
            a_dst = set(_obj_names(a.get("destination")))
            a_svc = set(_obj_names(a.get("service")))
            if not (
                _covers(a_src, b_src) and _covers(b_src, a_src)
                and _covers(a_dst, b_dst) and _covers(b_dst, a_dst)
                and _covers(a_svc, b_svc) and _covers(b_svc, a_svc)
            ):
                continue
            findings.append({
                **_finding(b, j, "redundant",
                    f"Matches the same traffic scope as rule '{_rule_name(a)}' "
                    f"(rule #{_rule_number(a, 0)}) which appears earlier"
                    " — consider consolidating."),
                "redundant_rule": _rule_summary(b),
                "duplicate_of": _rule_summary(a),
            })
            break
    return findings

def check_over_permissive(rules: list[dict]) -> list[dict]:
    findings = []
    for idx, r in enumerate(rules):
        if _is_section(r):
            continue
        if not _is_enabled(r):
            continue
        if _action_name(r) != "accept":
            continue
        src_any = _is_any(_obj_names(r.get("source")))
        dst_any = _is_any(_obj_names(r.get("destination")))
        svc_any = _is_any(_obj_names(r.get("service")))
        open_dims = [
            label for label, flag in
            (("source", src_any), ("destination", dst_any), ("service", svc_any))
            if flag
        ]
        count = len(open_dims)
        if count < 2:
            continue
        severity = "critical" if count == 3 else "high"
        detail = (
            "Fully open — source, destination, and service are all unrestricted"
            if count == 3
            else f"Over-permissive — {' and '.join(open_dims)} are unrestricted"
        )
        findings.append({**_finding(r, idx, "over_permissive", detail), "severity": severity})
    return findings

def check_broken_refs(rules: list[dict]) -> list[dict]:
    findings = []
    for idx, r in enumerate(rules):
        if _is_section(r):
            continue
        issues: list[str] = []
        for field_label, field_key in (
            ("source", "source"),
            ("destination", "destination"),
            ("service", "service"),
        ):
            raw = r.get(field_key) or []
            for item in (raw if isinstance(raw, list) else [raw]):
                if isinstance(item, dict):
                    obj_type = str(item.get("type", "")).lower()
                    obj_name = item.get("name", "")
                    if obj_type == "deleted-object" or obj_name == "deleted_object":
                        issues.append(f'{field_label}: deleted object "{obj_name}"')
        if issues:
            findings.append(_finding(r, idx, "broken_refs", "; ".join(issues)))
    return findings

# ── Dispatcher ────────────────────────────────────────────────────────────────

_CHECK_FNS = {
    "unnamed": check_unnamed,
    "unlogged": check_unlogged,
    "shadow": check_shadow,
    "disabled": check_disabled,
    "expired": check_expired,
    "unhit": check_unhit,
    "redundant": check_redundant_rules,
    "over_permissive": check_over_permissive,
    "broken_refs": check_broken_refs,
}

def run_checks(rules: list[dict], checks: list[str], **kwargs) -> list[dict]:
    """Run requested checks against rules list. Returns combined findings."""
    results = []
    for key in checks:
        fn = _CHECK_FNS.get(key)
        if fn:
            results.extend(fn(rules))
    return results
