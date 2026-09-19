import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.host_metrics._DB_PATH", tmp_path / "metrics.db")
    from app.host_metrics import init_db
    init_db()


def test_upsert_and_retrieve():
    from app.host_metrics import upsert_summary, get_history
    upsert_summary("2026-01-01", 10, 500)
    rows = get_history(days=30)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["gw_count"] == 10
    assert rows[0]["rule_count"] == 500


def test_upsert_replaces_existing_row():
    from app.host_metrics import upsert_summary, get_history
    upsert_summary("2026-01-01", 10, 500)
    upsert_summary("2026-01-01", 12, 600)
    rows = get_history(days=30)
    assert len(rows) == 1
    assert rows[0]["gw_count"] == 12
    assert rows[0]["rule_count"] == 600


def test_get_history_limits_rows():
    from app.host_metrics import upsert_summary, get_history
    for i in range(35):
        upsert_summary(f"2026-01-{i + 1:02d}", i, i * 10)
    rows = get_history(days=30)
    assert len(rows) == 30


def test_get_history_ordered_asc():
    from app.host_metrics import upsert_summary, get_history
    upsert_summary("2026-01-03", 3, 30)
    upsert_summary("2026-01-01", 1, 10)
    upsert_summary("2026-01-02", 2, 20)
    rows = get_history(days=30)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


def test_get_history_empty():
    from app.host_metrics import get_history
    assert get_history() == []
