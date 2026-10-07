# Authentication Guide

chkHealth uses **local bcrypt authentication** backed by `users.json`. All credentials are stored as bcrypt hashes — plaintext passwords are never written to disk.

Optional remote authentication providers — **LDAP/Active Directory**, **TACACS+**, and **RADIUS** — can be enabled via environment variables. Local bcrypt is always the final fallback and cannot be disabled.

---

## Role-Based Access Control (RBAC)

Every user has a **role**: `admin` or `viewer`.

| Role | Access |
|------|--------|
| `admin` | All tabs, all domains, Admin page |
| `viewer` | Group-controlled tab and domain access (see Groups below) |

Role is stored in the signed Flask session cookie at login. Clients cannot tamper with it — `SECRET_KEY` cryptographically signs and verifies the cookie on every request.

---

## Groups (viewer access control)

Viewer-role users must belong to at least one group to access anything. A user with no group membership sees no tabs.

Each group has four fields:

| Field | Type | Meaning |
|---|---|---|
| `members` | list of usernames | Users in this group |
| `allowed_tabs` | list of tab keys | Tabs members can access |
| `domain_restrict` | boolean | If `true`, restrict to `allowed_domains`; if `false`, allow all domains |
| `allowed_domains` | list of domain names | Effective only when `domain_restrict: true` |

**Tab keys:** `dashboard`, `firewalls`, `rule_review`

**Effective access is the union across all groups:** if a user belongs to two groups, they get the combined set of `allowed_tabs`, and domain access is unrestricted if either group has `domain_restrict: false`.

### Example `groups.json`

```json
{
  "network-ops": {
    "members": ["alice", "bob"],
    "allowed_tabs": ["dashboard", "firewalls", "rule_review"],
    "domain_restrict": false,
    "allowed_domains": []
  },
  "dc1-readonly": {
    "members": ["carol"],
    "allowed_tabs": ["firewalls", "rule_review"],
    "domain_restrict": true,
    "allowed_domains": ["DC1-Domain"]
  }
}
```

Groups are managed in the Admin UI (`/admin`) or by editing `groups.json` directly — changes take effect immediately without restarting the app.

---

## Session Security

| Setting | Default | Notes |
|---|---|---|
| `PERMANENT_SESSION_LIFETIME` | 3600 s (1 hour) | Sliding expiry — resets on activity |
| `SESSION_ABSOLUTE_LIFETIME` | 36000 s (10 hours) | Hard limit regardless of activity |
| `COOKIE_SECURE` | `false` | Set to `true` in production (HTTPS required) |
| `SESSION_COOKIE_HTTPONLY` | `true` (hardcoded) | Prevents JavaScript access to the session cookie |
| `SESSION_COOKIE_SAMESITE` | `Lax` (hardcoded) | Mitigates CSRF from cross-site navigation |

CSRF tokens are enforced on all state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`).

**Login rate limiting:** The login endpoint enforces brute-force protection — 10 failed attempts per source IP or 5 failed attempts per username within a 10-minute window returns HTTP 429 (Too Many Requests). The counter resets after 10 minutes.

---

## User Management CLI

Use `manage_users.py` for command-line user management (useful during initial setup and scripted provisioning).

```bash
# Add an admin user (prompts for password if --password is omitted)
uv run python manage_users.py add alice --role admin

# Add a viewer user
uv run python manage_users.py add bob --role viewer

# Update a user's password (same command — if user exists, password is updated)
uv run python manage_users.py add bob --role viewer

# Delete a user
uv run python manage_users.py delete bob

# List all users
uv run python manage_users.py list

# Generate a new SECRET_KEY value
uv run python manage_users.py secret
```

> **Important:** Always keep at least one local `admin` account. It is your only recovery path if the app is otherwise inaccessible.

---

## First-Time Setup

```bash
# 1. Generate a SECRET_KEY and add it to .env
uv run python manage_users.py secret

# 2. Create the first admin account
uv run python manage_users.py add admin --role admin

# 3. Start the app
uv run flask --app app run
```

After logging in, create groups and additional users via the Admin UI.

---

## Remote Authentication Providers

chkHealth supports three optional remote authentication backends. Only one may be active at a time. Local bcrypt (`users.json`) is always the final fallback and cannot be disabled.

**Provider priority (when enabled):** LDAP → TACACS+ → RADIUS → Local

> **Important:** Always keep at least one local `admin` account. It is your only recovery path if the remote provider is unreachable.

---

### LDAP / Active Directory

Requires no additional install — `ldap3` is included in the default dependencies.

```dotenv
LDAP_ENABLED=true
LDAP_SERVER=ldaps://dc01.corp.example.com
LDAP_DOMAIN=corp.example.com
LDAP_BASE_DN=DC=corp,DC=example,DC=com
LDAP_BIND_USER=svc-chkhealth@corp.example.com
LDAP_BIND_PASSWORD=<service-account-password>
LDAP_USER_SEARCH=(sAMAccountName={username})
LDAP_GROUP_ADMIN=chkhealth-admins
LDAP_GROUP_VIEWER=chkhealth-viewers
LDAP_VERIFY_SSL=true
```

**Role resolution:** On successful authentication the user's `memberOf` attribute is read. CN values are matched case-insensitively (substring) against `LDAP_GROUP_ADMIN` and `LDAP_GROUP_VIEWER`. If a user has group membership but no CN matches either configured value, access is denied. If a user has no `memberOf` attribute, they receive the `viewer` role.

**SSL note:** Set `LDAP_VERIFY_SSL=false` only for self-signed lab certificates.

**Smoke test:**
```bash
uv run python -c "
from app.ldap_auth import authenticate
print(authenticate('your-username', 'your-password',
    server_url='ldaps://your-dc',
    base_dn='DC=corp,DC=example,DC=com',
    bind_user='svc@corp.example.com',
    bind_password='svc-pass',
    user_search='(sAMAccountName={username})',
    group_admin='chkhealth-admins',
    group_viewer='chkhealth-viewers',
    verify_ssl=False))
"
```

---

### TACACS+

Requires no additional install — `tacacs_plus` is included in the default dependencies.

```dotenv
TACACS_ENABLED=true
TACACS_HOST=10.0.0.1
TACACS_PORT=49
TACACS_SECRET=<shared-secret>
TACACS_TIMEOUT=10
# Privilege-level mode (most common):
TACACS_PRIV_ADMIN=15
# OR group AV-pair mode (set TACACS_PRIV_ADMIN="" and configure these):
# TACACS_GROUP_ADMIN=chkhealth-admins
# TACACS_GROUP_VIEWER=chkhealth-viewers
```

**Role resolution — choose one mode:**

- **Privilege-level mode** (`TACACS_PRIV_ADMIN` non-empty): users with `priv-lvl` ≥ threshold become `admin`; below threshold → `viewer`; missing `priv-lvl` → `viewer`.
- **Group AV-pair mode** (`TACACS_PRIV_ADMIN` empty): AV pair values are matched case-insensitively against `TACACS_GROUP_ADMIN` / `TACACS_GROUP_VIEWER`. Present but unmatched → access denied.

**Secondary server:** Set `TACACS_HOST_2` and `TACACS_PORT_2` for automatic failover.

**Smoke test:**
```bash
uv run python -c "
from app.tacacs_auth import authenticate
print(authenticate('your-username', 'your-password',
    host='10.0.0.1', port=49,
    secret='your-secret', timeout=5,
    priv_admin='15', group_admin='', group_viewer=''))
"
```

---

### RADIUS

No additional dependencies — pure Python implementation.

```dotenv
RADIUS_ENABLED=true
RADIUS_HOST=10.0.0.1
RADIUS_PORT=1812
RADIUS_SECRET=<shared-secret>
RADIUS_TIMEOUT=10
RADIUS_GROUP_ADMIN=network-admins
RADIUS_GROUP_VIEWER=network-viewers
```

**Role resolution:** The RADIUS server must return `Filter-Id` (attribute 11) or `Class` (attribute 25) reply attributes containing the group name. Values are matched case-insensitively (substring). If group attributes are present but nothing matches, access is denied. If no group attributes are returned, the user receives the `viewer` role.

**Secondary server:** Set `RADIUS_HOST_2` and `RADIUS_PORT_2` for automatic failover.

**Smoke test:**
```bash
uv run python -c "
from app.radius_auth import authenticate
print(authenticate('your-username', 'your-password',
    host='10.0.0.1', port=1812,
    secret='your-secret', timeout=5,
    group_admin='network-admins', group_viewer='network-viewers'))
"
```
