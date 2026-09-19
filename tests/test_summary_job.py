import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.host_metrics._DB_PATH", tmp_path / "metrics.db")
    from app.host_metrics import init_db
    init_db()


def _make_mock_client(gw_count=2, cluster_count=1, package_names=None, rule_count=5):
    client = MagicMock()
    client.get_gateways.return_value = [{"name": f"gw{i}"} for i in range(gw_count)]
    client.get_clusters.return_value = [{"name": f"cl{i}"} for i in range(cluster_count)]
    pkgs = [{"name": p} for p in (package_names or ["Pkg1"])]
    client.get_packages.return_value = pkgs
    client.get_access_rulebase.return_value = [
        {"uid": f"r{i}", "type": "access-rule"} for i in range(rule_count)
    ]
    return client


def _mock_cm(mock_client):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_run_summary_job_updates_cache():
    mock_client = _make_mock_client(gw_count=3, cluster_count=1, rule_count=10)
    domain_data = {"domains": [{"name": "D1"}], "status": "ok"}
    with patch("app.summary_job.get_cached_domains", return_value=domain_data), \
         patch("app.summary_job.make_client", return_value=_mock_cm(mock_client)):
        from app.summary_job import run_summary_job, get_summary_cache
        run_summary_job()
    cache = get_summary_cache()
    assert cache["gw_count"] == 4
    assert cache["rule_count"] == 10
    assert cache["last_updated"] is not None


def test_get_summary_cache_returns_copy():
    from app.summary_job import get_summary_cache
    c1 = get_summary_cache()
    c2 = get_summary_cache()
    c1["gw_count"] = 9999
    assert c2["gw_count"] != 9999


def test_run_summary_job_writes_to_db():
    mock_client = _make_mock_client(gw_count=2, cluster_count=0, rule_count=7)
    domain_data = {"domains": [{"name": "D1"}], "status": "ok"}
    with patch("app.summary_job.get_cached_domains", return_value=domain_data), \
         patch("app.summary_job.make_client", return_value=_mock_cm(mock_client)):
        from app.summary_job import run_summary_job
        run_summary_job()
    from app.host_metrics import get_history
    rows = get_history()
    assert len(rows) == 1
    assert rows[0]["gw_count"] == 2


def test_run_summary_job_handles_no_domains():
    domain_data = {"domains": [], "status": "ok"}
    with patch("app.summary_job.get_cached_domains", return_value=domain_data):
        from app.summary_job import run_summary_job, get_summary_cache
        run_summary_job()
    assert get_summary_cache()["gw_count"] == 0


def test_run_summary_job_handles_domain_error():
    domain_data = {"domains": [{"name": "D1"}], "status": "ok"}
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("MDS down")
    with patch("app.summary_job.get_cached_domains", return_value=domain_data), \
         patch("app.summary_job.make_client", return_value=bad_cm):
        from app.summary_job import run_summary_job
        run_summary_job()
