import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def jobs_file(tmp_path):
    f = tmp_path / "config_delta_jobs.json"
    f.write_text("[]")
    return f


@pytest.fixture
def smtp_file(tmp_path):
    cfg = {"host": "smtp.test", "port": 587, "username": "u",
           "password": "p", "from_address": "f@test", "use_tls": False, "run_history_days": 30}
    f = tmp_path / "smtp_config.json"
    f.write_text(json.dumps(cfg))
    return f


def test_load_jobs_returns_empty_list_for_missing_file(tmp_path):
    import app.config_delta_scheduler as mod
    result = mod.load_jobs(tmp_path / "nonexistent.json")
    assert result == []


def test_save_and_load_jobs_roundtrip(jobs_file):
    import app.config_delta_scheduler as mod
    jobs = [{"id": "1", "domain": "CORP", "email": "ops@x.com"}]
    mod.save_jobs(jobs, jobs_file)
    assert mod.load_jobs(jobs_file) == jobs


def test_execute_job_sends_email(smtp_file, jobs_file):
    import app.config_delta_scheduler as mod
    job = {
        "id": "job-1", "domain": "CORP", "email": "ops@x.com",
        "format": "csv", "enabled": True,
        "days_of_week": ["MON"], "time": "06:00", "runs": [],
    }
    fake_gw = [{"name": "GW-01", "ip": "10.0.0.1", "policy_package": "P", "install_status": "pending"}]
    fake_changes = {
        "summary": {"access_rules": 2, "address_objects": 0, "nat_rules": 0,
                    "services": 0, "system": 0, "other": 0},
        "changes": [
            {"category": "access_rules", "change_type": "modified",
             "name": "rule-1", "properties": {}},
        ],
    }
    mock_client = MagicMock()
    mock_client.get_gateways_with_status.return_value = fake_gw
    mock_client.get_pending_changes.return_value = fake_changes
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_client)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.config_delta_scheduler.make_client", return_value=mock_ctx):
        with patch("app.config_delta_scheduler.send_email") as mock_send:
            with patch("app.config_delta_scheduler._JOBS_PATH", jobs_file):
                with patch("app.config_delta_scheduler._SMTP_PATH", smtp_file):
                    mod.execute_job(job)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == "ops@x.com"
    assert "GW-01" in kwargs["body_html"]
    assert kwargs["attachment_filename"].endswith(".csv")


def test_execute_job_records_run_on_success(smtp_file, jobs_file):
    import app.config_delta_scheduler as mod
    job = {
        "id": "job-2", "domain": "CORP", "email": "ops@x.com",
        "format": "json", "enabled": True,
        "days_of_week": ["MON"], "time": "06:00", "runs": [],
    }
    mock_client = MagicMock()
    mock_client.get_gateways_with_status.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_client)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.config_delta_scheduler.make_client", return_value=mock_ctx):
        with patch("app.config_delta_scheduler.send_email"):
            with patch("app.config_delta_scheduler._JOBS_PATH", jobs_file):
                with patch("app.config_delta_scheduler._SMTP_PATH", smtp_file):
                    jobs_file.write_text(json.dumps([job]))
                    mod.execute_job(job)

    updated = json.loads(jobs_file.read_text())
    assert len(updated[0]["runs"]) == 1
    assert updated[0]["runs"][0]["status"] == "ok"
