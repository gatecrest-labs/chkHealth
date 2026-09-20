<picture>
  <source media="(prefers-color-scheme: dark)" srcset="logo-dark.svg">
  <img alt="chkHealth logo" src="logo.svg" width="240">
</picture>

# chkHealth — Check Point Operations Dashboard

A read-only web dashboard for **Check Point Provider-1 (MDS)** environments.

## Features

- **Dashboard** — managed gateway counts, 30-day trend charts, infrastructure health (MDS HA pair + log servers)
- **Firewalls** — browse gateways and clusters by domain with full details
- **Rule Review** — view access rulebases, look up objects, interfaces, and NAT rules by domain
- **Admin** — local user management, group-based access control, application logs

## Screenshots

<!-- TODO: add screenshots once the UI is complete -->

## Requirements

- Python ≥ 3.11
- [UV](https://docs.astral.sh/uv/) package manager
- A Check Point Provider-1 (MDS) environment with a read-only API key

---

## Deployment

### macOS (local development)

```bash
# Install UV if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone <repo-url>
cd check.health
uv sync

cp .env.example .env
# Edit .env — set SECRET_KEY, CP_MDS_PRIMARY, CP_API_KEY, etc.
# Generate a SECRET_KEY: python manage_users.py secret

python manage_users.py add admin --role admin
uv run flask --app app run --debug
```

Open http://127.0.0.1:5000

### Red Hat Enterprise Linux / Rocky Linux / AlmaLinux

```bash
# Install Python 3.11+ (RHEL 9 ships with 3.11; RHEL 8 needs the module stream)
# RHEL 9:
sudo dnf install -y python3.11 python3.11-pip

# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # or open a new shell

# Clone and set up the project
git clone <repo-url>
cd check.health
uv sync

cp .env.example .env
# Edit .env — fill in all CP_* values and SECRET_KEY

python manage_users.py add admin --role admin

# Run under gunicorn for production use
uv run gunicorn --workers 2 --bind 0.0.0.0:8080 wsgi:application
```

To run as a systemd service, create `/etc/systemd/system/check-health.service`:

```ini
[Unit]
Description=check.health web application
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/check.health
EnvironmentFile=/opt/check.health/.env
ExecStart=/opt/check.health/.venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8080 wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now check-health
```

### Container (Docker / Podman)

Create a `Dockerfile` at the project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install uv && uv sync --no-dev

COPY app/ app/
COPY wsgi.py manage_users.py ./

# Runtime data lives in a mounted volume — not baked into the image
VOLUME ["/app/data"]
ENV USERS_FILE=/app/data/users.json
ENV GROUPS_FILE=/app/data/groups.json
ENV APP_SETTINGS_FILE=/app/data/app_settings.json
ENV METRICS_DB_PATH=/app/data/metrics.db

EXPOSE 8080
CMD ["uv", "run", "gunicorn", "--workers", "2", "--bind", "0.0.0.0:8080", "wsgi:application"]
```

```bash
# Build
docker build -t check-health .

# Run (pass .env file; mount a data volume for persistent users/groups)
docker run -d \
  --name check-health \
  --env-file .env \
  -v check-health-data:/app/data \
  -p 8080:8080 \
  check-health
```

> **Note:** The container image never contains `.env`, `users.json`, `groups.json`, or any credentials. Always pass secrets via `--env-file` or orchestrator secrets (Kubernetes Secrets, Podman secrets, etc.).

---

## Configuration

See `.env.example` for all available configuration options.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## License

[MIT](LICENSE)
