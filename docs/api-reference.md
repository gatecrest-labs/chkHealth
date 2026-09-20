# API Reference

All endpoints require an authenticated session (HTTP 401 otherwise). Endpoints marked `*` require the `admin` role (HTTP 403 for viewer-role users).

Tab-restricted endpoints return HTTP 403 if the authenticated user does not have access to the relevant tab via their group membership.

## Authentication

| Method | Path | Description |
|---|---|---|
| `GET` | `/login` | Login page |
| `POST` | `/login` | Submit credentials (`username`, `password` form fields). Sets a signed session cookie on success. Redirects to dashboard. |
| `POST` | `/logout` | End the current session. Requires a valid CSRF token (`X-CSRF-Token` header or `csrf_token` form field). |

---

## Dashboard

All endpoints require the `dashboard` tab.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dashboard/summary` | Gateway count, rule count, last-updated timestamp, 30-day history array |
| `GET` | `/api/dashboard/health` | Infrastructure health for all configured MDS and MLS servers |
| `POST` | `/api/dashboard/refresh` | Trigger an immediate background recalculation of gateway/rule counts. Returns `{"status": "accepted"}` (202) or `{"status": "already_running"}` (202) if a job is already in progress. |
| `POST` | `/api/dashboard/refresh-health` | Trigger an immediate re-poll of all infrastructure health targets. Same response shape as `/refresh`. |

### `GET /api/dashboard/summary` response shape

```json
{
  "gw_count": 47,
  "rule_count": 12843,
  "last_updated": "2026-09-19T14:00:00+00:00",
  "history": [
    {"date": "2026-08-20", "gw_count": 45},
    ...
  ]
}
```

### `GET /api/dashboard/health` response shape

```json
{
  "servers": [
    {
      "label": "MDS Primary (DC1)",
      "host": "10.x.x.x",
      "type": "MDS",
      "status": "healthy",
      "hostname": "mds-primary",
      "version": "R82",
      "ha_role": "active",
      "cpu_pct": null,
      "mem_pct": null
    },
    {
      "label": "MLS Primary",
      "host": "10.x.x.x",
      "type": "MLS",
      "status": "healthy",
      ...
    }
  ],
  "last_updated": "2026-09-19T14:05:00+00:00"
}
```

`status` values: `"healthy"` | `"unreachable"`

---

## Firewalls

All endpoints require the `firewalls` tab (except `/api/firewalls/domains`, which also accepts `rule_review` tab).

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/firewalls/domains` | List domains visible to the authenticated user. Requires `firewalls` or `rule_review` tab. |
| `GET` | `/api/firewalls/gateways?domain=<name>` | List all gateways and clusters in a domain (full detail level). |
| `GET` | `/api/firewalls/gateway?domain=<name>&name=<gw>&type=<gateway\|cluster>` | Full details for a single gateway or cluster. |

### `GET /api/firewalls/domains` response

```json
{"domains": ["DC1-Domain", "DC2-Domain"]}
```

### `GET /api/firewalls/gateways` response

```json
{
  "domain": "DC1-Domain",
  "gateways": [ { ...Check Point gateway object... } ],
  "clusters": [ { ...Check Point cluster object... } ]
}
```

### `GET /api/firewalls/gateway` response

Returns the full Check Point gateway or cluster object, including `interfaces`, `policy`, HA members, etc.

**Error responses:**
- `400` — missing required parameter
- `403` — domain access denied for this user
- Upstream errors are proxied with the Check Point error detail

---

## Rule Review

All endpoints require the `rule_review` tab.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/rule-review/packages?domain=<name>` | List policy package names in a domain |
| `GET` | `/api/rule-review/rules?domain=<name>&package=<name>` | Fetch the access rulebase for a package (max 2,000 rules) |
| `GET` | `/api/rule-review/objects?domain=<name>&name=<object-name>` | Look up a network object or group by name |
| `GET` | `/api/rule-review/interfaces?domain=<name>&ips=<ip1,ip2,...>` | Find gateway interfaces matching one or more IP addresses |
| `GET` | `/api/rule-review/nat?domain=<name>&ip=<ip>` | Find NAT rules matching an IP across all packages in a domain |

### `GET /api/rule-review/rules` response

```json
{
  "rules": [
    {
      "type": "access-rule",
      "name": "Allow-Web",
      "rule-number": 1,
      "source": [...],
      "destination": [...],
      "service": [...],
      "action": {"name": "Accept"},
      "track": {"type": "Log"},
      "enabled": true,
      "comments": ""
    }
  ],
  "total": 142
}
```

### `GET /api/rule-review/interfaces` response

```json
{
  "results": [
    {
      "gateway": "gw-dc1-01",
      "interface": "eth1",
      "ip": "10.x.x.x",
      "subnet": "10.x.x.0",
      "mask": "255.255.255.0"
    }
  ]
}
```

### `GET /api/rule-review/nat` response

```json
{
  "results": [
    {
      "package": "Policy-DC1",
      "rule-number": 5,
      "original-source": {"ip-address": "10.x.x.x"},
      "translated-source": {"ip-address": "10.x.x.x"},
      ...
    }
  ]
}
```

---

## Admin `*`

All endpoints in this section require the `admin` role.

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/api/users` `*` | List all local users (`[{"username": "alice", "role": "admin"}, ...]`) |
| `GET` | `/admin/api/groups` `*` | List all groups |
| `POST` | `/admin/api/groups` `*` | Create a group. Body: `{"name": "...", "members": [...], "allowed_tabs": [...], "domain_restrict": false, "allowed_domains": [...]}` |
| `PUT` | `/admin/api/groups/<name>` `*` | Update a group. Body: same shape as POST (name omitted). |
| `DELETE` | `/admin/api/groups/<name>` `*` | Delete a group |
| `GET` | `/admin/api/domains` `*` | List all domains from the domain cache |
| `GET` | `/admin/api/logs` `*` | Fetch log entries. Query params: `level`, `component`, `limit` (max 2000, default 500) |
| `POST` | `/admin/api/logs/level` `*` | Set live log level. Body: `{"level": "DEBUG\|INFO\|WARN\|ERROR"}` |
| `DELETE` | `/admin/api/logs` `*` | Clear all in-memory log entries |
| `GET` | `/admin/api/tabs` `*` | List registered tab keys and labels |
| `GET` | `/admin/api/settings` `*` | Get all application settings |
| `PUT` | `/admin/api/settings` `*` | Update settings. Body: `{"key": value, ...}` |

**All mutating endpoints require a valid CSRF token** (`X-CSRF-Token` header or `csrf_token` form field). Obtain the token from the session after login.
