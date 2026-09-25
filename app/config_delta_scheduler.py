from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from app.app_logger import app_log
from app.atomic_io import atomic_write_json
from app.cp_helpers import make_client
from app.smtp_client import send_email

_JOBS_PATH = Path(__file__).parent.parent / "config_delta_jobs.json"
_SMTP_PATH = Path(__file__).parent.parent / "smtp_config.json"


def load_jobs(path: Path | None = None) -> list[dict]:
    if path is None:
        path = _JOBS_PATH
    if not Path(path).exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_jobs(jobs: list[dict], path: Path | None = None) -> None:
    if path is None:
        path = _JOBS_PATH
    atomic_write_json(path, jobs)


def schedule_all_jobs(scheduler) -> None:
    from apscheduler.triggers.cron import CronTrigger

    day_map = {"MON": "mon", "TUE": "tue", "WED": "wed", "THU": "thu",
               "FRI": "fri", "SAT": "sat", "SUN": "sun"}
    jobs = load_jobs()
    for job in jobs:
        if not job.get("enabled", True):
            continue
        job_id = job.get("id", "")
        if not job_id:
            continue
        days = ",".join(day_map.get(d, d.lower()) for d in job.get("days_of_week", []))
        time_parts = str(job.get("time", "06:00")).split(":")
        hour = time_parts[0] if time_parts else "6"
        minute = time_parts[1] if len(time_parts) > 1 else "0"
        trigger = CronTrigger(day_of_week=days, hour=hour, minute=minute)
        scheduler.add_job(
            execute_job,
            trigger=trigger,
            args=[job],
            id=f"cd_{job_id}",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        app_log("INFO", "config_delta_scheduler",
                "Scheduled job", job_id=job_id, domain=job.get("domain"), time=job.get("time"))


def execute_job(job: dict) -> None:
    job_id = job.get("id", "unknown")
    domain = job.get("domain", "")
    app_log("INFO", "config_delta_scheduler", "Starting job", job_id=job_id, domain=domain)

    try:
        with make_client(domain=domain) as client:
            gateways = client.get_gateways_with_status()
            results = []
            for gw in gateways:
                try:
                    changes = client.get_pending_changes()
                    results.append({
                        "gateway": gw["name"], "ip": gw["ip"],
                        "install_status": gw["install_status"],
                        "policy_package": gw.get("policy_package", ""),
                        "summary": changes["summary"],
                        "changes": changes["changes"],
                    })
                except Exception as exc:
                    app_log("WARN", "config_delta_scheduler",
                            "Failed to get changes for gateway",
                            gateway=gw["name"], exc=str(exc))
                    results.append({
                        "gateway": gw["name"], "ip": gw["ip"],
                        "install_status": "error", "policy_package": "",
                        "summary": {}, "changes": [], "error": str(exc),
                    })

        body_html = _build_email_body(domain, results)
        fmt = job.get("format", "html").lower()
        attachment_data, attachment_filename, attachment_mime = _build_attachment(
            domain, results, fmt
        )
        send_email(
            to=job["email"],
            subject=f"Config-Delta Report: {domain} — {datetime.now().strftime('%Y-%m-%d')}",
            body_html=body_html,
            attachment_data=attachment_data,
            attachment_filename=attachment_filename,
            attachment_mime=attachment_mime,
            config_path=_SMTP_PATH,
        )
        _record_run(job_id, "ok", len(gateways),
                    sum(1 for r in results if r["install_status"] == "pending"))
        app_log("INFO", "config_delta_scheduler", "Job completed", job_id=job_id)
    except Exception as exc:
        app_log("ERROR", "config_delta_scheduler", "Job failed", job_id=job_id, exc=str(exc))
        _record_run(job_id, "error", 0, 0, error=str(exc))


def _record_run(
    job_id: str, status: str, gateways_total: int,
    gateways_with_changes: int, error: Optional[str] = None
) -> None:
    jobs = load_jobs()
    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cutoff = datetime.now(timezone.utc) - timedelta(days=_run_history_days())
    run: dict = {"ran_at": now_str, "status": status,
                 "gateways_total": gateways_total,
                 "gateways_with_changes": gateways_with_changes}
    if error:
        run["error"] = error
    for job in jobs:
        if job.get("id") == job_id:
            runs = job.setdefault("runs", [])
            runs.append(run)
            job["runs"] = [
                r for r in runs
                if datetime.fromisoformat(r["ran_at"]) >= cutoff
            ]
            break
    save_jobs(jobs)


def _run_history_days() -> int:
    if not _SMTP_PATH.exists():
        return 30
    try:
        with open(_SMTP_PATH) as f:
            return int(json.load(f).get("run_history_days", 30))
    except Exception:
        return 30


def _build_email_body(domain: str, results: list[dict]) -> str:
    rows = "".join(
        f"<tr><td>{r['gateway']}</td><td>{r['ip']}</td>"
        f"<td>{'Pending Install' if r['install_status'] == 'pending' else r['install_status']}</td>"
        f"<td>{sum(r.get('summary', {}).values())}</td></tr>"
        for r in results
    )
    return f"""<html><body>
<h2>Config-Delta Report: {domain}</h2>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse">
<thead><tr><th>Gateway</th><th>IP</th><th>Status</th><th>Total Changes</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p>See attachment for full details.</p>
</body></html>"""


def _build_attachment(
    domain: str, results: list[dict], fmt: str
) -> tuple[str, str, str]:
    date = datetime.now().strftime("%Y-%m-%d")
    if fmt == "json":
        return (
            json.dumps(results, indent=2),
            f"config-delta-{domain}-{date}.json",
            "application/json",
        )
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["gateway", "ip", "install_status", "category",
                          "change_type", "name", "properties"])
        for r in results:
            for c in r.get("changes", []):
                writer.writerow([
                    r["gateway"], r["ip"], r["install_status"],
                    c["category"], c["change_type"], c["name"],
                    json.dumps(c.get("properties", {})),
                ])
        return buf.getvalue(), f"config-delta-{domain}-{date}.csv", "text/csv"
    # html (default)
    rows = "".join(
        f"<tr><td>{r['gateway']}</td><td>{r['ip']}</td><td>{r['install_status']}</td>"
        f"<td>{sum(r.get('summary', {}).values())}</td></tr>"
        for r in results
    )
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Config-Delta {domain} {date}</title>
<style>body{{font-family:sans-serif;padding:20px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:4px 8px}}</style></head><body>
<h1>Config-Delta: {domain} — {date}</h1>
<table><thead><tr><th>Gateway</th><th>IP</th><th>Status</th><th>Changes</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""
    return html, f"config-delta-{domain}-{date}.html", "text/html"
