import pytest
from unittest.mock import MagicMock, patch


def _patch_config(monkeypatch):
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "10.0.0.1")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY", "10.0.0.2")
    monkeypatch.setattr("app.config.Config.CP_API_KEY", "test-key")
    monkeypatch.setattr("app.config.Config.CP_VERIFY_SSL", False)
    monkeypatch.setattr("app.config.Config.CP_TIMEOUT", 10)
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY_LABEL", "Primary")
    monkeypatch.setattr("app.config.Config.CP_MDS_SECONDARY_LABEL", "Secondary")


def test_make_client_connects_to_primary(monkeypatch):
    _patch_config(monkeypatch)
    mock_instance = MagicMock()
    mock_instance.login.return_value = None
    with patch("app.cp_helpers.CPClient", return_value=mock_instance):
        from app.cp_helpers import make_client
        with make_client():
            pass
    mock_instance.login.assert_called_once()
    mock_instance.logout.assert_called_once()


def test_make_client_falls_back_to_secondary(monkeypatch):
    _patch_config(monkeypatch)
    primary = MagicMock()
    primary.login.side_effect = ConnectionError("primary down")
    secondary = MagicMock()
    secondary.login.return_value = None
    with patch("app.cp_helpers.CPClient", side_effect=[primary, secondary]):
        from app.cp_helpers import make_client
        with make_client() as client:
            result = client
    assert result is secondary


def test_make_client_raises_when_both_fail(monkeypatch):
    _patch_config(monkeypatch)
    bad = MagicMock()
    bad.login.side_effect = ConnectionError("down")
    with patch("app.cp_helpers.CPClient", side_effect=[bad, bad]):
        from app.cp_helpers import make_client
        with pytest.raises(ConnectionError):
            with make_client():
                pass


def test_make_client_skips_empty_primary(monkeypatch):
    _patch_config(monkeypatch)
    monkeypatch.setattr("app.config.Config.CP_MDS_PRIMARY", "")
    secondary = MagicMock()
    secondary.login.return_value = None
    with patch("app.cp_helpers.CPClient", return_value=secondary):
        from app.cp_helpers import make_client
        with make_client():
            pass
    secondary.login.assert_called_once()


def test_get_cached_domains_initial_state():
    from app.domain_cache import get_cached_domains
    result = get_cached_domains()
    assert "domains" in result
    assert "status" in result


def test_refresh_domains_updates_cache(monkeypatch):
    _patch_config(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_domains.return_value = [{"name": "D1"}, {"name": "D2"}]
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_client)
    mock_cm.__exit__ = MagicMock(return_value=False)
    with patch("app.domain_cache.make_client", return_value=mock_cm):
        from app.domain_cache import refresh_domains, get_cached_domains
        refresh_domains()
    cache = get_cached_domains()
    assert cache["status"] == "ok"
    assert len(cache["domains"]) == 2


def test_refresh_domains_sets_error_on_failure():
    mock_cm = MagicMock()
    mock_cm.__enter__.side_effect = ConnectionError("all hosts down")
    with patch("app.domain_cache.make_client", return_value=mock_cm):
        from app.domain_cache import refresh_domains, get_cached_domains
        refresh_domains()
    assert get_cached_domains()["status"] == "error"
