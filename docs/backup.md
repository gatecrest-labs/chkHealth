# Backup and Restore Guide

The application code lives in git — only runtime data needs backing up. All of these files are gitignored and never appear in the repository.

## What to Back Up

| File | Contents | Critical? |
|------|----------|-----------|
| `.env` | `SECRET_KEY`, Check Point API key, all configuration | **Yes** — app won't start without it |
| `users.json` | Local user accounts with bcrypt-hashed passwords | **Yes** — required for login |
| `groups.json` | Group definitions, tab permissions, domain access | **Yes** — restores access control |
| `app_settings.json` | Persistent application settings | Yes |
| `metrics.db` | SQLite DB with 30-day gateway count history | Recommended — regenerates slowly over time |
| `certs/cert.pem` | TLS certificate | Yes (if self-signed or corp CA; skip if Let's Encrypt manages it) |
| `certs/key.pem` | TLS private key | Yes (same caveat) |

---

## Manual Backup

```bash
# Linux deployment — tar the data files
sudo tar czf chkhealth-backup-$(date +%Y%m%d).tar.gz \
  -C /opt/chkhealth \
  .env users.json groups.json app_settings.json metrics.db certs/

# Copy to a backup location
scp chkhealth-backup-$(date +%Y%m%d).tar.gz backup-server:/backups/chkhealth/
```

```bash
# Container deployment — back up the data volume
docker run --rm \
  -v chkhealth-data:/data \
  -v $(pwd):/backup \
  busybox tar czf /backup/chkhealth-data-backup-$(date +%Y%m%d).tar.gz /data
```

---

## Restore on a New Server

```bash
# 1. Clone the repo and install dependencies
git clone <repo-url> /opt/chkhealth
cd /opt/chkhealth
uv sync --no-dev --extra prod

# 2. Extract the backup
tar xzf chkhealth-backup-YYYYMMDD.tar.gz -C /opt/chkhealth

# 3. Fix ownership
sudo chown -R chkhealth:chkhealth /opt/chkhealth

# 4. Reinstall systemd service and start
sudo systemctl daemon-reload
sudo systemctl enable --now chkhealth
```

If restoring `certs/`, ensure the Nginx config points to the restored paths.

---

## Rotation Schedule (recommended)

- **Daily:** `.env`, `users.json`, `groups.json` — small files, change rarely, essential for recovery
- **Weekly:** `metrics.db`, `app_settings.json`, `certs/`
- Retain at least 30 days of backups off-server
