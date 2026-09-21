import pytest
from unittest.mock import MagicMock, patch


def _patch_config(monkeypatch):
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "10.0.0.1")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY", "10.0.0.2")
    monkeypatch.setattr("app.config.Config.CP_MDS_3", "")
    monkeypatch.setattr("app.config.Config.CP_MDS_4", "")
    monkeypatch.setattr("app.config.Config.CP_API_KEY", "test-key")
    monkeypatch.setattr("app.config.Config.CP_VERIFY_SSL", False)
    monkeypatch.setattr("app.config.Config.CP_TIMEOUT", 10)
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY_LABEL", "Primary")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY_LABEL", "Secondary")
    monkeypatch.setattr("app.config.Config.CP_MDS_3_LABEL", "")
    monkeypatch.setattr("app.config.Config.CP_MDS_4_LABEL", "")
    # Clear the SID cache so tests start clean
    monkeypatch.setattr("app.session_pool._sids", {})


def test_make_client_connects_to_primary(monkeypatch):
    _patch_config(monkeypatch)
    mock_client = MagicMock()
    with patch("app.session_pool.connect", return_value=mock_client) as mock_connect:
        from app.cp_helpers import make_client
        with make_client() as client:
            pass
    assert client is mock_client
    # connect() called with the primary host first
    assert mock_connect.call_args_list[0][0][0] == "10.0.0.1"


def test_make_client_falls_back_to_secondary(monkeypatch):
    _patch_config(monkeypatch)
    secondary_client = MagicMock()

    def _connect(host, *args, **kwargs):
        if host == "10.0.0.1":
            raise ConnectionError("primary down")
        return secondary_client

    with patch("app.session_pool.connect", side_effect=_connect):
        from app.cp_helpers import make_client
        with make_client() as client:
            result = client
    assert result is secondary_client


def test_make_client_raises_when_both_fail(monkeypatch):
    _patch_config(monkeypatch)
    with patch("app.session_pool.connect", side_effect=ConnectionError("down")), \
         patch("app.cp_helpers.time.sleep"):
        from app.cp_helpers import make_client
        with pytest.raises(ConnectionError):
            with make_client():
                pass


def test_make_client_skips_empty_primary(monkeypatch):
    _patch_config(monkeypatch)
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "")
    secondary_client = MagicMock()

    with patch("app.session_pool.connect", return_value=secondary_client) as mock_connect:
        from app.cp_helpers import make_client
        with make_client():
            pass
    # Only the secondary host should be contacted (primary skipped because it's empty)
    hosts = [c[0][0] for c in mock_connect.call_args_list]
    assert "10.0.0.1" not in hosts
    assert "10.0.0.2" in hosts


def test_get_cached_domains_initial_state():
    from app.domain_cache import get_cached_domains
    result = get_cached_domains()
    assert "domains" in result
    assert "status" in result


def test_refresh_domains_updates_cache(monkeypatch):
    _patch_config(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_domains.return_value = [{"name": "D1"}, {"name": "D2"}]
    with patch("app.session_pool.connect", return_value=mock_client):
        from app.domain_cache import refresh_domains, get_cached_domains
        refresh_domains()
    cache = get_cached_domains()
    assert cache["status"] == "ok"
    assert len(cache["domains"]) == 2


def test_refresh_domains_sets_error_on_failure(monkeypatch):
    monkeypatch.setattr("app.session_pool._sids", {})
    with patch("app.session_pool.connect", side_effect=ConnectionError("all hosts down")):
        from app.domain_cache import refresh_domains, get_cached_domains
        refresh_domains()
    assert get_cached_domains()["status"] == "error"
