from flask import Blueprint, jsonify, render_template, request

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.security import upstream_api_error

registry.register("device_review", "Device Review", "device_review.device_review_page", icon="💻")

bp = Blueprint("device_review", __name__, url_prefix="/")

_BLADES = {
    "firewall": "Firewall",
    "vpn": "VPN",
    "ips": "IPS",
    "application-control": "App Control",
    "url-filtering": "URL Filtering",
    "anti-bot": "Anti-Bot",
    "anti-virus": "Anti-Virus",
    "threat-emulation": "Threat Emulation",
    "threat-extraction": "Threat Extraction",
    "content-awareness": "Content Awareness",
    "identity-awareness": "Identity Awareness",
    "mobile-access": "Mobile Access",
    "data-loss-prevention": "DLP",
    "anti-spam-and-email-security": "Anti-Spam",
    "qos": "QoS",
    "monitoring": "Monitoring",
    "policy-server": "Policy Server",
}


def _device_row(obj: dict, obj_type: str) -> dict:
    blades = [label for key, label in _BLADES.items() if obj.get(key) is True]
    members = obj.get("cluster-members", [])
    return {
        "name": obj.get("name", ""),
        "type": obj_type,
        "ip": obj.get("ipv4-address") or obj.get("ipv6-address") or "",
        "version": obj.get("version", ""),
        "os": obj.get("os-name", ""),
        "hardware": obj.get("hardware", ""),
        "platform": obj.get("platform", ""),
        "blades": blades,
        "policy": obj.get("fetch-policy") or [],
        "member_count": len(members),
        "comments": obj.get("comments") or "",
    }


@bp.route("/device-review")
@login_required
@tab_required("device_review")
def device_review_page():
    return render_template("device_review.html")


@bp.route("/api/device-review/summary")
@login_required
@tab_required("device_review")
def api_dr_summary():
    from app.device_version_cache import get_device_versions
    return jsonify(get_device_versions())


@bp.route("/api/device-review/refresh", methods=["POST"])
@login_required
@tab_required("device_review")
def api_dr_refresh():
    import threading
    from app.device_version_cache import refresh_device_versions
    threading.Thread(target=refresh_device_versions, daemon=True).start()
    return jsonify({"status": "refreshing"}), 202


@bp.route("/api/device-review/devices")
@login_required
@tab_required("device_review")
def api_dr_devices():
    domain = request.args.get("domain", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            gateways = client._fetch_all("show-simple-gateways", {"details-level": "full"})
            clusters = client._fetch_all("show-simple-clusters", {"details-level": "full"})
        devices = sorted(
            [_device_row(g, "Gateway") for g in gateways] +
            [_device_row(c, "Cluster") for c in clusters],
            key=lambda d: d["name"],
        )
        return jsonify({"devices": devices, "domain": domain})
    except Exception as exc:
        return upstream_api_error("device_review", exc)
