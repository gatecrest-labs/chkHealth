# Domain access: effective allowed set is UNION of allowed_domains across all
# restricted groups the user belongs to, OR unrestricted if any group has
# domain_restrict=False. No group membership → no domain access.

import json
import threading
from pathlib import Path

GROUPS_FILE = Path(__file__).parent.parent / "groups.json"
_lock = threading.Lock()

KNOWN_TABS: dict[str, str] = {}


def _load() -> dict:
    if not GROUPS_FILE.exists():
        return {}
    with GROUPS_FILE.open() as f:
        return json.load(f)


def _save(data: dict) -> None:
    from app.atomic_io import atomic_write_json
    atomic_write_json(GROUPS_FILE, data)


def _group_to_dict(name: str, g: dict) -> dict:
    return {
        "name": name,
        "members": g.get("members", []),
        "allowed_tabs": g.get("allowed_tabs", []),
        "domain_restrict": bool(g.get("domain_restrict", False)),
        "allowed_domains": g.get("allowed_domains", []),
    }


def list_groups() -> list[dict]:
    with _lock:
        groups = _load()
    return [_group_to_dict(name, g) for name, g in groups.items()]


def get_group(name: str) -> dict | None:
    with _lock:
        groups = _load()
    g = groups.get(name)
    return _group_to_dict(name, g) if g is not None else None


def create_group(name: str, data: dict) -> None:
    with _lock:
        groups = _load()
        groups[name] = {
            "members": data.get("members", []),
            "allowed_tabs": data.get("allowed_tabs", []),
            "domain_restrict": bool(data.get("domain_restrict", False)),
            "allowed_domains": data.get("allowed_domains", []),
        }
        _save(groups)


def update_group(name: str, data: dict) -> None:
    with _lock:
        groups = _load()
        existing = groups.get(name, {})
        existing.update({
            "members": data.get("members", existing.get("members", [])),
            "allowed_tabs": data.get("allowed_tabs", existing.get("allowed_tabs", [])),
            "domain_restrict": bool(data.get("domain_restrict", existing.get("domain_restrict", False))),
            "allowed_domains": data.get("allowed_domains", existing.get("allowed_domains", [])),
        })
        groups[name] = existing
        _save(groups)


def delete_group(name: str) -> bool:
    with _lock:
        groups = _load()
        if name not in groups:
            return False
        del groups[name]
        _save(groups)
    return True


def _user_groups(username: str, ad_groups: list | None = None) -> list[dict]:
    all_groups = _load()
    result = []
    for name, g in all_groups.items():
        if username in g.get("members", []):
            result.append(_group_to_dict(name, g))
    return result


def get_allowed_tabs(username: str, ad_groups: list | None = None, role: str = "viewer") -> set[str]:
    if role == "admin":
        return set(KNOWN_TABS.keys())
    with _lock:
        user_grps = _user_groups(username, ad_groups)
    tabs: set[str] = set()
    for g in user_grps:
        tabs.update(g["allowed_tabs"])
    return tabs


def get_allowed_domains(username: str, ad_groups: list | None = None) -> list[str] | None:
    with _lock:
        user_grps = _user_groups(username, ad_groups)
    if not user_grps:
        return []
    if any(not g["domain_restrict"] for g in user_grps):
        return None
    domains: set[str] = set()
    for g in user_grps:
        domains.update(g["allowed_domains"])
    return sorted(domains)


def user_can_access_domain(username: str, domain: str, ad_groups: list | None = None) -> bool:
    allowed = get_allowed_domains(username, ad_groups)
    if allowed is None:
        return True
    return domain in allowed
