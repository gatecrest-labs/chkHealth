from flask import Blueprint, jsonify, render_template, request
from markupsafe import Markup

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.security import upstream_api_error

bp = Blueprint("firewall_detail", __name__, url_prefix="/")

# ── Overview renderer ─────────────────────────────────────────────────────────

_BLADE_LABELS = {
    "firewall": "Firewall", "vpn": "VPN", "ips": "IPS",
    "application-control": "App Control", "url-filtering": "URL Filtering",
    "anti-bot": "Anti-Bot", "anti-virus": "Anti-Virus",
    "threat-emulation": "Threat Emulation", "threat-extraction": "Threat Extraction",
    "content-awareness": "Content Awareness", "identity-awareness": "Identity Awareness",
    "mobile-access": "Mobile Access", "data-loss-prevention": "DLP",
    "anti-spam-and-email-security": "Anti-Spam & Email", "qos": "QoS",
    "monitoring": "Monitoring",
}


def _render_overview(obj: dict, obj_type: str) -> str:
    from markupsafe import escape as e
    members = obj.get("cluster-members") or []
    is_cluster = len(members) > 0
    sic = obj.get("sic-state", "")

    rows = [
        ("Name", obj.get("name", "")),
        ("IPv4 Address", obj.get("ipv4-address", "")),
        ("Version", obj.get("version", "")),
        ("OS", obj.get("os-name", "")),
        ("Hardware", obj.get("hardware", "")),
        ("Platform", obj.get("platform", "")),
    ]
    if not is_cluster:
        rows += [("SIC State", sic), ("SIC Name", obj.get("sic-name", ""))]
    rows.append(("Cluster Mode", obj.get("cluster-mode", "")))
    rows.append(("Comments", obj.get("comments", "")))

    html = '<table class="data-table" style="margin-bottom:1rem"><tbody>'
    for label, val in rows:
        html += f'<tr><td style="color:var(--text-muted);width:40%;font-size:.82rem">{e(label)}</td><td>{e(str(val or ""))}</td></tr>'
    html += "</tbody></table>"

    if is_cluster:
        sorted_members = sorted(members, key=lambda m: m.get("priority", 99))
        any_down = any((m.get("sic-state") or "").lower() != "communicating" for m in sorted_members)
        if any_down:
            html += '<div class="cluster-warn-banner">&#9888; One or more cluster members are not communicating</div>'
        html += '<strong style="font-size:.85rem;display:block;margin-bottom:.4rem">HA Cluster Members</strong>'
        html += '<table class="data-table" style="margin-bottom:1rem;font-size:.82rem"><thead><tr><th>Priority</th><th>Name</th><th>IP</th><th>SIC</th></tr></thead><tbody>'
        for m in sorted_members:
            msic = m.get("sic-state", "unknown")
            down = msic.lower() != "communicating"
            cls = "badge-sic-bad" if down else "badge-sic-ok"
            html += (
                f'<tr{"  class=\"member-down\"" if down else ""}>'
                f'<td style="text-align:center">{e(str(m.get("priority",""))  )}</td>'
                f'<td>{"&#9888; " if down else ""}{e(m.get("name",""))}</td>'
                f'<td>{e(m.get("ip-address") or m.get("ipv4-address",""))}</td>'
                f'<td><span class="badge {cls}">{e(msic)}</span></td></tr>'
            )
        html += "</tbody></table>"

    pkgs = obj.get("fetch-policy") or []
    if pkgs:
        html += '<strong style="font-size:.85rem">Installed Policy</strong><ul style="margin:.4rem 0 1rem;padding-left:1.2rem;font-size:.875rem">'
        for p in pkgs:
            html += f"<li>{e(p)}</li>"
        html += "</ul>"

    active_blades = [k for k in _BLADE_LABELS if obj.get(k) is True]
    if active_blades:
        html += '<strong style="font-size:.85rem">Active Software Blades</strong>'
        html += '<ul style="margin:.4rem 0 0;padding-left:1.2rem;font-size:.875rem;columns:2">'
        for b in active_blades:
            html += f"<li>{e(_BLADE_LABELS[b])}</li>"
        html += "</ul>"

    return html

# ── Version gate helpers ──────────────────────────────────────────────────────

_PROTO_MAP = {
    "S": "static", "O": "ospf", "B": "bgp",
    "C": "connected", "K": "kernel", "A": "aggregate",
    "D": "direct", "R": "rip",
}


def _supports_routing(version: str) -> bool:
    v = (version or "").strip().upper()
    return v.startswith("R82") or v == "R81.20"


def _supports_bgp_peers(version: str) -> bool:
    return (version or "").strip().upper().startswith("R82")


def _gaia_target(obj: dict, obj_type: str) -> tuple[str | None, str | None]:
    """Return (gaia_target_name, display_member_name).

    For gateways: (gateway_name, None).
    For clusters: (active_member_name, active_member_name) where the active
    member is the highest-priority (lowest priority number) member with
    sic-state == 'communicating'. Returns (None, None) if no active member.
    """
    if obj_type == "gateway":
        return obj["name"], None
    members = sorted(
        obj.get("cluster-members", []),
        key=lambda m: m.get("priority", 99),
    )
    for m in members:
        if (m.get("sic-state") or "").lower() == "communicating":
            return m["name"], m["name"]
    return None, None


def _normalize_routes(raw: list[dict]) -> tuple[list[dict], dict]:
    """Normalise Gaia route objects and compute protocol_counts."""
    routes = []
    counts: dict[str, int] = {}
    for r in raw:
        nexthops = r.get("nexthop") or []
        nexthop = nexthops[0].get("gateway", "") if nexthops else ""
        proto = _PROTO_MAP.get(str(r.get("type", "")).upper(), "other")
        counts[proto] = counts.get(proto, 0) + 1
        routes.append({
            "destination": r.get("dest", ""),
            "mask_length": r.get("mask-length", 0),
            "nexthop": nexthop,
            "interface": r.get("ifname", ""),
            "protocol": proto,
            "metric": r.get("metric", 0),
            "rank": r.get("rank", 0),
        })
    return routes, counts


# ── Detail page ───────────────────────────────────────────────────────────────

@bp.route("/firewalls/gateway")
@login_required
@tab_required("firewalls")
def firewall_detail_page():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    obj_type = request.args.get("type", "").strip().lower()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    if obj_type not in ("gateway", "cluster"):
        return jsonify({"error": "type must be 'gateway' or 'cluster'"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            if obj_type == "gateway":
                obj = client.get_gateway_full(name)
            else:
                obj = client.get_cluster_full(name)
    except Exception as exc:
        return upstream_api_error("firewalls", exc)
    return render_template(
        "firewall_detail.html",
        obj=obj,
        obj_type=obj_type,
        domain=domain,
        _overview_html=Markup(_render_overview(obj, obj_type)),
    )


# ── Interfaces API ────────────────────────────────────────────────────────────

@bp.route("/api/firewalls/gateway/interfaces")
@login_required
@tab_required("firewalls")
def api_gateway_interfaces():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    obj_type = request.args.get("type", "").strip().lower()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    if obj_type not in ("gateway", "cluster"):
        return jsonify({"error": "type must be 'gateway' or 'cluster'"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            if obj_type == "gateway":
                obj = client.get_gateway_full(name)
            else:
                obj = client.get_cluster_full(name)
            gaia_target, member_name = _gaia_target(obj, obj_type)
            if gaia_target is None:
                return jsonify({
                    "available": False,
                    "reason": "no_active_member",
                    "physical": [], "vlan": [], "bond": [], "loopback": [],
                })
            ifaces = client.get_gaia_interfaces(gaia_target)
        return jsonify({
            "available": True,
            "target_member": member_name,
            **ifaces,
        })
    except Exception as exc:
        return upstream_api_error("firewalls", exc)


# ── Routing API ───────────────────────────────────────────────────────────────

@bp.route("/api/firewalls/gateway/routing")
@login_required
@tab_required("firewalls")
def api_gateway_routing():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    obj_type = request.args.get("type", "").strip().lower()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    if obj_type not in ("gateway", "cluster"):
        return jsonify({"error": "type must be 'gateway' or 'cluster'"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            if obj_type == "gateway":
                obj = client.get_gateway_full(name)
            else:
                obj = client.get_cluster_full(name)
            version = obj.get("version", "")
            if not _supports_routing(version):
                return jsonify({
                    "available": False,
                    "reason": "requires_r81_20",
                    "current_version": version,
                })
            gaia_target, member_name = _gaia_target(obj, obj_type)
            if gaia_target is None:
                return jsonify({
                    "available": False,
                    "reason": "no_active_member",
                    "routes": [], "total": 0, "protocol_counts": {},
                })
            raw = client.get_gaia_routing(gaia_target)
        routes, protocol_counts = _normalize_routes(raw)
        return jsonify({
            "available": True,
            "target_member": member_name,
            "routes": routes,
            "total": len(routes),
            "protocol_counts": protocol_counts,
        })
    except Exception as exc:
        return upstream_api_error("firewalls", exc)


# ── Protocols API ─────────────────────────────────────────────────────────────

@bp.route("/api/firewalls/gateway/protocols")
@login_required
@tab_required("firewalls")
def api_gateway_protocols():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    obj_type = request.args.get("type", "").strip().lower()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    if obj_type not in ("gateway", "cluster"):
        return jsonify({"error": "type must be 'gateway' or 'cluster'"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            if obj_type == "gateway":
                obj = client.get_gateway_full(name)
            else:
                obj = client.get_cluster_full(name)
            version = obj.get("version", "")
            gaia_target, member_name = _gaia_target(obj, obj_type)

            bgp: dict
            if not _supports_bgp_peers(version):
                bgp = {"available": False, "reason": "requires_r82"}
            elif gaia_target is None:
                bgp = {"available": False, "reason": "no_active_member"}
            else:
                bgp_data = client.get_gaia_bgp(gaia_target)
                bgp = {
                    "available": True,
                    "groups": bgp_data.get("groups", []),
                    "peers": bgp_data.get("peers", []),
                }

        return jsonify({
            "target_member": member_name,
            "bgp": bgp,
            "ospf": {
                "available": True,
                "note": (
                    "OSPF route count is shown in the Routing Table tab "
                    "(filter by Protocol: OSPF). Live neighbor state requires "
                    "running 'clish -c show ospf neighbors all' on the gateway."
                ),
            },
        })
    except Exception as exc:
        return upstream_api_error("firewalls", exc)
