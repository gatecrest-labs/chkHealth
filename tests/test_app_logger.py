import pytest
from app.app_logger import app_log, get_log_entries, clear_log_entries, set_log_level, get_log_level


def setup_function():
    clear_log_entries()
    set_log_level("INFO")


def test_log_entry_stored():
    app_log("INFO", "test", "hello world")
    entries = get_log_entries(level=None, component=None, limit=10)
    assert len(entries) == 1
    assert entries[0]["message"] == "hello world"
    assert entries[0]["level"] == "INFO"
    assert entries[0]["component"] == "test"


def test_log_filtered_by_level():
    app_log("DEBUG", "test", "debug msg")
    app_log("INFO", "test", "info msg")
    entries = get_log_entries(level="INFO", component=None, limit=10)
    assert all(e["level"] in ("INFO", "WARN", "ERROR") for e in entries)


def test_log_filtered_by_component():
    app_log("INFO", "auth", "login")
    app_log("INFO", "other", "other msg")
    entries = get_log_entries(level=None, component="auth", limit=10)
    assert all(e["component"] == "auth" for e in entries)


def test_clear_entries():
    app_log("INFO", "test", "msg")
    clear_log_entries()
    assert get_log_entries(level=None, component=None, limit=10) == []


def test_set_log_level_filters_below():
    set_log_level("WARN")
    app_log("INFO", "test", "should not appear")
    app_log("WARN", "test", "should appear")
    entries = get_log_entries(level=None, component=None, limit=10)
    assert len(entries) == 1
    assert entries[0]["level"] == "WARN"


def test_extra_fields_stored():
    app_log("INFO", "auth", "login", username="alice", remote="1.2.3.4")
    entries = get_log_entries(level=None, component=None, limit=10)
    assert entries[0]["extra"]["username"] == "alice"
