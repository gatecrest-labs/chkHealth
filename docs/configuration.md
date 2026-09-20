# Configuration Reference

## Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in your values. The file is gitignored — never commit credentials.

### Flask Core

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | Flask session signing key — generate with `uv run python manage_users.py secret` |
| `FLASK_DEBUG` | `0` | Set to `1` to enable Flask debug mode and auto-reload (development only) |
| `COOKIE_SECURE` | `false` | Set to `true` when serving over HTTPS |
| `PERMANENT_SESSION_LIFETIME` | `3600` | Sliding session lifetime in seconds (default: 1 hour) |
| `SESSION_ABSOLUTE_LIFETIME` | `36000` | Hard session expiry in seconds regardless of activity (default: 10 hours) |

> **Note:** `FLASK_ENV` was removed in Flask 2.3 and has no effect. Use `FLASK_DEBUG=1` or the `--debug` flag instead.

> **Security:** `SECRET_KEY` must be a long random string. Any change invalidates all active sessions. Generate one with:
> ```bash
> uv run python manage_users.py secret
> ```

---

### Check Point MDS

| Variable | Default | Description |
|---|---|---|
| `CP_MDS_PRIMARY` | *(required)* | IP or hostname of the primary MDS server |
| `CP_MDS_SECONDARY` | — | IP or hostname of the secondary MDS server (leave blank if no HA pair) |
| `CP_API_KEY` | *(required)* | Read-only API key from the MDS (see below) |
| `CP_VERIFY_SSL` | `false` | Set to `true` to validate the MDS TLS certificate |
| `CP_TIMEOUT` | `30` | API request timeout in seconds |

**Generating a read-only API key on Check Point MDS:**
1. Log in to the MDS CLI as an administrator.
2. Run: `mgmt_cli add api-key user-name <username> --format json`
3. Or create a read-only API user via SmartConsole and copy the generated key.

The API key is used for all MDS API calls. A read-only account is strongly recommended — chkHealth never writes to the MDS.

---

### Log Servers (MLS)

Optional. Configure up to two Check Point log servers (MLS) for infrastructure health monitoring.

| Variable | Default | Description |
|---|---|---|
| `CP_MLS_1` | — | IP or hostname of the first log server (MLS) |
| `CP_MLS_2` | — | IP or hostname of the second log server (MLS) |

Log server health is checked by attempting a TCP connection to port 443. No credentials are required.

---

### Display Labels (optional)

These labels appear on the infrastructure health cards on the Dashboard.

| Variable | Default | Description |
|---|---|---|
| `CP_MDS_PRIMARY_LABEL` | `MDS Primary` | Display name for the primary MDS card |
| `CP_MDS_SECONDARY_LABEL` | `MDS Secondary` | Display name for the secondary MDS card |
| `CP_MLS_1_LABEL` | `MLS Primary` | Display name for the first log server card |
| `CP_MLS_2_LABEL` | `MLS Secondary` | Display name for the second log server card |

---

### Health Thresholds

| Variable | Default | Description |
|---|---|---|
| `CPU_WARN` | `70` | CPU % that triggers a warning state on the infrastructure health card |
| `CPU_CRIT` | `90` | CPU % that triggers a critical state |
| `MEM_WARN` | `75` | Memory % that triggers a warning state |
| `MEM_CRIT` | `90` | Memory % that triggers a critical state |

---

### Runtime File Paths (optional)

By default all runtime data files live in the project root. Override these in `.env` or via the container's environment when mounting a data volume.

| Variable | Default | Description |
|---|---|---|
| `USERS_FILE` | `users.json` | Local user accounts (bcrypt hashes) |
| `GROUPS_FILE` | `groups.json` | Group definitions and access rules |
| `APP_SETTINGS_FILE` | `app_settings.json` | Persistent key/value application settings |
| `METRICS_DB_PATH` | `metrics.db` | SQLite database for gateway count history |

> In the container setup from the README, all four are overridden to `/app/data/` so they land on the mounted volume instead of inside the container image.
