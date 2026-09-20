# Authentication Guide

chkHealth uses **local bcrypt authentication** backed by `users.json`. All credentials are stored as bcrypt hashes — plaintext passwords are never written to disk.

> **Planned:** Active Directory / LDAP and RADIUS authentication are planned for a future release. This guide covers the currently implemented local authentication only.

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
