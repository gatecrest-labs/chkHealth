# Operations Guide

Monitoring, maintenance, and updates for chkHealth in production.

---

## Verifying the Stack

In the standard Linux deployment, Gunicorn binds to `127.0.0.1:8100` and Nginx terminates TLS on port 443. Port 8080 is only used in direct/dev mode or the container deployment.

```bash
# 1. Check both services are running
sudo systemctl status chkhealth
sudo systemctl status nginx

# 2. Confirm Nginx is on 443 and Gunicorn is on 8100
sudo ss -tlnp | grep -E '443|8100'

# 3. Test Gunicorn directly (bypasses Nginx)
curl -s http://127.0.0.1:8100/login | grep -i chkhealth

# 4. Test the full stack through Nginx
curl -sk https://localhost/login | grep -i chkhealth

# 5. Check the infrastructure health endpoint
curl -sk https://localhost/api/dashboard/health \
  -H "Cookie: session=<your-session-cookie>" | python3 -m json.tool
```

---

## Logs

### Systemd / Gunicorn Logs

```bash
# Follow live application logs
sudo journalctl -u chkhealth -f

# Application access log (if configured in the systemd unit)
sudo tail -f /var/log/chkhealth/access.log

# Application error log
sudo tail -f /var/log/chkhealth/error.log
```

### Nginx Logs

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### In-App Logs (Admin UI)

Admin users can view, filter, and clear application-level logs at `/admin`. Log entries record login events, API errors, group changes, and background job activity. These are in-memory only — they reset on restart.

To change the log level live (without restarting):
```bash
curl -sk -X POST https://localhost/admin/api/logs/level \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" \
  -H "Cookie: session=<admin-session>" \
  -d '{"level": "DEBUG"}'
# Valid levels: TRACE, DEBUG, INFO, WARN, ERROR
```
Or use the log level control in the Admin UI.

---

## Updating the Application

```bash
cd /opt/chkhealth
sudo -u chkhealth git pull

# Install any new or updated dependencies
sudo -u chkhealth uv sync --no-dev --extra prod

# Restart the service
sudo systemctl restart chkhealth
sudo systemctl status chkhealth
```

Verify with a smoke test after restarting:
```bash
curl -sk https://localhost/login | grep -i chkhealth
```

---

## Rotating SECRET_KEY

Rotating `SECRET_KEY` immediately logs out all active users (the signed cookies become invalid). Schedule during a maintenance window.

```bash
# 1. Generate a new key
sudo -u chkhealth uv run python manage_users.py secret

# 2. Update .env — replace the SECRET_KEY= line
sudo nano /opt/chkhealth/.env

# 3. Restart
sudo systemctl restart chkhealth
```

---

## Background Job Health

| Job | Interval | Startup | Trigger endpoint |
|---|---|---|---|
| Summary (gateway + rule count) | 60 min | Yes | `POST /api/dashboard/refresh` |
| Infrastructure health | 15 min | Yes | `POST /api/dashboard/refresh-health` |
| Domain cache | 30 min | Yes | — |
| Device version cache | 60 min | Yes (after domain cache) | `POST /api/device-review/refresh` |

If the Dashboard shows stale data or persistent spinners:

```bash
# Check for errors in the application logs
sudo journalctl -u chkhealth --since "1 hour ago" | grep -i "ERROR\|WARN\|summary_job\|infra_health\|device_version"
```

You can also trigger an immediate refresh from the Dashboard (summary: the refresh button; infra health: the refresh button on the health cards) or from the Device Review tab (Refresh button). All refresh buttons are available to all logged-in users with the relevant tab access.
