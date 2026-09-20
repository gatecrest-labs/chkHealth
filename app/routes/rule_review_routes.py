from flask import Blueprint, jsonify, render_template, request

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.security import upstream_api_error

registry.register("rule_review", "Rule Review", "rule_review.rule_review_page", icon="📋")

bp = Blueprint("rule_review", __name__, url_prefix="/")

_RULE_FIELDS = (
    "type", "name", "rule-number", "source", "destination",
    "service", "action", "track", "enabled", "comments",
)


@bp.route("/rule-review")
@login_required
@tab_required("rule_review")
def rule_review_page():
    return render_template("rule_review.html")


@bp.route("/api/rule-review/packages")
@login_required
@tab_required("rule_review")
def api_rr_packages():
    domain = request.args.get("domain", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            pkgs = client.get_packages()
        names = sorted(p.get("name", "") for p in pkgs if p.get("name"))
        return jsonify({"packages": names})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


def _fetch_layer_rules(client, layer: str) -> list[dict]:
    """Fetch rules for a layer and resolve UIDs to names via objects-dictionary."""
    results = []
    uid_names: dict[str, str] = {}
    offset, limit = 0, 500
    while True:
        data = client.call("show-access-rulebase", {
            "name": layer, "details-level": "standard", "limit": limit, "offset": offset,
        })
        chunk = data.get("rulebase", [])
        if not chunk:
            break
        results.extend(chunk)
        for obj in data.get("objects-dictionary", []):
            uid = obj.get("uid")
            name = obj.get("name")
            if uid and name:
                uid_names[uid] = name
        if len(results) >= data.get("total", len(results)):
            break
        offset += len(chunk)

    def _res(v):
        if isinstance(v, str):
            return uid_names.get(v, v)
        if isinstance(v, list):
            return [uid_names.get(x, x) if isinstance(x, str) else x for x in v]
        return v

    resolved = []
    for r in results:
        trk = r.get("track") or {}
        resolved.append({
            **r,
            "source": _res(r.get("source", [])),
            "destination": _res(r.get("destination", [])),
            "service": _res(r.get("service", [])),
            "action": _res(r.get("action")),
            "track": {**trk, "type": _res(trk.get("type"))},
        })
    return resolved


@bp.route("/api/rule-review/rules")
@login_required
@tab_required("rule_review")
def api_rr_rules():
    domain = request.args.get("domain", "").strip()
    package = request.args.get("package", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not package:
        return jsonify({"error": "package is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            layers = client.get_access_layers(package)
            rulebase = []
            for layer in layers:
                rulebase.extend(_fetch_layer_rules(client, layer["name"]))
        rules = [
            {k: r.get(k) for k in _RULE_FIELDS}
            for r in rulebase
            if r.get("type") == "access-rule"
        ][:2000]
        return jsonify({"rules": rules, "total": len(rules)})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


def _object_detail(obj: dict) -> str:
    t = obj.get("type", "")
    if t == "host":
        return obj.get("ipv4-address") or obj.get("ipv6-address") or ""
    if t == "network":
        subnet = obj.get("subnet4") or obj.get("subnet6") or ""
        mask = obj.get("subnet-mask") or (f"/{obj.get('mask-length4')}" if obj.get("mask-length4") is not None else "")
        return f"{subnet} {mask}".strip()
    if t == "address-range":
        return f"{obj.get('ipv4-address-first','')} – {obj.get('ipv4-address-last','')}"
    return ""


def _object_category(obj_type: str) -> str:
    return {
        "host": "Host", "network": "Network", "group": "Group",
        "address-range": "Range", "service-tcp": "TCP Service",
        "service-udp": "UDP Service", "service-icmp": "ICMP Service",
        "service-group": "Service Group",
    }.get(obj_type, obj_type.replace("-", " ").title() if obj_type else "")


@bp.route("/api/rule-review/objects")
@login_required
@tab_required("rule_review")
def api_rr_objects():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            raw = client.call("show-objects", {
                "filter": name, "type": "object",
                "details-level": "full", "limit": 50,
            }).get("objects", [])
            result = []
            for obj in raw:
                obj_type = obj.get("type", "")
                members = []
                if obj_type in ("group", "service-group"):
                    try:
                        cmd = "show-service-group" if obj_type == "service-group" else "show-group"
                        grp = client.call(cmd, {"name": obj.get("name", "")})
                        members = [m.get("name", "") for m in grp.get("members", []) if m.get("name")]
                    except Exception:
                        pass
                result.append({
                    "name": obj.get("name"),
                    "type": obj_type,
                    "category": _object_category(obj_type),
                    "detail": _object_detail(obj),
                    "members": members,
                    "comments": obj.get("comments") or "",
                    "uid": obj.get("uid"),
                })
        return jsonify({"objects": result})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


def _extract_interfaces(gw_name: str, details: dict) -> list[dict]:
    results = []
    for iface in details.get("interfaces", []):
        ip = iface.get("ipv4-address", "")
        if ip:
            results.append({
                "gateway": gw_name,
                "interface": iface.get("name", ""),
                "ip": ip,
                "subnet": iface.get("subnet4", ""),
                "mask": iface.get("ipv4-network-mask", ""),
            })
    return results


@bp.route("/api/rule-review/interfaces")
@login_required
@tab_required("rule_review")
def api_rr_interfaces():
    domain = request.args.get("domain", "").strip()
    ips_raw = request.args.get("ips", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not ips_raw:
        return jsonify({"error": "ips is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    target_ips = {ip.strip() for ip in ips_raw.split(",") if ip.strip()}
    try:
        with make_client(domain=domain) as client:
            gateways = client.get_gateways()
            clusters = client.get_clusters()
            results = []
            for gw in gateways:
                name = gw.get("name", "")
                details = client.get_gateway_full(name)
                for entry in _extract_interfaces(name, details):
                    if entry["ip"] in target_ips:
                        results.append(entry)
            for cl in clusters:
                name = cl.get("name", "")
                details = client.get_cluster_full(name)
                for entry in _extract_interfaces(name, details):
                    if entry["ip"] in target_ips:
                        results.append(entry)
        return jsonify({"results": results})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


def _nat_matches_ip(rule: dict, ip: str) -> bool:
    for field in (
        "original-source", "original-destination",
        "translated-source", "translated-destination",
    ):
        obj = rule.get(field)
        if isinstance(obj, dict) and obj.get("ip-address") == ip:
            return True
    return False


@bp.route("/api/rule-review/nat")
@login_required
@tab_required("rule_review")
def api_rr_nat():
    domain = request.args.get("domain", "").strip()
    ip = request.args.get("ip", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not ip:
        return jsonify({"error": "ip is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        results = []
        with make_client(domain=domain) as client:
            packages = client.get_packages()
            for pkg in packages:
                pkg_name = pkg.get("name", "")
                nat_rules = client.get_nat_rulebase(pkg_name)
                for rule in nat_rules:
                    if _nat_matches_ip(rule, ip):
                        results.append({"package": pkg_name, **rule})
        return jsonify({"results": results})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)
