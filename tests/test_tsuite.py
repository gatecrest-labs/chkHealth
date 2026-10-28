"""4tSuite integration: SSO login, group push, revocation, no-access, cross-process safety."""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.tsuite_adapter import ADAPTER_VERSION, PROTOCOL_VERSION


@pytest.fixture
def suite(tmp_path, monkeypatch):
    import app.auth as auth_mod
    import app.groups as groups_mod
    from app import create_app

    key = Ed25519PrivateKey.generate()
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key_path = tmp_path / "sso_public_key.pem"
    key_path.write_bytes(pem)
    monkeypatch.setenv("SSO_PUBLIC_KEY_PATH", str(key_path))
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    groups_mod.create_group("ops", {"members": [], "allowed_tabs": ["dashboard"]})
    app = create_app({"TESTING": True, "SECRET_KEY": "x" * 40})

    def mint(sub="alice", aud="chkhealth", **extra):
        now = int(time.time())
        claims = {"sub": sub, "aud": aud, "iss": "4tsuite", "iat": now, "nbf": now,
                  "exp": now + 60, **extra}
        return jwt.encode(claims, key, algorithm="EdDSA")

    return app, groups_mod, mint


def test_adapter_version_is_1_2_0():
    assert (ADAPTER_VERSION, PROTOCOL_VERSION) == ("1.2.0", 1)


def test_sso_login_grants_tabs_from_group(suite):
    app, groups, mint = suite
    groups.apply_group_change("alice", "ops", True)
    c = app.test_client()
    r = c.get(f"/sso/login?token={mint()}")
    assert r.status_code == 302
    assert c.get("/").status_code == 302
    with c.session_transaction() as s:
        assert s["user"] == "alice" and s["role"] == "viewer" and s["sso"] is True
        assert s["allowed_tabs"] == ["dashboard"]


def test_sso_login_rejects_bad_wrong_audience_and_service_tokens(suite):
    app, _, mint = suite
    c = app.test_client()
    for tok in ("garbage", mint(aud="4tlog"), mint(scope="manifest_read")):
        r = c.get(f"/sso/login?token={tok}")
        assert r.status_code == 302 and r.headers["Location"].endswith("/login")
        with c.session_transaction() as s:
            assert "user" not in s


def test_sso_user_without_grants_sees_no_access_not_a_redirect_loop(suite):
    app, _, mint = suite
    c = app.test_client()
    r = c.get(f"/sso/login?token={mint(sub='nobody')}")
    assert r.headers["Location"].endswith("/no-access")
    page = c.get("/no-access")
    assert page.status_code == 403 and b"no tabs assigned" in page.data
    assert c.get("/login").headers["Location"].endswith("/no-access")


def test_sso_user_never_inherits_a_same_named_local_admin(suite):
    import app.auth as auth_mod
    app, _, mint = suite
    auth_mod.add_user("alice", "pw", "admin")
    c = app.test_client()
    c.get(f"/sso/login?token={mint()}")
    assert c.get("/admin/api/users").status_code in (401, 403)
    with c.session_transaction() as s:
        assert s["role"] == "viewer"


def test_revoked_sso_session_is_dropped(suite):
    app, groups, mint = suite
    groups.apply_group_change("alice", "ops", True)
    app.extensions["tsuite_session_checker"] = lambda user, login_at: False
    c = app.test_client()
    c.get(f"/sso/login?token={mint()}")
    r = c.get("/firewalls")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_group_push_add_remove_and_unknown_group(suite, monkeypatch):
    app, groups, _ = suite
    import app.sso_verify as sv
    monkeypatch.setattr(sv, "_decode", lambda token: {"scope": "groups_push"} if token == "t" else None)
    c = app.test_client()
    h = {"Authorization": "Bearer t"}
    body = {"username": "bob", "group": "ops", "member": True}
    assert c.post("/4tsuite/groups", json=body, headers=h).status_code == 204
    assert "bob" in groups.get_group("ops")["members"]
    body["member"] = False
    assert c.post("/4tsuite/groups", json=body, headers=h).status_code == 204
    assert "bob" not in groups.get_group("ops")["members"]
    assert c.post("/4tsuite/groups", json={**body, "group": "nope"}, headers=h).status_code == 400
    assert c.post("/4tsuite/groups", json=body).status_code == 403


def test_manifest_lists_tabs_groups_and_revocations(suite, monkeypatch):
    app, _, _ = suite
    import app.sso_verify as sv
    monkeypatch.setattr(sv, "_decode", lambda token: {"scope": "manifest_read"} if token == "t" else None)
    r = app.test_client().get("/4tsuite/manifest", headers={"Authorization": "Bearer t"})
    m = r.get_json()
    assert m["app_id"] == "chkhealth"
    assert set(m["tabs"]) == {"dashboard", "firewalls", "rule_review", "device_review"}
    assert m["groups"] == ["ops"]


def test_concurrent_pushes_in_separate_processes_lose_nothing(tmp_path):
    import multiprocessing as mp
    path = tmp_path / "groups.json"
    path.write_text(json.dumps({"ops": {"members": []}}))
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_push_many, args=(str(path), i)) for i in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    members = json.loads(path.read_text())["ops"]["members"]
    assert len(members) == 4 * 25 and len(set(members)) == 4 * 25


def _push_many(path, n):
    from pathlib import Path
    import os
    os.environ.setdefault("SECRET_KEY", "x" * 40)
    import app.groups as g
    g.GROUPS_FILE = Path(path)
    for i in range(25):
        g.apply_group_change(f"u{n}-{i}", "ops", True)
