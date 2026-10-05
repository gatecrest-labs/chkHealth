# API Reference

All endpoints require an authenticated session (HTTP 401 otherwise). Endpoints marked `*` require the `admin` role (HTTP 403 for viewer-role users).

Tab-restricted endpoints return HTTP 403 if the authenticated user does not have access to the relevant tab via their group membership.

## Authentication

| Method | Path | Description |
|---|---|---|
| `GET` | `/login` | Login page |
| `POST` | `/login` | Submit credentials (`username`, `password` form fields). Sets a signed session cookie on success. Redirects to dashboard. Returns HTTP 429 if login rate limits are exceeded (10 failures/IP or 5 failures/username within 10 minutes). |
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
    {"date": "2026-08-20", "gw_count": 45, "rule_count": 12843},
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
{
  "domains": ["DC1-Domain", "DC2-Domain"],
  "status": "ok"
}
```

`status` values: `"empty"` (cache not yet populated) | `"collecting"` (refresh in progress) | `"ok"` (ready) | `"error"` (last refresh failed)

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

### `GET /firewalls/gateway`

Renders the gateway detail page. Requires the `firewalls` tab.

| Query param | Required | Description |
|---|---|---|
| `domain` | Yes | Domain name |
| `name` | Yes | Gateway or cluster name |
| `type` | Yes | `gateway` or `cluster` |

Returns HTTP 200 (HTML page) on success, 400 if params are missing/invalid.

---

### `GET /api/firewalls/gateway/interfaces`

Returns live interface data from the Gaia API via management proxy. Requires the `firewalls` tab.

**Query params:** `domain`, `name`, `type` (same as above)

**Response (success):**
```json
{
  "available": true,
  "target_member": "member-name-or-null",
  "physical": [
    {
      "name": "eth0",
      "ipv4-address": "10.0.0.1",
      "ipv4-mask-length": 24,
      "mac-addr": "aa:bb:cc:dd:ee:ff",
      "enabled": true,
      "status": { "link-state": true, "speed": "1000M", "duplex": "full" }
    }
  ],
  "vlan": [...],
  "bond": [...],
  "loopback": [...]
}
```

**Response (unavailable):**
```json
{ "available": false, "reason": "no_active_member" }
```

---

### `GET /api/firewalls/gateway/routing`

Returns the full routing table from the Gaia API. Requires R81.20+. Requires the `firewalls` tab.

**Query params:** `domain`, `name`, `type`

**Response (success):**
```json
{
  "available": true,
  "target_member": null,
  "routes": [
    {
      "destination": "10.0.0.0",
      "mask_length": 24,
      "nexthop": "192.168.1.1",
      "interface": "eth0",
      "protocol": "static",
      "metric": 0,
      "rank": 60
    }
  ],
  "total": 847,
  "protocol_counts": { "static": 12, "ospf": 800, "connected": 8 }
}
```

**Response (version gate):**
```json
{ "available": false, "reason": "requires_r81_20", "current_version": "R81.10" }
```

---

### `GET /api/firewalls/gateway/protocols`

Returns BGP peer summary and OSPF note. BGP peers require R82+. Requires the `firewalls` tab.

**Query params:** `domain`, `name`, `type`

**Response:**
```json
{
  "target_member": null,
  "bgp": {
    "available": true,
    "groups": [{ "as": 65000, "num-peers": 2, "num-peers-est": 2 }],
    "peers": [
      {
        "peer": "10.0.0.2",
        "remote-as": 65001,
        "state": "Established",
        "uptime": "3d 12h",
        "received": { "routes-received": 124, "routes-received-active": 100 }
      }
    ]
  },
  "ospf": {
    "available": true,
    "note": "OSPF route count is shown in the Routing Table tab. The `available` flag is a static marker; use the gateway CLI for live OSPF neighbor state."
  }
}
```

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
| `GET` | `/api/rule-review/where-used?domain=<name>&uid=<uid>&name=<object-name>` | Find all access rules that reference an object by UID |

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

### `GET /api/rule-review/where-used` response

```json
{
  "object_name": "Host-WebServer",
  "domain": "Corp-DC1",
  "total": 2,
  "rules": [
    {
      "rule_name": "Allow-Web",
      "rule_number": 3,
      "package": "Standard_Policy",
      "package_domain": "Corp-DC1",
      "layer": "Network",
      "columns": [],
      "is_global": false
    }
  ]
}
```

---

## Device Review

All endpoints require the `device_review` tab.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/device-review/summary` | Cross-domain version distribution from the background cache |
| `POST` | `/api/device-review/refresh` | Trigger an immediate background refresh of the version cache. Returns `{"status": "refreshing"}` (202). |
| `GET` | `/api/device-review/devices?domain=<name>` | Fetch full device list for a single domain live from the CP API |

### `GET /api/device-review/summary` response

```json
{
  "status": "ok",
  "total": 39,
  "domain_count": 5,
  "domains_ok": 5,
  "last_updated": "2026-09-21T13:40:00+00:00",
  "by_version": [
    {
      "version": "R81.10",
      "count": 23,
      "pct": 59.0,
      "devices": [
        {"name": "gw-dc1-01", "type": "Gateway", "domain": "DC1", "ip": "10.x.x.x"}
      ]
    }
  ]
}
```

`status` values: `"empty"` | `"collecting"` | `"ok"` | `"error"`

### `GET /api/device-review/devices` response

```json
{
  "domain": "DC1-Domain",
  "devices": [
    {
      "name": "gw-dc1-01",
      "type": "Gateway",
      "ip": "10.x.x.x",
      "version": "R81.10",
      "os": "Gaia",
      "hardware": "5000 Appliances",
      "blades": ["Firewall", "VPN", "IPS", "Monitoring"],
      "member_count": 0,
      "comments": ""
    }
  ]
}
```

**Error responses:**
- `400` — `domain` parameter missing
- `403` — domain access denied for this user
- Upstream errors are proxied with the Check Point error detail

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
| `POST` | `/admin/api/logs/level` `*` | Set live log level. Body: `{"level": "TRACE\|DEBUG\|INFO\|WARN\|ERROR"}` |
| `DELETE` | `/admin/api/logs` `*` | Clear all in-memory log entries |
| `GET` | `/admin/api/tabs` `*` | List registered tab keys and labels |
| `GET` | `/admin/api/settings` `*` | Get all application settings |
| `PUT` | `/admin/api/settings` `*` | Update settings. Body: `{"key": value, ...}` |

**All mutating endpoints require a valid CSRF token** (`X-CSRF-Token` header or `csrf_token` form field). Obtain the token from the session after login.
