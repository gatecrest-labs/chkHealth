from flask import Blueprint, jsonify, render_template, request, session

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.security import upstream_api_error

registry.register("firewalls", "Firewalls", "firewalls.firewalls_page", icon="🔥")

bp = Blueprint("firewalls", __name__, url_prefix="/")


@bp.route("/firewalls")
@login_required
@tab_required("firewalls")
def firewalls_page():
    return render_template("firewalls.html")


@bp.route("/api/firewalls/domains")
@login_required
@tab_required("firewalls", "rule_review")
def api_firewalls_domains():
    from app.domain_cache import get_cached_domains
    from app.groups import get_allowed_domains

    cached = get_cached_domains()
    all_domains = [d["name"] for d in cached.get("domains", [])]

    role = session.get("role", "viewer")
    if role == "admin":
        return jsonify({"domains": ["Global"] + sorted(all_domains)})

    allowed = get_allowed_domains(
        session.get("user", ""),
        ad_groups=session.get("ad_groups", []),
    )
    if allowed is None:
        domain_list = sorted(all_domains)
    else:
        domain_list = sorted(d for d in all_domains if d in allowed)
    return jsonify({"domains": ["Global"] + domain_list})


@bp.route("/api/firewalls/gateways")
@login_required
@tab_required("firewalls")
def api_firewalls_gateways():
    domain = request.args.get("domain", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            gateways = sorted(
                client._fetch_all("show-simple-gateways", {"details-level": "full"}),
                key=lambda g: g.get("name", ""),
            )
            clusters = sorted(
                client._fetch_all("show-simple-clusters", {"details-level": "full"}),
                key=lambda c: c.get("name", ""),
            )
        return jsonify({"gateways": gateways, "clusters": clusters, "domain": domain})
    except Exception as exc:
        return upstream_api_error("firewalls", exc)


@bp.route("/api/firewalls/gateway")
@login_required
@tab_required("firewalls")
def api_firewalls_gateway():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    obj_type = request.args.get("type", "").strip().lower()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if obj_type not in ("gateway", "cluster"):
        return jsonify({"error": "type must be 'gateway' or 'cluster'"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            if obj_type == "gateway":
                details = client.get_gateway_full(name)
            else:
                details = client.get_cluster_full(name)
        return jsonify(details)
    except Exception as exc:
        return upstream_api_error("firewalls", exc)
