# Hardening & Security Guide

---

## File Permissions

### Secure `.env`

```bash
sudo chmod 640 /opt/chkhealth/.env
sudo chown chkhealth:chkhealth /opt/chkhealth/.env
ls -la /opt/chkhealth/.env
# Expected: -rw-r-----
```

### Secure Runtime Data Files

```bash
for f in users.json groups.json app_settings.json metrics.db; do
  sudo chmod 640 /opt/chkhealth/$f
  sudo chown chkhealth:chkhealth /opt/chkhealth/$f
done

sudo chmod 640 /opt/chkhealth/certs/key.pem
sudo chown chkhealth:chkhealth /opt/chkhealth/certs/key.pem
```

---

## SECRET_KEY

- Must be a long, random string (at least 32 bytes of entropy). Generate with: `python manage_users.py secret`
- Never reuse a key from another app or environment.
- Rotating the key immediately invalidates all active sessions (every user is logged out). Schedule rotation during a maintenance window.

---

## HTTPS

Set `COOKIE_SECURE=true` in `.env` whenever the app is served over HTTPS (i.e., in all production deployments). This tells Flask to set the `Secure` flag on the session cookie, preventing it from being sent over plain HTTP.

---

## Nginx TLS

Use the Nginx config from [deployment.md](deployment.md) as a baseline. Additional hardening:

```nginx
# Add to the ssl server block in /etc/nginx/conf.d/chkhealth.conf
ssl_session_cache   shared:SSL:10m;
ssl_session_timeout 10m;
ssl_prefer_server_ciphers on;

# Disable weak protocols explicitly
ssl_protocols TLSv1.2 TLSv1.3;

# HSTS — tells browsers to always use HTTPS for this host
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

# Prevent click-jacking (already set by Flask, belt-and-suspenders at Nginx)
add_header X-Frame-Options "DENY" always;
```

---

## Network Firewall

| Port | Direction | Allow from | Notes |
|------|-----------|-----------|-------|
| 443 | Inbound | User workstations / authorized networks | HTTPS only |
| 80 | Inbound | Same (or block entirely if redirect not needed) | Redirects to 443 |
| 8100 | Inbound | Block from outside | Gunicorn — internal only, proxied by Nginx |
| 443 | Outbound | MDS IP(s) | Check Point Management API |
| 443 | Outbound | MLS IP(s) | Log server reachability check (TCP port 443) |

---

## Check Point API Key

- Use a **read-only** API user on the MDS. chkHealth never writes to Check Point.
- Restrict the API user's source IP to the chkhealth server's IP on the MDS (if your version supports it).
- Set `CP_VERIFY_SSL=true` if the MDS has a valid, trusted TLS certificate.

---

## CSRF Protection

CSRF tokens are automatically enforced on all state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`). No configuration is required. Do not disable `WTF_CSRF_ENABLED` in production.

---

## Security Headers

The following headers are set by the Flask app on every response (see `app/__init__.py`):

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- `Content-Security-Policy: default-src 'self'; ...`

No Nginx configuration is needed for these headers.
