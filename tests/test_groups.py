import pytest


@pytest.fixture
def groups_file(tmp_path, monkeypatch):
    import app.groups as g_mod
    path = tmp_path / "groups.json"
    monkeypatch.setattr(g_mod, "GROUPS_FILE", path)
    return path


def test_create_and_list(groups_file):
    from app.groups import create_group, list_groups
    create_group("ops", {
        "members": ["alice"],
        "allowed_tabs": ["dashboard"],
        "domain_restrict": False,
        "allowed_domains": [],
    })
    groups = list_groups()
    assert len(groups) == 1
    assert groups[0]["name"] == "ops"


def test_get_group(groups_file):
    from app.groups import create_group, get_group
    create_group("team", {"members": ["bob"], "allowed_tabs": [], "domain_restrict": False, "allowed_domains": []})
    g = get_group("team")
    assert g is not None
    assert "bob" in g["members"]


def test_update_group(groups_file):
    from app.groups import create_group, update_group, get_group
    create_group("grp", {"members": [], "allowed_tabs": ["dashboard"], "domain_restrict": False, "allowed_domains": []})
    update_group("grp", {"members": ["carol"], "allowed_tabs": ["firewalls"], "domain_restrict": False, "allowed_domains": []})
    g = get_group("grp")
    assert "carol" in g["members"]
    assert "firewalls" in g["allowed_tabs"]


def test_delete_group(groups_file):
    from app.groups import create_group, delete_group, get_group
    create_group("temp", {"members": [], "allowed_tabs": [], "domain_restrict": False, "allowed_domains": []})
    assert delete_group("temp") is True
    assert get_group("temp") is None


def test_delete_nonexistent(groups_file):
    from app.groups import delete_group
    assert delete_group("ghost") is False


def test_get_allowed_tabs_via_membership(groups_file):
    from app.groups import create_group, get_allowed_tabs, KNOWN_TABS
    KNOWN_TABS.update({"dashboard": "Dashboard", "firewalls": "Firewalls"})
    create_group("net", {"members": ["dave"], "allowed_tabs": ["dashboard"], "domain_restrict": False, "allowed_domains": []})
    tabs = get_allowed_tabs("dave", ad_groups=[], role="viewer")
    assert "dashboard" in tabs


def test_admin_gets_all_tabs(groups_file):
    from app.groups import get_allowed_tabs, KNOWN_TABS
    KNOWN_TABS.update({"dashboard": "Dashboard", "firewalls": "Firewalls"})
    tabs = get_allowed_tabs("admin", ad_groups=[], role="admin")
    assert "dashboard" in tabs
    assert "firewalls" in tabs


def test_domain_unrestricted(groups_file):
    from app.groups import create_group, get_allowed_domains
    create_group("open", {"members": ["eve"], "allowed_tabs": [], "domain_restrict": False, "allowed_domains": []})
    result = get_allowed_domains("eve", ad_groups=[])
    assert result is None  # None = unrestricted


def test_domain_restricted(groups_file):
    from app.groups import create_group, get_allowed_domains
    create_group("restricted", {
        "members": ["frank"],
        "allowed_tabs": [],
        "domain_restrict": True,
        "allowed_domains": ["domain-a"],
    })
    result = get_allowed_domains("frank", ad_groups=[])
    assert result == ["domain-a"]


def test_user_can_access_domain(groups_file):
    from app.groups import create_group, user_can_access_domain
    create_group("dc1", {
        "members": ["grace"],
        "allowed_tabs": [],
        "domain_restrict": True,
        "allowed_domains": ["domain-a"],
    })
    assert user_can_access_domain("grace", "domain-a", ad_groups=[]) is True
    assert user_can_access_domain("grace", "domain-b", ad_groups=[]) is False
