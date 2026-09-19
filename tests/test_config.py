import pytest


def test_config_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
    monkeypatch.setenv("CP_MDS_PRIMARY", "10.1.1.1")
    monkeypatch.setenv("CP_MDS_SECONDARY", "10.1.1.2")
    monkeypatch.setenv("CP_API_KEY", "test-key")
    monkeypatch.setenv("CP_VERIFY_SSL", "false")
    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.Config.CP_MDS_PRIMARY == "10.1.1.1"
    assert cfg_mod.Config.CP_VERIFY_SSL is False


def test_app_settings_get_set(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
    import app.app_settings as s_mod
    import importlib
    monkeypatch.setattr(s_mod, "_SETTINGS_PATH", tmp_path / "app_settings.json")
    importlib.reload(s_mod)
    monkeypatch.setattr(s_mod, "_SETTINGS_PATH", tmp_path / "app_settings.json")
    s_mod.set_setting("test_key", "hello")
    assert s_mod.get_setting("test_key") == "hello"


def test_app_settings_default(tmp_path, monkeypatch):
    import app.app_settings as s_mod
    monkeypatch.setattr(s_mod, "_SETTINGS_PATH", tmp_path / "missing.json")
    result = s_mod.get_setting("nonexistent_key", default="fallback")
    assert result == "fallback"
