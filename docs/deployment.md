# Production Deployment Guide

Two deployment paths:

- **[Path A](#path-a--linux--nginx--gunicorn--systemd)** — Gunicorn + Nginx + systemd on a Linux server (recommended for bare-metal or VM)
- **[Path B](#path-b--docker--podman)** — Container image with a mounted data volume

For authentication configuration, see [authentication.md](authentication.md).
For hardening, see [hardening.md](hardening.md).
For monitoring and maintenance, see [operations.md](operations.md).

---

## Path A — Linux + Nginx + Gunicorn + systemd

**Supported OS:** Rocky Linux 9 / AlmaLinux 9 / RHEL 9, Ubuntu 22.04/24.04 LTS, Debian 12

Estimated time: 30–60 minutes for a first deployment.

### Phase 1 — Server Prerequisites

```bash
# RHEL/Rocky/Alma 9
sudo dnf install -y python3.11 python3.11-pip nginx

# Ubuntu/Debian
sudo apt-get install -y python3.11 python3-pip nginx

# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Make UV available system-wide so the chkhealth service account can call it
sudo install -m 755 ~/.local/bin/uv /usr/local/bin/uv

# Create a dedicated service account
sudo useradd --system --no-create-home --shell /usr/sbin/nologin chkhealth

# Open HTTP and HTTPS ports (both needed — HTTP redirects to HTTPS)
# RHEL/Rocky/Alma:
sudo firewall-cmd --permanent --add-service=https && sudo firewall-cmd --permanent --add-service=http && sudo firewall-cmd --reload
# Ubuntu/Debian:
sudo ufw allow 'Nginx Full'
```

### Phase 2 — Application Setup

```bash
# Clone to /opt/chkhealth
sudo git clone <repo-url> /opt/chkhealth
sudo chown -R chkhealth:chkhealth /opt/chkhealth
cd /opt/chkhealth

# Install dependencies (--extra prod installs gunicorn)
sudo -u chkhealth uv sync --no-dev --extra prod

# Create .env from the example
sudo -u chkhealth cp .env.example .env
sudo -u chkhealth nano .env   # fill in CP_* values and SECRET_KEY
```

Generate `SECRET_KEY`:
```bash
sudo -u chkhealth uv run python manage_users.py secret
# Copy the output into .env
```

> **Note:** Set `COOKIE_SECURE=true` in `.env` once Nginx TLS is configured (Phase 5).

Create the first admin user:
```bash
sudo -u chkhealth uv run python manage_users.py add admin --role admin
```

### Phase 3 — TLS Certificate

Self-signed (for lab/internal use):
```bash
sudo mkdir -p /opt/chkhealth/certs
sudo openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
  -keyout /opt/chkhealth/certs/key.pem \
  -out /opt/chkhealth/certs/cert.pem \
  -subj "/CN=chkhealth"
sudo chown chkhealth:chkhealth /opt/chkhealth/certs/*.pem
sudo chmod 640 /opt/chkhealth/certs/*.pem
```

For a CA-signed cert, place it at `/opt/chkhealth/certs/cert.pem` and the key at `/opt/chkhealth/certs/key.pem`.

### Phase 4 — Systemd Service

Create `/etc/systemd/system/chkhealth.service`:

```ini
[Unit]
Description=chkHealth web application
After=network.target

[Service]
Type=simple
User=chkhealth
WorkingDirectory=/opt/chkhealth
EnvironmentFile=/opt/chkhealth/.env
ExecStart=/opt/chkhealth/.venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:8100 \
    --timeout 120 \
    --access-logfile /var/log/chkhealth/access.log \
    --error-logfile /var/log/chkhealth/error.log \
    wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /var/log/chkhealth
sudo chown chkhealth:chkhealth /var/log/chkhealth

sudo systemctl daemon-reload
sudo systemctl enable --now chkhealth
sudo systemctl status chkhealth
```

### Phase 5 — Nginx Reverse Proxy

Create `/etc/nginx/conf.d/chkhealth.conf`:

```nginx
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /opt/chkhealth/certs/cert.pem;
    ssl_certificate_key /opt/chkhealth/certs/key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    location / {
        proxy_pass         http://127.0.0.1:8100;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo nginx -t
sudo systemctl enable --now nginx
```

Open `https://<server-ip>` in a browser to verify.

---

## Path B — Docker / Podman

### Build the Image

Create a `Dockerfile` at the project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install uv && uv sync --no-dev --extra prod

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
docker build -t chkhealth .
```

### Run

```bash
# Create a named volume for persistent data
docker volume create chkhealth-data

# Run — pass .env for all secrets
docker run -d \
  --name chkhealth \
  --restart unless-stopped \
  --env-file .env \
  -v chkhealth-data:/app/data \
  -p 8080:8080 \
  chkhealth
```

### First Admin User (container)

```bash
docker exec -it chkhealth uv run python manage_users.py add admin --role admin
```

### TLS in front of the container

Place Nginx or another reverse proxy in front of the container. The container binds to `0.0.0.0:8080` internally — do not expose it directly on 443. Use the same Nginx config from Path A, pointing `proxy_pass` to `http://127.0.0.1:8080` (or the container's published port).

> **Security note:** The container image never contains `.env`, `users.json`, `groups.json`, or credentials. Always pass secrets via `--env-file` or orchestrator secrets (Kubernetes Secrets, Podman secrets).

### Podman

Substitute `podman` for `docker` in all commands above. Use `podman volume create` and `podman run` equivalents. For rootless Podman, ensure the data volume path is accessible to the container user.
