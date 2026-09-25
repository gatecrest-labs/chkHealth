import pytest


@pytest.fixture
def jobs_path(tmp_path):
    return tmp_path / "rule_hygiene_jobs.json"


@pytest.fixture
def scheduler_mod(jobs_path, monkeypatch):
    import app.rule_hygiene_scheduler as mod
    monkeypatch.setattr(mod, "_JOBS_PATH", jobs_path)
    monkeypatch.setattr(mod, "_scheduler", None)
    mod._running_jobs.clear()
    yield mod


def _job_data(**kwargs):
    base = {
        "domain": "corp",
        "email": "admin@example.com",
        "days_of_week": ["MON"],
        "time": "06:00",
        "checks": ["unnamed"],
        "include_unused_objects": False,
        "batch_size": 20,
        "format": "html",
        "enabled": True,
    }
    base.update(kwargs)
    return base


def test_create_job(scheduler_mod):
    job = scheduler_mod.create_job(_job_data())
    assert job["domain"] == "corp"
    assert job["email"] == "admin@example.com"
    assert "id" in job


def test_create_job_missing_email(scheduler_mod):
    with pytest.raises(ValueError, match="email"):
        scheduler_mod.create_job(_job_data(email=""))


def test_create_job_missing_domain(scheduler_mod):
    with pytest.raises(ValueError, match="domain"):
        scheduler_mod.create_job(_job_data(domain=""))


def test_create_job_invalid_days(scheduler_mod):
    with pytest.raises(ValueError, match="days_of_week"):
        scheduler_mod.create_job(_job_data(days_of_week=["MONDAY"]))


def test_create_job_invalid_time(scheduler_mod):
    with pytest.raises(ValueError, match="time"):
        scheduler_mod.create_job(_job_data(time="25:00"))


def test_get_all_jobs(scheduler_mod):
    scheduler_mod.create_job(_job_data())
    jobs = scheduler_mod.get_all_jobs()
    assert len(jobs) == 1


def test_update_job(scheduler_mod):
    job = scheduler_mod.create_job(_job_data())
    updated = scheduler_mod.update_job(job["id"], _job_data(email="new@example.com"))
    assert updated["email"] == "new@example.com"


def test_update_job_not_found(scheduler_mod):
    with pytest.raises(KeyError):
        scheduler_mod.update_job("nonexistent-id", _job_data())


def test_delete_job(scheduler_mod):
    job = scheduler_mod.create_job(_job_data())
    scheduler_mod.delete_job(job["id"])
    assert len(scheduler_mod.get_all_jobs()) == 0


def test_delete_job_not_found(scheduler_mod):
    with pytest.raises(KeyError):
        scheduler_mod.delete_job("nonexistent-id")


def test_execute_job_calls_bulk_and_sends_email(scheduler_mod, monkeypatch):
    pkg_result = {
        "package": "Standard",
        "package_name": "Standard",
        "findings": [],
        "unused_objects": None,
        "policy_count": 5,
        "error": None,
    }
    monkeypatch.setattr(scheduler_mod, "_bulk_hygiene_domain",
                        lambda *a, **kw: [pkg_result])
    sent = []
    monkeypatch.setattr(scheduler_mod, "_send_email",
                        lambda to, subject, body, attachments: sent.append(to))

    job = scheduler_mod.create_job(_job_data())
    scheduler_mod._execute_job(job["id"])

    assert len(sent) == 1
    assert sent[0] == "admin@example.com"

    jobs = scheduler_mod.get_all_jobs()
    assert jobs[0]["runs"][0]["status"] == "ok"


def test_run_history_appended(scheduler_mod, monkeypatch):
    monkeypatch.setattr(scheduler_mod, "_bulk_hygiene_domain",
                        lambda *a, **kw: [])
    monkeypatch.setattr(scheduler_mod, "_send_email",
                        lambda *a, **kw: None)
    job = scheduler_mod.create_job(_job_data())
    scheduler_mod._execute_job(job["id"])
    jobs = scheduler_mod.get_all_jobs()
    assert len(jobs[0]["runs"]) == 1


def test_is_job_running_false(scheduler_mod):
    job = scheduler_mod.create_job(_job_data())
    assert not scheduler_mod.is_job_running(job["id"])
