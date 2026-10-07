

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


def test_ldap_config_defaults(monkeypatch):
    monkeypatch.delenv("LDAP_ENABLED", raising=False)
    monkeypatch.delenv("LDAP_SERVER", raising=False)
    monkeypatch.delenv("LDAP_VERIFY_SSL", raising=False)
    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.Config.LDAP_ENABLED is False
    assert cfg_mod.Config.LDAP_SERVER == ""
    assert cfg_mod.Config.LDAP_VERIFY_SSL is True


def test_ldap_config_from_env(monkeypatch):
    monkeypatch.setenv("LDAP_ENABLED", "true")
    monkeypatch.setenv("LDAP_SERVER", "ldaps://dc01.example.com")
    monkeypatch.setenv("LDAP_VERIFY_SSL", "false")
    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.Config.LDAP_ENABLED is True
    assert cfg_mod.Config.LDAP_SERVER == "ldaps://dc01.example.com"
    assert cfg_mod.Config.LDAP_VERIFY_SSL is False


def test_tacacs_config_defaults(monkeypatch):
    monkeypatch.delenv("TACACS_ENABLED", raising=False)
    monkeypatch.delenv("TACACS_PORT", raising=False)
    monkeypatch.delenv("TACACS_PRIV_ADMIN", raising=False)
    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.Config.TACACS_ENABLED is False
    assert cfg_mod.Config.TACACS_PORT == 49
    assert cfg_mod.Config.TACACS_PRIV_ADMIN == "15"


def test_radius_config_defaults(monkeypatch):
    monkeypatch.delenv("RADIUS_ENABLED", raising=False)
    monkeypatch.delenv("RADIUS_PORT", raising=False)
    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.Config.RADIUS_ENABLED is False
    assert cfg_mod.Config.RADIUS_PORT == 1812
