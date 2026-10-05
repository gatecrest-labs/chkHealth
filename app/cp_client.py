from __future__ import annotations

import warnings

import requests
import urllib3


class CPAPIError(Exception):
    def __init__(self, message: str, command: str, data: dict):
        super().__init__(message)
        self.command = command
        self.data = data


class CPClient:
    def __init__(
        self,
        host: str,
        api_key: str,
        verify_ssl: bool = False,
        timeout: int = 30,
    ):
        self.host = host
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._sid: str | None = None
        self._domain: str | None = None
        self._session = requests.Session()
        if not verify_ssl:
            warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

    def _url(self, command: str) -> str:
        return f"https://{self.host}/web_api/{command}"

    def login(self, domain: str | None = None) -> None:
        self._domain = domain
        payload: dict = {"api-key": self._api_key}
        if domain:
            payload["domain"] = domain
        resp = self._session.post(
            self._url("login"),
            json=payload,
            headers={"Content-Type": "application/json"},
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise CPAPIError(data.get("message", "Login failed"), "login", data)
        self._sid = data["sid"]

    def logout(self) -> None:
        if not self._sid:
            return
        try:
            self._session.post(
                self._url("logout"),
                json={},
                headers={"Content-Type": "application/json", "X-chkp-sid": self._sid},
                verify=self._verify_ssl,
                timeout=self._timeout,
            )
        except Exception:
            pass
        finally:
            self._sid = None

    def call(self, command: str, payload: dict | None = None) -> dict:
        resp = self._session.post(
            self._url(command),
            json=payload or {},
            headers={
                "Content-Type": "application/json",
                "X-chkp-sid": self._sid or "",
            },
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise CPAPIError(data.get("message", "API call failed"), command, data)
        return data

    def _fetch_all(self, command: str, extra: dict | None = None, key: str = "objects") -> list[dict]:
        results: list[dict] = []
        offset = 0
        limit = 500
        while True:
            data = self.call(command, {"limit": limit, "offset": offset, **(extra or {})})
            objects = data.get(key, [])
            if not objects:
                break
            results.extend(objects)
            if len(results) >= data.get("total", len(results)):
                break
            offset += len(objects)
        return results

    def get_domains(self) -> list[dict]:
        return self._fetch_all("show-domains")

    def get_api_version(self) -> dict:
        return self.call("show-api-versions")

    def get_gateways(self) -> list[dict]:
        return self._fetch_all("show-simple-gateways")

    def get_clusters(self, details_level: str = "uid") -> list[dict]:
        extra = {"details-level": details_level} if details_level != "uid" else {}
        return self._fetch_all("show-simple-clusters", extra)

    def get_packages(self) -> list[dict]:
        return self._fetch_all("show-packages", key="packages")

    def get_access_layers(self, package: str) -> list[dict]:
        """Return the access layers defined in a policy package."""
        resp = self.call("show-package", {"name": package})
        return resp.get("access-layers", [])

    def get_access_rulebase(self, layer: str, details_level: str = "uid") -> list[dict]:
        """Fetch rules from an access layer name (not the package name)."""
        extra: dict = {"name": layer}
        if details_level != "uid":
            extra["details-level"] = details_level
        return self._fetch_all("show-access-rulebase", extra, key="rulebase")

    def get_nat_rulebase(self, package: str) -> list[dict]:
        return self._fetch_all("show-nat-rulebase", {"name": package}, key="rulebase")

    def get_objects(self, name_filter: str) -> list[dict]:
        return self._fetch_all(
            "show-objects",
            {"filter": name_filter, "type": "object", "limit": 200},
            key="objects",
        )

    def get_gateway_full(self, name: str) -> dict:
        return self.call("show-simple-gateway", {"name": name})

    def get_cluster_full(self, name: str) -> dict:
        return self.call("show-simple-cluster", {"name": name, "details-level": "full"})

    # ── Gaia API proxy helpers ────────────────────────────────────────────────

    def gaia_call(
        self, command: str, target: str,
        payload: dict | None = None,
        api_version: str = "1.6",
    ) -> dict:
        """Call a Gaia API command via the management server proxy.

        The management server forwards the call to the target gateway over SIC.
        No per-gateway credentials are required — uses the existing session.
        """
        full_payload = {"target": target, **(payload or {})}
        # Gaia calls use a separate timeout (GAIA_TIMEOUT config, default 15s)
        # rather than the management API timeout to avoid long hangs on SIC failures.
        from app.config import Config
        original_timeout = self._timeout
        self._timeout = Config.GAIA_TIMEOUT
        try:
            return self.call(f"gaia-api/v{api_version}/{command}", full_payload)
        finally:
            self._timeout = original_timeout

    def get_gaia_interfaces(self, target: str) -> dict:
        """Return interface lists grouped by type.

        Calls show-physical-interfaces, show-vlan-interfaces, show-bond-interfaces,
        and show-loopback-interfaces. Any call that fails returns an empty list for
        its type (older gateways may not support VLAN/bond commands).
        """
        def _safe_objects(command: str) -> list[dict]:
            try:
                return self.gaia_call(command, target).get("objects", [])
            except (CPAPIError, requests.HTTPError):
                return []

        return {
            "physical": _safe_objects("show-physical-interfaces"),
            "vlan": _safe_objects("show-vlan-interfaces"),
            "bond": _safe_objects("show-bond-interfaces"),
            "loopback": _safe_objects("show-loopback-interfaces"),
        }

    def get_gaia_routing(self, target: str) -> list[dict]:
        """Return the full active routing table from show-routes."""
        return self.gaia_call("show-routes", target).get("objects", [])

    def get_gaia_bgp(self, target: str) -> dict:
        """Return BGP groups and per-peer details (R82+ / Gaia API 1.7)."""
        groups_raw = self.gaia_call("show-bgp-groups", target, api_version="1.7").get("objects", [])
        peers: list[dict] = []
        try:
            summary = self.gaia_call("show-bgp-summary", target, api_version="1.7")
            for peer_entry in summary.get("peers", []):
                peer_ip = peer_entry.get("peer") or peer_entry.get("neighbor")
                if not peer_ip:
                    continue
                try:
                    detail = self.gaia_call(
                        "show-bgp-peer", target,
                        payload={"peer": peer_ip},
                        api_version="1.7",
                    )
                    peers.append(detail)
                except (CPAPIError, requests.HTTPError):
                    peers.append(peer_entry)
        except (CPAPIError, requests.HTTPError):
            pass  # groups already fetched; peers stay empty
        return {"groups": groups_raw, "peers": peers}

    # ── Config-Delta helpers ──────────────────────────────────────────────────

    def get_gateways_with_status(self) -> list[dict]:
        """Return all gateways with normalised install_status.

        FIELD VERIFICATION REQUIRED: Inspect a live `show-gateways-and-servers`
        response in your CP environment and confirm the field paths below match.
        Common variations by CP version:
          - ipv4-address vs ip-address
          - policy.access-policy-name vs policy.policy-name
          - policy.policy-installation-status.overall-installation-status
            may be absent on older R80 builds (falls back to "unknown")
        """
        raw = self._fetch_all(
            "show-gateways-and-servers", {"details-level": "full"}
        )
        return [self._normalize_gateway(gw) for gw in raw]

    def _normalize_gateway(self, gw: dict) -> dict:
        ip = gw.get("ipv4-address") or gw.get("ip-address", "")
        policy = gw.get("policy") or {}
        pkg = (
            policy.get("access-policy-name")
            or policy.get("policy-name", "")
        )
        install_info = policy.get("policy-installation-status") or {}
        overall = str(
            install_info.get("overall-installation-status", "")
        ).lower()
        if overall == "succeeded":
            status = "insync"
        elif overall in ("failed", "not installed", "partially installed"):
            status = "pending"
        elif overall:
            status = "pending"
        else:
            status = "unknown"
        return {
            "name": gw.get("name", ""),
            "ip": ip,
            "policy_package": pkg,
            "install_status": status,
        }

    def get_pending_changes(self, from_days: int = 30) -> dict:
        """Return structured pending changes from show-changes.

        FIELD VERIFICATION REQUIRED: Inspect a live `show-changes` response
        in your CP environment. The response key containing the list of sessions
        is typically "changelog" but may be "objects" or "changes" depending on
        CP version. Each session entry contains a "changes" list of modified
        objects. Adjust _extract_session_objects() if the shape differs.
        """
        from datetime import datetime, timezone, timedelta
        from_date = (
            datetime.now(timezone.utc) - timedelta(days=from_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = self.call("show-changes", {"from-date": from_date, "details-level": "full"})
        sessions = (
            data.get("changelog")
            or data.get("changes")
            or data.get("objects")
            or []
        )
        summary = {
            "access_rules": 0, "address_objects": 0, "nat_rules": 0,
            "services": 0, "system": 0, "other": 0,
        }
        changes: list[dict] = []
        for session in sessions:
            objects = self._extract_session_objects(session)
            for obj in objects:
                category = self._classify_change(obj)
                summary[category] += 1
                changes.append({
                    "category": category,
                    "change_type": str(obj.get("operation", "modify")).lower(),
                    "name": obj.get("name") or obj.get("uid", ""),
                    "properties": self._extract_properties(obj, category),
                })
        return {"summary": summary, "changes": changes}

    def _extract_session_objects(self, session: dict) -> list[dict]:
        # session may be a list of objects directly, or a dict with a "changes" key
        if isinstance(session, list):
            return session
        return session.get("changes", [])

    def _classify_change(self, obj: dict) -> str:
        obj_type = str(obj.get("type", "")).lower()
        if "access-rule" in obj_type or "access-layer" in obj_type:
            return "access_rules"
        if obj_type in ("host", "network", "address-range", "group",
                        "wildcard", "dns-domain", "multicast-address-range",
                        "address-range-v6", "network-v6", "group-with-exclusion"):
            return "address_objects"
        if "nat-rule" in obj_type:
            return "nat_rules"
        if "service" in obj_type or "service-group" in obj_type:
            return "services"
        if obj_type.startswith("simple-gateway") or obj_type.startswith("simple-cluster"):
            return "system"
        return "other"

    def _extract_properties(self, obj: dict, category: str) -> dict:
        props: dict = {}
        if category == "access_rules":
            for k in ("source", "destination", "service", "action", "comments"):
                if k in obj:
                    v = obj[k]
                    props[k] = v if isinstance(v, str) else str(v)
        elif category == "address_objects":
            for k in ("ipv4-address", "subnet4", "ipv4-mask-length", "ipv4-address-first"):
                if k in obj:
                    props[k] = str(obj[k])
        return props

    def __enter__(self) -> "CPClient":
        self.login(domain=self._domain)
        return self

    def __exit__(self, *args) -> None:
        self.logout()
