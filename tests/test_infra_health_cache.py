import pytest
from unittest.mock import MagicMock, patch


def _patch_config(monkeypatch):
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "10.0.0.1")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY", "10.0.0.2")
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY_LABEL", "MDS Primary")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY_LABEL", "MDS Secondary")
    monkeypatch.setattr("app.config.Config.CP_MLS_1", "10.0.1.1")
    monkeypatch.setattr("app.config.Config.CP_MLS_2", "10.0.1.2")
    monkeypatch.setattr("app.config.Config.CP_MLS_1_LABEL", "MLS 1")
    monkeypatch.setattr("app.config.Config.CP_MLS_2_LABEL", "MLS 2")
    monkeypatch.setattr("app.config.Config.CP_API_KEY", "key")
    monkeypatch.setattr("app.config.Config.CP_VERIFY_SSL", False)
    monkeypatch.setattr("app.config.Config.CP_TIMEOUT", 10)


def _mds_cm(version="R81.20"):
    client = MagicMock()
    client.get_api_version.return_value = {"current-version": version, "success": True}
    client.call.return_value = {"success": True}
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, client


def test_get_infra_health_initial_state():
    from app.infra_health_cache import get_infra_health
    result = get_infra_health()
    assert "servers" in result
    assert "last_updated" in result


def test_mds_healthy_on_successful_connect(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm("R81.20")
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection"):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mds = [s for s in get_infra_health()["servers"] if s["type"] == "MDS"]
    assert len(mds) == 2
    assert all(s["status"] == "healthy" for s in mds)
    assert mds[0]["version"] == "R81.20"


def test_mds_unreachable_on_connection_error(monkeypatch):
    _patch_config(monkeypatch)
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("down")
    with patch("app.infra_health_cache.make_client", return_value=bad_cm), \
         patch("app.infra_health_cache.socket.create_connection"):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mds = [s for s in get_infra_health()["servers"] if s["type"] == "MDS"]
    assert all(s["status"] == "unreachable" for s in mds)


def test_mls_healthy_on_tcp_connect(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm()
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection", return_value=MagicMock()):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mls = [s for s in get_infra_health()["servers"] if s["type"] == "MLS"]
    assert all(s["status"] == "healthy" for s in mls)


def test_mls_unreachable_on_tcp_failure(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm()
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection",
               side_effect=OSError("refused")):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    mls = [s for s in get_infra_health()["servers"] if s["type"] == "MLS"]
    assert all(s["status"] == "unreachable" for s in mls)


def test_server_entry_has_required_fields(monkeypatch):
    _patch_config(monkeypatch)
    cm, _ = _mds_cm()
    with patch("app.infra_health_cache.make_client", return_value=cm), \
         patch("app.infra_health_cache.socket.create_connection"):
        from app.infra_health_cache import refresh_infra_health, get_infra_health
        refresh_infra_health()
    for s in get_infra_health()["servers"]:
        for field in ("label", "host", "type", "status", "hostname",
                      "version", "serial", "ha_role"):
            assert field in s, f"Missing field {field!r}"
