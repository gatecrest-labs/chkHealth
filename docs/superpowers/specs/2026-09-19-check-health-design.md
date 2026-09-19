# check.health — Design Spec

**Date:** 2026-09-19
**Status:** Approved

---

## Overview

`check.health` is a Flask web application that provides a read-only operational dashboard for a Check Point Provider-1 (MDS) environment. It connects to two MDS servers configured as an HA pair across two datacenters, plus two MLS (log) servers. The app exposes three user-facing tabs (Dashboard, Firewalls, Rule Review) and an Admin tab, and is built to be run locally on macOS for development and eventually deployed as a public-facing (open-source) project.

The architecture is modeled after the `4thealth` project: Flask + UV + APScheduler + SQLite, local bcrypt authentication, blueprint-based routing, and Jinja2 server-rendered templates with vanilla JS.

---

## Tech Stack

| Component | Choice |
|---|---|
| Language | Python ≥ 3.11 |
| Package manager | UV |
| Web framework | Flask ≥ 3.1 |
| Scheduler | APScheduler ≥ 3.11 |
| Auth | bcrypt (local), roles: admin / viewer |
| History store | SQLite via stdlib `sqlite3` |
| HTTP client | requests |
| Frontend | Jinja2 templates + vanilla JS |

Dependencies: `flask`, `requests`, `bcrypt`, `apscheduler`, `openpyxl`, `cryptography`, `psutil`, `pyyaml`, `python-dotenv`.

---

## Repo Layout

```
check.health/
├── app/
│   ├── __init__.py               Flask app factory, blueprint registration
│   ├── config.py                 Config class — reads .env
│   ├── auth.py                   Local bcrypt auth
│   ├── cp_client.py              Check Point MDS REST client
│   ├── cp_helpers.py             make_client() factory + HA failover
│   ├── domain_cache.py           Cached domain/gateway list
│   ├── infra_health_cache.py     MDS + MLS health polling (in-memory)
│   ├── summary_job.py            APScheduler job — gateway + rule counts
│   ├── host_metrics.py           SQLite history store (metrics.db)
│   ├── registry.py               Nav tab registry
│   ├── decorators.py             tab_required, admin_required
│   ├── security.py               CSRF helpers, error response helpers
│   ├── groups.py                 Group/domain access control
│   ├── app_logger.py             In-memory log buffer
│   ├── app_settings.py           Persistent key/value settings (JSON)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth_routes.py
│   │   ├── dashboard_routes.py
│   │   ├── firewall_routes.py
│   │   ├── rule_review_routes.py
│   │   └── admin_routes.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── dashboard.html
│   │   ├── firewalls.html
│   │   ├── rule_review.html
│   │   └── admin.html
│   └── static/
│       ├── css/
│       └── js/
├── docs/
│   └── superpowers/specs/        Design specs (this file)
├── ansible/                      Existing — untouched
├── pyproject.toml
├── .env.example
├── .gitignore
├── users.example.json
├── groups.example.json
├── manage_users.py
├── wsgi.py
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── CODE_OF_CONDUCT.md
```

---

## Configuration

All runtime secrets and host addresses live in `.env` (never committed). `.env.example` ships with placeholder values.

```ini
# Check Point MDS (HA pair — two datacenters)
CP_MDS_PRIMARY=10.x.x.x
CP_MDS_SECONDARY=10.x.x.x
CP_API_KEY=<your-read-only-api-key>
CP_VERIFY_SSL=false

# Optional display labels for infrastructure health cards
CP_MDS_PRIMARY_LABEL=MDS Primary (DC1)
CP_MDS_SECONDARY_LABEL=MDS Secondary (DC2)

# Log servers (MLS)
CP_MLS_1=10.x.x.x
CP_MLS_2=10.x.x.x
CP_MLS_1_LABEL=MLS Primary
CP_MLS_2_LABEL=MLS Secondary

# Flask
SECRET_KEY=<random-secret-at-least-32-chars>
FLASK_ENV=development
```

### Local dev startup

```bash
cd check.health
uv sync
cp .env.example .env          # fill in real values
python manage_users.py add admin --role admin
uv run flask --app app run --debug
```

---

## Check Point MDS Client (`cp_client.py`)

### Authentication

- Login: `POST /web_api/login {"api-key": "..."}` → `{"sid": "...", ...}`
- Domain-context login: `POST /web_api/login {"api-key": "...", "domain": "<name>"}` → domain-scoped `sid`
- All API calls carry header `X-chkp-sid: <sid>`
- Logout: `POST /web_api/logout {}`
- SSL verification controlled by `CP_VERIFY_SSL`; defaults to `false` for self-signed certs

### Session model

Short-lived per-request sessions via context manager:

```python
with make_client() as client:
    domains = client.get_domains()
```

`__enter__` logs in; `__exit__` logs out. No cross-request session reuse — avoids idle-timeout complexity for a read-only workload.

### HA failover

`make_client()` tries the primary MDS first. On connection or login failure it retries against the secondary. The active host is logged. There is no persistent "which is active" state — each call re-probes, which is appropriate for a low-frequency read-only app.

### Known API endpoints

| Method | Endpoint | Scope | Purpose |
|---|---|---|---|
| POST | `login` | Global | Authenticate; receive sid |
| POST | `logout` | Any | End session |
| POST | `show-domains` | Global | List all domains |
| POST | `show-simple-gateways` | Domain | Gateway list |
| POST | `show-simple-clusters` | Domain | Cluster list |
| POST | `show-packages` | Domain | Policy package list |
| POST | `show-access-rulebase` | Domain | Rules in a package |
| POST | `show-objects` | Domain | Object search by name |
| POST | `show-nat-rulebase` | Domain | NAT rules |
| POST | `show-api-versions` | Global | API version / connectivity check |

**TODO (discovery required):** Endpoint for MDS system info (hostname, version, serial number, HA role, CPU/MEM). Candidate: `show-mdss` or a system-status endpoint. Until confirmed, `get_system_info()` returns version from `show-api-versions` and marks remaining fields `null` (displayed as "N/A").

---

## Dashboard Tab

### Summary tiles

Two large tiles across the top:
- **Managed Gateways/Clusters** — total count across all domains
- **Policy Rules Managed** — total rules across all policy packages in all domains

Both values come from the background `summary_job` cache (never block on page load). Refresh button re-triggers the job. "Counts as of `<timestamp>`" shown.

Rule count may be expensive (requires iterating all packages in all domains). It runs exclusively in the background; the dashboard always shows the last cached value.

### 30-day trend sparklines

Two side-by-side area charts:
- "Managed Gateways — 30 Days"
- "Policy Rules — 30 Days"

Data stored in `metrics.db` (SQLite, at the project root — same level as `pyproject.toml`, excluded from git):

```sql
CREATE TABLE summary_history (
    date       TEXT PRIMARY KEY,   -- YYYY-MM-DD
    gw_count   INTEGER NOT NULL,
    rule_count INTEGER NOT NULL
);
```

One row per calendar day, upserted by the scheduler. Charts render the last 30 rows.

### Infrastructure Health

Section header: "Infrastructure Health" with last-updated timestamp and refresh interval selector (5 / 15 / 30 min).

Four cards in order:
1. MDS Primary (DC1)
2. MDS Secondary (DC2)
3. MLS 1
4. MLS 2

Each card shows:
- Display label + IP address + type badge ("MDS" or "MLS")
- Hostname
- Version
- Serial number
- HA Role (Active / Standby for MDS; N/A for MLS)
- CPU / MEM (if available)

Card left-border color:
- Green — healthy / reachable
- Red — unreachable or login failure
- Yellow — reachable but data partially unavailable

MDS health: queried via CP Management API.
MLS health: connectivity check (TCP port 443 or 18184) + any data the MDS API exposes about registered log servers. Exact API endpoint is a discovery TODO.

Background job `infra_health_cache` polls every 15 minutes (configurable) and stores results in memory for fast dashboard response.

---

## Firewalls Tab

### Domain selector

Dropdown populated on page load from `show-domains`. Selecting a domain loads the firewall table.

### Firewall table

Columns: **Name**, **Type** (Gateway / Cluster), **Management IP**, **Version**, **SIC Status**, **Comments**

- SIC Status color-coded: green = `communicating`, red = any other state
- Table sortable by clicking column headers
- Data from `show-simple-gateways` + `show-simple-clusters` with `details-level: full`

### Details panel

Clicking a row opens a modal with:
- All table fields
- Policy packages installed on this gateway (from `show-packages` matched to scope members)
- Software blades enabled (if returned by full-details API response)
- Last connect time (if available)
- Full SIC state string

No VDOM section — not applicable to Check Point.

---

## Rule Review Tab

Four independent sections on one page. Each has its own domain selector.

### 1 — Policy Rules

- Domain dropdown → Policy Package dropdown (populated from `show-packages`)
- Optional: type package name directly as an alternative to the dropdown
- **Load** button → fetches rules via `show-access-rulebase`
- Rules table columns: `#`, Name, Source, Destination, Service, Action (Accept/Drop — color-coded), Track, Enabled
- Large rulebases fetched with `offset`/`limit` pagination; all pages loaded before display

### 2 — Object Lookup

- Domain dropdown → Object Name text field (name or partial name) → **Search**
- API: `show-objects` with name filter
- Results table: Name, Type (host / network / group / address-range), IP or IP range, group members (if applicable)

### 3 — Interface Lookup

- Domain dropdown → IP Address(es) field (comma-separated) → **Search**
- Fetches gateways + clusters (full details), matches each input IP against interface addresses
- Results: Gateway/Cluster Name, Interface Name, Matched IP, Subnet

### 4 — NAT Lookup

- Domain dropdown → single IP Address → **Search**
- Fetches `show-nat-rulebase` for all packages in the domain, matches rules where original or translated source/destination covers the input IP
- Results: Package, Rule #, Original Src/Dst/Service, Translated Src/Dst/Service

**TODO (discovery required):** Exact `show-objects` filter parameter for partial-name search; NAT rulebase scope (global policy vs per-package). These will be confirmed against the live API before implementation.

---

## Admin Tab

Identical in structure to the 4thealth admin tab:

| Feature | Details |
|---|---|
| Users | Local bcrypt accounts in `users.json`; `manage_users.py` CLI for add/reset/delete |
| Groups | `groups.json` — name, members, allowed_tabs, domain_restrict (bool), allowed_domains |
| Logs | In-memory buffer, filterable by level/component; log level toggle (DEBUG/INFO/WARNING) |
| Settings | Persistent key/value JSON file (e.g. scheduler interval) |
| Tab registry | Read-only display of registered tab keys and display names |

Roles: `admin` (full access) and `viewer` (tab access controlled by group membership).

Domain restriction in groups replaces ADOM restriction from 4thealth — same logic, different key name.

---

## Security Considerations

This will be a public open-source repository. The following must hold before any commit:

- `.gitignore` covers: `.env`, `users.json`, `groups.json`, `app_settings.json`, `api_tokens.json`, `*.db`, `__pycache__/`, `.venv/`, `*.pyc`, `dist/`, `*.egg-info/`
- All credential files have `.example` counterparts with placeholder values
- No real hostnames, IPs, API keys, or internal network details in any committed file
- CSRF protection on all state-changing POST endpoints
- Security headers set on all responses (X-Content-Type-Options, X-Frame-Options, CSP, etc.)
- `SECURITY.md` documents the responsible disclosure process

---

## Public Repo Readiness Tasks

The following documentation files must be authored before the repository is made public:

- `README.md` — overview, features, local setup instructions, screenshot placeholder
- `CHANGELOG.md` — initial `[Unreleased]` section
- `CONTRIBUTING.md` — how to contribute, branch conventions, PR process
- `SECURITY.md` — responsible disclosure policy, what to report
- `CODE_OF_CONDUCT.md` — Contributor Covenant or equivalent

---

## Open TODOs (Discovery Required)

| # | Item |
|---|---|
| 1 | MDS system-info API endpoint (hostname, serial, HA role, CPU/MEM) |
| 2 | MLS health API endpoint (via MDS or direct) |
| 3 | `show-objects` partial-name filter parameter |
| 4 | NAT rulebase scope: global policy vs per-package |

These will be resolved against the live API during implementation. Each has a fallback (N/A display or graceful empty result) so they do not block other work.
