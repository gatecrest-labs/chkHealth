"""Rule Hygiene tab — read-only policy analysis for Check Point packages."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, render_template, request, session

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.hygiene import CHECKS, run_checks
from app.security import upstream_api_error

bp = Blueprint("hygiene", __name__)
registry.register("rule_hygiene", "Rule Hygiene", "hygiene.hygiene_page")


@bp.route("/hygiene")
@login_required
@tab_required("rule_hygiene")
def hygiene_page():
    return render_template("hygiene.html", checks=CHECKS, user=session["user"])


@bp.route("/api/hygiene/domains/<domain>/packages")
@login_required
@tab_required("rule_hygiene")
def hygiene_packages(domain: str):
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            raw = client.get_packages()
        packages = [{"name": p["name"]} for p in raw if p.get("name")]
        return jsonify(packages)
    except Exception as exc:
        return upstream_api_error("hygiene", exc)


def _fetch_hygiene_rules(client, layer: str, show_hits: bool = False) -> list[dict]:
    """Paginate through a layer's rulebase at full details level."""
    results = []
    offset, limit = 0, 500
    while True:
        payload: dict = {
            "name": layer,
            "details-level": "full",
            "limit": limit,
            "offset": offset,
        }
        if show_hits:
            payload["show-hits"] = True
        data = client.call("show-access-rulebase", payload)
        chunk = data.get("rulebase", [])
        if not chunk:
            break
        results.extend(chunk)
        if len(results) >= data.get("total", len(results)):
            break
        offset += len(chunk)
    return results


@bp.route("/api/hygiene/run", methods=["POST"])
@login_required
@tab_required("rule_hygiene")
def hygiene_run():
    data = request.get_json(silent=True) or {}
    domain = (data.get("domain") or "").strip()
    package = (data.get("package") or "").strip()
    checks = data.get("checks") or list(CHECKS.keys())

    if not domain or not package:
        return jsonify({"error": "domain and package are required"}), 400
    err = check_domain_access(domain)
    if err:
        return err

    valid_checks = [c for c in checks if c in CHECKS]
    if not valid_checks:
        return jsonify({"error": "No valid check keys provided"}), 400

    show_hits = "unhit" in valid_checks

    try:
        with make_client(domain=domain) as client:
            layers = client.get_access_layers(package)
            rules: list[dict] = []
            for layer in layers:
                rules.extend(_fetch_hygiene_rules(client, layer["name"], show_hits=show_hits))
    except Exception as exc:
        return upstream_api_error("hygiene", exc)

    findings = run_checks(rules, valid_checks)

    policy_by_id: dict[str, dict] = {}
    for r in rules:
        rn = r.get("rule-number")
        if rn is not None:
            policy_by_id[str(rn)] = r

    def _names(val) -> list[str]:
        if not val:
            return []
        if isinstance(val, str):
            return [val]
        return [(i.get("name", str(i)) if isinstance(i, dict) else str(i)) for i in val]

    for f in findings:
        if "shadow_rule" in f or "rule_detail" in f:
            continue
        p = policy_by_id.get(f["policy_id"])
        if not p:
            continue
        action = p.get("action") or {}
        track = p.get("track") or {}
        track_type = track.get("type") or {}
        f["rule_detail"] = {
            "id": str(p.get("rule-number", "?")),
            "name": str(p.get("name") or ""),
            "enabled": p.get("enabled", True),
            "action": action.get("name", "") if isinstance(action, dict) else str(action),
            "source": _names(p.get("source")),
            "destination": _names(p.get("destination")),
            "service": _names(p.get("service")),
            "track": track_type.get("name", "") if isinstance(track_type, dict) else str(track_type),
            "comment": str(p.get("comments") or ""),
        }

    policy_count = len(rules)
    return jsonify({
        "domain": domain,
        "package": package,
        "checks_run": valid_checks,
        "policy_count": policy_count,
        "total": len(findings),
        "findings": findings,
    })


def bulk_hygiene_domain(
    domain: str,
    checks: list[str],
    include_unused_objects: bool = False,
    max_workers: int = 4,
) -> list[dict]:
    """Run hygiene checks on all packages in a domain. Session-free; used by scheduler."""
    with make_client(domain=domain) as client:
        packages = client.get_packages()

    show_hits = "unhit" in checks

    def _run_pkg(pkg: dict) -> dict:
        pkg_name = pkg.get("name", "")
        try:
            with make_client(domain=domain) as c:
                layers = c.get_access_layers(pkg_name)
                rules: list[dict] = []
                for layer in layers:
                    rules.extend(_fetch_hygiene_rules(c, layer["name"], show_hits=show_hits))
            findings = run_checks(rules, checks)
            return {
                "package": pkg_name,
                "package_name": pkg_name,
                "findings": findings,
                "unused_objects": None,
                "policy_count": len(rules),
                "error": None,
            }
        except Exception as exc:
            return {
                "package": pkg_name,
                "package_name": pkg_name,
                "findings": [],
                "unused_objects": None,
                "policy_count": 0,
                "error": str(exc),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(_run_pkg, packages))
