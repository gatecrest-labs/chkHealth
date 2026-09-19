# Plan 3: Firewalls Tab + Rule Review Tab

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new tabs to check.health: Firewalls (domain-scoped gateway/cluster browser with details modal) and Rule Review (policy rules, object lookup, interface lookup, NAT lookup — all domain-scoped). All data fetched live from the CP Management API via the existing `CPClient` / `make_client()` stack.

**Architecture:** Two new Flask blueprints (`firewalls`, `rule_review`) with GET-only API routes. `CPClient._fetch_all` is extended with a `key` parameter to support API responses that use keys other than `"objects"`. Four new convenience methods are added to `CPClient`. All user-supplied data flows through `esc()` in the JS before touching innerHTML.

**Tech Stack:** Python ≥ 3.11, Flask ≥ 3.1, UV, requests, `unittest.mock` (no live API calls in tests)

**Spec:** `docs/superpowers/specs/2026-09-19-check-health-design.md`

## Global Constraints

- Python ≥ 3.11 — use union type hints `X | Y`
- UV package manager — never `pip install` directly
- No real hostnames, IPs, API keys, or credentials in any committed file
- Public repo — no internal references anywhere in committed code
- No what-comments or what-docstrings
- TDD: write failing test first, then implement
- `requests` + `unittest.mock` — no live API calls in tests
- CSRF not needed on GET-only routes; `login_required` + `tab_required` on all routes
- All user data in HTML/JS through `esc()`
- `check_domain_access(domain)` called at top of every domain-scoped API handler
- Test runner: `uv run pytest`
- All new tests must pass alongside the existing Plan 1 + 2 test suite (84 tests)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/cp_client.py` | Modify | Add `key` param to `_fetch_all`; fix `get_packages`, `get_access_rulebase`; add `get_nat_rulebase`, `get_objects`, `get_gateway_full`, `get_cluster_full` |
| `app/routes/firewall_routes.py` | Create | Firewalls blueprint + 3 API endpoints |
| `app/templates/firewalls.html` | Create | Domain selector, sortable gateway/cluster table, details modal |
| `app/static/js/firewalls.js` | Create | Fetch domains, load table, sort, modal |
| `app/routes/rule_review_routes.py` | Create | Rule Review blueprint + 5 API endpoints |
| `app/templates/rule_review.html` | Create | Four sections: Policy Rules, Object Lookup, Interface Lookup, NAT Lookup |
| `app/static/js/rule_review.js` | Create | Four section loaders |
| `app/__init__.py` | Modify | Add both blueprints to `_BLUEPRINT_MODULES` |
| `app/static/css/app.css` | Modify | Append Firewalls + Rule Review styles |
| `tests/test_cp_client.py` | Modify | Update existing test + add tests for new methods |
| `tests/test_firewall_routes.py` | Create | Firewalls API route tests |
| `tests/test_rule_review_routes.py` | Create | Rule Review API route tests |

---

### Task 1: `CPClient` additions — `_fetch_all` key param + new methods

**Files:**
- Modify: `app/cp_client.py`
- Modify: `tests/test_cp_client.py`

**Interfaces:**
- `_fetch_all(command, extra=None, key="objects") -> list[dict]` — `key` selects which response field to read
- `get_packages() -> list[dict]` — fixed to use `key="packages"`
- `get_access_rulebase(package) -> list[dict]` — fixed to use `key="rulebase"`
- `get_nat_rulebase(package: str) -> list[dict]` — NEW
- `get_objects(name_filter: str) -> list[dict]` — NEW, limit=200
- `get_gateway_full(name: str) -> dict` — NEW
- `get_cluster_full(name: str) -> dict` — NEW

- [ ] **Step 1: Write new failing tests** — add to `tests/test_cp_client.py`

```python
def test_get_packages_uses_packages_key(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "packages": [{"name": "Pkg1"}, {"name": "Pkg2"}], "total": 2, "success": True,
    })):
        pkgs = client.get_packages()
    assert len(pkgs) == 2
    assert pkgs[0]["name"] == "Pkg1"


def test_get_access_rulebase_uses_rulebase_key(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "rulebase": [{"uid": "r1"}, {"uid": "r2"}], "total": 2, "success": True,
    })):
        rules = client.get_access_rulebase("Pkg1")
    assert len(rules) == 2


def test_get_nat_rulebase_uses_rulebase_key(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "rulebase": [{"uid": "n1"}], "total": 1, "success": True,
    })):
        rules = client.get_nat_rulebase("Pkg1")
    assert len(rules) == 1
    assert rules[0]["uid"] == "n1"


def test_get_objects_returns_objects(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "objects": [{"name": "host1", "type": "host"}], "total": 1, "success": True,
    })):
        objs = client.get_objects("host1")
    assert objs[0]["name"] == "host1"


def test_get_objects_uses_limit_200(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "objects": [], "total": 0, "success": True,
    })) as mock_post:
        client.get_objects("anything")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["limit"] == 200


def test_get_gateway_full_returns_dict(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "name": "gw1", "ipv4-address": "10.0.0.1", "success": True,
    })):
        gw = client.get_gateway_full("gw1")
    assert gw["name"] == "gw1"


def test_get_cluster_full_returns_dict(client):
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "name": "cl1", "ipv4-address": "10.0.0.2", "success": True,
    })):
        cl = client.get_cluster_full("cl1")
    assert cl["name"] == "cl1"


def test_fetch_all_key_param_used(client):
    """_fetch_all stops when empty list returned for the given key."""
    client._sid = "sid"
    with patch.object(client._session, "post", return_value=_resp({
        "packages": [], "total": 0, "success": True,
    })):
        result = client._fetch_all("show-packages", key="packages")
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cp_client.py -v -k "packages or rulebase or nat or objects or full or key_param"
```

Expected: 8 failures — methods not yet updated.

- [ ] **Step 3: Update `app/cp_client.py`**

Replace `_fetch_all` and the affected methods:

```python
def _fetch_all(self, command: str, extra: dict | None = None, key: str = "objects") -> list[dict]:
    results: list[dict] = []
    offset = 0
    limit = 500
    while True:
        data = self.call(command, {"limit": limit, "offset": offset, **(extra or {})})
        objects = data.get(key, [])
        if not objects:
            break
        results.extend(objects)
        if len(results) >= data.get("total", len(results)):
            break
        offset += limit
    return results

def get_packages(self) -> list[dict]:
    return self._fetch_all("show-packages", key="packages")

def get_access_rulebase(self, package: str) -> list[dict]:
    return self._fetch_all("show-access-rulebase", {"name": package}, key="rulebase")

def get_nat_rulebase(self, package: str) -> list[dict]:
    return self._fetch_all("show-nat-rulebase", {"name": package}, key="rulebase")

def get_objects(self, name_filter: str) -> list[dict]:
    return self._fetch_all(
        "show-objects",
        {"filter": name_filter, "type": "object", "limit": 200},
        key="objects",
    )

def get_gateway_full(self, name: str) -> dict:
    return self.call("show-simple-gateways", {"name": name, "details-level": "full"})

def get_cluster_full(self, name: str) -> dict:
    return self.call("show-simple-clusters", {"name": name, "details-level": "full"})
```

Note: `get_objects` passes `limit=200` inside `extra` — the `_fetch_all` call will merge it into the payload, overriding the default `limit=500`. This is intentional; object search is UI-interactive so 200 is the cap.

- [ ] **Step 4: Run full cp_client test suite**

```bash
uv run pytest tests/test_cp_client.py -v
```

Expected: All tests PASS (existing 8 + new 8 = 16 total).

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
uv run pytest -v
```

Expected: All existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/cp_client.py tests/test_cp_client.py
git commit -m "feat: add key param to _fetch_all and new CPClient methods for firewalls and rule review

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Firewalls blueprint + API

**Files:**
- Create: `app/routes/firewall_routes.py`
- Create: `tests/test_firewall_routes.py`
- Modify: `app/__init__.py` — add `"app.routes.firewall_routes"` to `_BLUEPRINT_MODULES`

**Interfaces (Blueprint `firewalls`, url_prefix `/`):**
- `GET  /firewalls` → render `firewalls.html` `[login_required, tab_required("firewalls")]`
- `GET  /api/firewalls/domains` → `{"domains": ["D1", "D2"]}` `[login_required]`
- `GET  /api/firewalls/gateways?domain=X` → `{"gateways": [...], "clusters": [...], "domain": "X"}` `[login_required, tab_required("firewalls"), check_domain_access]`
- `GET  /api/firewalls/gateway?domain=X&name=Y&type=Z` → full details dict `[login_required, tab_required("firewalls"), check_domain_access]`

Blueprint self-registers: `register("firewalls", "Firewalls", "firewalls.firewalls_page", icon="🔥")`

`/api/firewalls/domains` returns names the current user can access (filtered by `get_allowed_domains`). Admin users see all cached domains.

`/api/firewalls/gateways` returns gateways and clusters sorted by name. Each item is the short-form object returned by `get_gateways()` / `get_clusters()`.

`/api/firewalls/gateway` fetches full details via `get_gateway_full(name)` or `get_cluster_full(name)` depending on `type` query param (`"gateway"` or `"cluster"`). Returns the raw dict from the API.

- [ ] **Step 1: Write failing tests**

Create `tests/test_firewall_routes.py`:

```python
import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def fw_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    import app.groups as groups_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = ["firewalls"]
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
        sess["_csrf_token"] = "test-token"
    return client


def _mock_cm(gateways=None, clusters=None):
    mock_client = MagicMock()
    mock_client.get_gateways.return_value = gateways or [
        {"name": "gw1", "ipv4-address": "10.0.0.1"}
    ]
    mock_client.get_clusters.return_value = clusters or []
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, mock_client


def test_firewalls_page_loads(fw_client):
    r = fw_client.get("/firewalls")
    assert r.status_code == 200


def test_firewalls_page_requires_login(client):
    r = client.get("/firewalls")
    assert r.status_code in (302, 401)


def test_domains_api_returns_list(fw_client, monkeypatch):
    monkeypatch.setattr(
        "app.domain_cache.get_cached_domains",
        lambda: {"domains": [{"name": "D1"}, {"name": "D2"}], "status": "ok"},
    )
    r = fw_client.get("/api/firewalls/domains")
    assert r.status_code == 200
    data = r.get_json()
    assert "domains" in data
    assert "D1" in data["domains"]


def test_gateways_api_returns_sorted(fw_client):
    cm, _ = _mock_cm(
        gateways=[{"name": "zGW"}, {"name": "aGW"}],
        clusters=[{"name": "cl1"}],
    )
    with patch("app.routes.firewall_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateways?domain=D1")
    assert r.status_code == 200
    data = r.get_json()
    assert data["gateways"][0]["name"] == "aGW"
    assert data["gateways"][1]["name"] == "zGW"
    assert data["clusters"][0]["name"] == "cl1"
    assert data["domain"] == "D1"


def test_gateways_api_requires_domain(fw_client):
    r = fw_client.get("/api/firewalls/gateways")
    assert r.status_code == 400


def test_gateway_detail_gateway_type(fw_client):
    mock_client = MagicMock()
    mock_client.get_gateway_full.return_value = {
        "name": "gw1", "ipv4-address": "10.0.0.1", "success": True
    }
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    with patch("app.routes.firewall_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway?domain=D1&name=gw1&type=gateway")
    assert r.status_code == 200
    assert r.get_json()["name"] == "gw1"


def test_gateway_detail_cluster_type(fw_client):
    mock_client = MagicMock()
    mock_client.get_cluster_full.return_value = {
        "name": "cl1", "ipv4-address": "10.0.0.2", "success": True
    }
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    with patch("app.routes.firewall_routes.make_client", return_value=cm):
        r = fw_client.get("/api/firewalls/gateway?domain=D1&name=cl1&type=cluster")
    assert r.status_code == 200
    assert r.get_json()["name"] == "cl1"


def test_gateway_detail_invalid_type(fw_client):
    r = fw_client.get("/api/firewalls/gateway?domain=D1&name=gw1&type=unknown")
    assert r.status_code == 400


def test_gateways_api_upstream_error(fw_client):
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("MDS down")
    with patch("app.routes.firewall_routes.make_client", return_value=bad_cm):
        r = fw_client.get("/api/firewalls/gateways?domain=D1")
    assert r.status_code == 502
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_firewall_routes.py -v
```

Expected: ImportError or 404 — blueprint not yet registered.

- [ ] **Step 3: Create `app/routes/firewall_routes.py`**

```python
from flask import Blueprint, jsonify, render_template, request, session

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.security import internal_api_error, upstream_api_error

registry.register("firewalls", "Firewalls", "firewalls.firewalls_page", icon="🔥")

bp = Blueprint("firewalls", __name__)


@bp.route("/firewalls")
@login_required
@tab_required("firewalls")
def firewalls_page():
    return render_template("firewalls.html")


@bp.route("/api/firewalls/domains")
@login_required
def api_firewalls_domains():
    from app.domain_cache import get_cached_domains
    from app.groups import get_allowed_domains

    cached = get_cached_domains()
    all_domains = [d["name"] for d in cached.get("domains", [])]

    role = session.get("role", "viewer")
    if role == "admin":
        return jsonify({"domains": sorted(all_domains)})

    allowed = get_allowed_domains(
        session.get("user", ""),
        ad_groups=session.get("ad_groups", []),
    )
    if allowed is None:
        return jsonify({"domains": sorted(all_domains)})
    return jsonify({"domains": sorted(d for d in all_domains if d in allowed)})


@bp.route("/api/firewalls/gateways")
@login_required
@tab_required("firewalls")
def api_firewalls_gateways():
    domain = request.args.get("domain", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            gateways = sorted(client.get_gateways(), key=lambda g: g.get("name", ""))
            clusters = sorted(client.get_clusters(), key=lambda c: c.get("name", ""))
        return jsonify({"gateways": gateways, "clusters": clusters, "domain": domain})
    except Exception as exc:
        return upstream_api_error("firewalls", exc)


@bp.route("/api/firewalls/gateway")
@login_required
@tab_required("firewalls")
def api_firewalls_gateway():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    obj_type = request.args.get("type", "").strip().lower()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if obj_type not in ("gateway", "cluster"):
        return jsonify({"error": "type must be 'gateway' or 'cluster'"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            if obj_type == "gateway":
                details = client.get_gateway_full(name)
            else:
                details = client.get_cluster_full(name)
        return jsonify(details)
    except Exception as exc:
        return upstream_api_error("firewalls", exc)
```

- [ ] **Step 4: Add `"app.routes.firewall_routes"` to `_BLUEPRINT_MODULES` in `app/__init__.py`**

Edit `app/__init__.py` — update `_BLUEPRINT_MODULES`:

```python
_BLUEPRINT_MODULES = [
    "app.routes.auth_routes",
    "app.routes.admin_routes",
    "app.routes.dashboard_routes",
    "app.routes.firewall_routes",
]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_firewall_routes.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/routes/firewall_routes.py app/__init__.py tests/test_firewall_routes.py
git commit -m "feat: add firewalls blueprint with domains, gateways, and gateway detail API endpoints

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Firewalls template + JS

**Files:**
- Create: `app/templates/firewalls.html`
- Create: `app/static/js/firewalls.js`
- Modify: `app/static/css/app.css` — append Firewalls styles

No automated tests for templates or JS; full suite is the regression guard.

- [ ] **Step 1: Create `app/templates/firewalls.html`**

```html
{% extends "base.html" %}
{% block title %}Firewalls — check.health{% endblock %}

{% block content %}
<div class="page-header">
  <h2>🔥 Firewalls</h2>
</div>

<div class="card mb-3">
  <div class="d-flex gap-2" style="align-items:flex-end;flex-wrap:wrap">
    <div class="form-group" style="margin-bottom:0;min-width:220px">
      <label class="form-label" for="domainSelect">Domain</label>
      <select id="domainSelect" class="form-select">
        <option value="">— select domain —</option>
      </select>
    </div>
    <button id="loadBtn" class="btn btn-primary" disabled>Load</button>
    <span id="loadStatus" class="text-muted" style="font-size:.82rem;align-self:center"></span>
  </div>
</div>

<div id="tableSection" style="display:none">
  <div class="table-wrapper">
    <table class="data-table" id="fwTable">
      <thead>
        <tr>
          <th class="sortable-header" data-sort="name">Name &#8597;</th>
          <th class="sortable-header" data-sort="type">Type &#8597;</th>
          <th class="sortable-header" data-sort="ip">Management IP &#8597;</th>
          <th class="sortable-header" data-sort="version">Version &#8597;</th>
          <th>SIC Status</th>
          <th>Comments</th>
        </tr>
      </thead>
      <tbody id="fwTbody"></tbody>
    </table>
  </div>
</div>

<!-- Details modal -->
<div id="fwModal" class="modal-overlay" style="display:none">
  <div class="modal-box" style="max-width:760px">
    <div class="modal-header">
      <span class="modal-title" id="fwModalTitle">Gateway Details</span>
      <button class="modal-close" id="fwModalClose">&#10005;</button>
    </div>
    <div class="modal-body" id="fwModalBody"></div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/firewalls.js') }}?v=1"></script>
{% endblock %}
```

- [ ] **Step 2: Create `app/static/js/firewalls.js`**

```javascript
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let _allRows = [];   // [{name, type, ip, version, sic, comments, _raw}]
let _sortCol = 'name';
let _sortAsc = true;
let _currentDomain = '';

// ── Domain loader ─────────────────────────────────────────────────────────
async function loadDomains() {
  const r = await fetch('/api/firewalls/domains');
  if (!r.ok) return;
  const data = await r.json();
  const sel = document.getElementById('domainSelect');
  (data.domains || []).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    sel.appendChild(opt);
  });
  sel.addEventListener('change', () => {
    document.getElementById('loadBtn').disabled = !sel.value;
  });
}

// ── Gateway loader ────────────────────────────────────────────────────────
document.getElementById('loadBtn').addEventListener('click', async () => {
  const domain = document.getElementById('domainSelect').value;
  if (!domain) return;
  _currentDomain = domain;
  document.getElementById('loadStatus').textContent = 'Loading…';
  document.getElementById('loadBtn').disabled = true;
  document.getElementById('tableSection').style.display = 'none';
  try {
    const r = await fetch('/api/firewalls/gateways?domain=' + encodeURIComponent(domain));
    if (!r.ok) {
      document.getElementById('loadStatus').textContent = 'Error loading data.';
      return;
    }
    const data = await r.json();
    _allRows = [
      ...(data.gateways || []).map(g => _toRow(g, 'Gateway')),
      ...(data.clusters || []).map(c => _toRow(c, 'Cluster')),
    ];
    document.getElementById('loadStatus').textContent =
      `${_allRows.length} object(s) loaded.`;
    document.getElementById('tableSection').style.display = '';
    renderTable();
  } finally {
    document.getElementById('loadBtn').disabled = false;
  }
});

function _toRow(obj, type) {
  return {
    name: obj.name || '',
    type,
    ip: obj['ipv4-address'] || obj['ipv6-address'] || '',
    version: (obj['os-version'] || {}).version || '',
    sic: (obj['sic-status'] || {}).sic || '',
    comments: obj.comments || '',
    _raw: obj,
  };
}

// ── Sort + render ─────────────────────────────────────────────────────────
document.querySelectorAll('.sortable-header').forEach(th => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    if (_sortCol === col) { _sortAsc = !_sortAsc; }
    else { _sortCol = col; _sortAsc = true; }
    renderTable();
  });
});

function renderTable() {
  const rows = [..._allRows].sort((a, b) => {
    const av = (a[_sortCol] || '').toString().toLowerCase();
    const bv = (b[_sortCol] || '').toString().toLowerCase();
    return _sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  document.getElementById('fwTbody').innerHTML = rows.map(row => {
    const sicOk = row.sic.toLowerCase().includes('communicating');
    const sicBadge = sicOk
      ? `<span class="badge badge-sic-ok">${esc(row.sic)}</span>`
      : `<span class="badge badge-sic-bad">${esc(row.sic || 'Unknown')}</span>`;
    const typeBadge = `<span class="badge badge-type">${esc(row.type)}</span>`;
    return `<tr class="fw-row" data-name="${esc(row.name)}" data-type="${esc(row.type.toLowerCase())}">
      <td>${esc(row.name)}</td>
      <td>${typeBadge}</td>
      <td>${esc(row.ip)}</td>
      <td>${esc(row.version)}</td>
      <td>${sicBadge}</td>
      <td class="truncate-cell" title="${esc(row.comments)}">${esc(row.comments)}</td>
    </tr>`;
  }).join('');

  document.querySelectorAll('.fw-row').forEach(tr => {
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => openModal(tr.dataset.name, tr.dataset.type));
  });
}

// ── Modal ─────────────────────────────────────────────────────────────────
async function openModal(name, type) {
  document.getElementById('fwModal').style.display = 'flex';
  document.getElementById('fwModalTitle').textContent = name;
  document.getElementById('fwModalBody').innerHTML = '<p class="text-muted">Loading…</p>';
  const url = `/api/firewalls/gateway?domain=${encodeURIComponent(_currentDomain)}&name=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}`;
  try {
    const r = await fetch(url);
    if (!r.ok) {
      document.getElementById('fwModalBody').innerHTML = '<p class="text-muted">Error loading details.</p>';
      return;
    }
    const d = await r.json();
    document.getElementById('fwModalBody').innerHTML = renderDetails(d);
  } catch {
    document.getElementById('fwModalBody').innerHTML = '<p class="text-muted">Error loading details.</p>';
  }
}

function renderDetails(d) {
  const row = (label, val) =>
    `<tr><td style="color:var(--text-muted);width:40%;font-size:.82rem">${esc(label)}</td><td>${esc(val ?? '')}</td></tr>`;
  const sic = (d['sic-status'] || {}).sic || '';
  const osVer = (d['os-version'] || {}).version || '';
  const lastConn = d['last-login-details'] ? JSON.stringify(d['last-login-details']) : '';
  let html = `<table class="data-table" style="margin-bottom:1rem">
    <tbody>
      ${row('Name', d.name)}
      ${row('IPv4 Address', d['ipv4-address'])}
      ${row('IPv6 Address', d['ipv6-address'])}
      ${row('Version', osVer)}
      ${row('SIC Status', sic)}
      ${row('Comments', d.comments)}
      ${row('Last Connect', lastConn)}
    </tbody>
  </table>`;

  const pkgs = d['policy-package-names'] || [];
  if (pkgs.length) {
    html += `<strong style="font-size:.85rem">Policy Packages</strong>
      <ul style="margin:.4rem 0 1rem;padding-left:1.2rem;font-size:.875rem">
        ${pkgs.map(p => `<li>${esc(p)}</li>`).join('')}
      </ul>`;
  }

  const blades = d['software-blades'] || {};
  const activeBlades = Object.entries(blades).filter(([, v]) => v === true).map(([k]) => k);
  if (activeBlades.length) {
    html += `<strong style="font-size:.85rem">Active Software Blades</strong>
      <ul style="margin:.4rem 0 0;padding-left:1.2rem;font-size:.875rem">
        ${activeBlades.map(b => `<li>${esc(b)}</li>`).join('')}
      </ul>`;
  }
  return html;
}

document.getElementById('fwModalClose').addEventListener('click', () => {
  document.getElementById('fwModal').style.display = 'none';
});
document.getElementById('fwModal').addEventListener('click', e => {
  if (e.target === document.getElementById('fwModal')) {
    document.getElementById('fwModal').style.display = 'none';
  }
});

// ── Init ──────────────────────────────────────────────────────────────────
loadDomains();
```

- [ ] **Step 3: Append Firewalls styles to `app/static/css/app.css`**

```css
/* ── Firewalls / Rule Review shared ─────────────────────────────────────── */
.badge-type { background: #e0e7ff; color: #3730a3; }
.badge-sic-ok { background: #d1e7dd; color: #0a3622; }
.badge-sic-bad { background: #f8d7da; color: #842029; }
.badge-action-accept { background: #d1e7dd; color: #0a3622; }
.badge-action-drop { background: #f8d7da; color: #842029; }
.sortable-header { cursor: pointer; user-select: none; }
.sortable-header:hover { color: var(--primary); }
.truncate-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rule-review-section { margin-bottom: 2rem; }
```

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/templates/firewalls.html app/static/js/firewalls.js app/static/css/app.css
git commit -m "feat: add firewalls template, JS (domain selector, sortable table, details modal), and CSS

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Rule Review blueprint + API

**Files:**
- Create: `app/routes/rule_review_routes.py`
- Create: `tests/test_rule_review_routes.py`
- Modify: `app/__init__.py` — add `"app.routes.rule_review_routes"` to `_BLUEPRINT_MODULES`

**Interfaces (Blueprint `rule_review`, url_prefix `/`):**
- `GET  /rule-review` → render `rule_review.html` `[login_required, tab_required("rule_review")]`
- `GET  /api/rule-review/packages?domain=X` → `{"packages": [...]}` `[login_required, tab_required("rule_review"), check_domain_access]`
- `GET  /api/rule-review/rules?domain=X&package=P` → `{"rules": [...], "total": N}` `[login_required, tab_required("rule_review"), check_domain_access]`
- `GET  /api/rule-review/objects?domain=X&name=N` → `{"objects": [...]}` `[login_required, tab_required("rule_review"), check_domain_access]`
- `GET  /api/rule-review/interfaces?domain=X&ips=1.2.3.4,5.6.7.8` → `{"results": [...]}` `[login_required, tab_required("rule_review"), check_domain_access]`
- `GET  /api/rule-review/nat?domain=X&ip=1.2.3.4` → `{"results": [...]}` `[login_required, tab_required("rule_review"), check_domain_access]`

Blueprint self-registers: `register("rule_review", "Rule Review", "rule_review.rule_review_page", icon="📋")`

**API details:**
- `/packages` — calls `get_packages()` for the domain, returns `{"packages": [...names sorted...]}`.
- `/rules` — calls `get_access_rulebase(package)`, filters to `type == "access-rule"` entries, caps at 2000, returns `{"rules": [...], "total": N}`. Each rule dict includes: `type`, `name`, `rule-number`, `source`, `destination`, `service`, `action`, `track`, `enabled`, `comments`.
- `/objects` — calls `get_objects(name)`, returns `{"objects": [...]}`.
- `/interfaces` — fetches all gateways and clusters (short form), then for each calls `get_gateway_full` or `get_cluster_full`, extracts interface IPs from `topology` → `interfaces`, matches against input IPs. Returns `{"results": [{"gateway": str, "interface": str, "ip": str, "subnet": str, "mask": str}]}`.
- `/nat` — calls `get_packages()`, then `get_nat_rulebase(package)` for each package, filters rules where `original-source.ip-address`, `original-destination.ip-address`, `translated-source.ip-address`, or `translated-destination.ip-address` equals the input IP (exact string match). Returns `{"results": [...]}`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_rule_review_routes.py`:

```python
import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def rr_client(app_ctx, tmp_path, monkeypatch):
    import app.auth as auth_mod
    import app.groups as groups_mod
    monkeypatch.setattr(auth_mod, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(groups_mod, "GROUPS_FILE", tmp_path / "groups.json")
    auth_mod.add_user("admin", "adminpass", "admin")
    client = app_ctx.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
        sess["allowed_tabs"] = ["rule_review"]
        sess["ad_groups"] = []
        sess["login_at"] = int(time.time())
        sess["_csrf_token"] = "test-token"
    return client


def _make_cm(mock_client):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_client)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_rule_review_page_loads(rr_client):
    r = rr_client.get("/rule-review")
    assert r.status_code == 200


def test_rule_review_page_requires_login(client):
    r = client.get("/rule-review")
    assert r.status_code in (302, 401)


def test_packages_api(rr_client):
    mock_client = MagicMock()
    mock_client.get_packages.return_value = [
        {"name": "PkgB"}, {"name": "PkgA"},
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/packages?domain=D1")
    assert r.status_code == 200
    data = r.get_json()
    assert data["packages"] == ["PkgA", "PkgB"]


def test_packages_requires_domain(rr_client):
    r = rr_client.get("/api/rule-review/packages")
    assert r.status_code == 400


def test_rules_api_filters_access_rules(rr_client):
    mock_client = MagicMock()
    mock_client.get_access_rulebase.return_value = [
        {"type": "access-rule", "name": "Rule1", "rule-number": 1,
         "source": [], "destination": [], "service": [], "action": {"name": "Accept"},
         "track": {}, "enabled": True, "comments": ""},
        {"type": "section-title", "name": "Section"},
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/rules?domain=D1&package=Pkg1")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert len(data["rules"]) == 1
    assert data["rules"][0]["name"] == "Rule1"


def test_rules_requires_domain_and_package(rr_client):
    r = rr_client.get("/api/rule-review/rules?domain=D1")
    assert r.status_code == 400
    r2 = rr_client.get("/api/rule-review/rules?package=Pkg1")
    assert r2.status_code == 400


def test_objects_api(rr_client):
    mock_client = MagicMock()
    mock_client.get_objects.return_value = [
        {"name": "host1", "type": "host", "ipv4-address": "10.0.0.1"}
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/objects?domain=D1&name=host1")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["objects"]) == 1


def test_nat_api_filters_by_ip(rr_client):
    mock_client = MagicMock()
    mock_client.get_packages.return_value = [{"name": "Pkg1"}]
    mock_client.get_nat_rulebase.return_value = [
        {
            "type": "nat-rule",
            "rule-number": 1,
            "original-source": {"ip-address": "10.1.1.1"},
            "original-destination": {"ip-address": "any"},
            "translated-source": {"ip-address": "10.2.2.2"},
            "translated-destination": {"ip-address": "original"},
        },
        {
            "type": "nat-rule",
            "rule-number": 2,
            "original-source": {"ip-address": "192.168.1.1"},
            "original-destination": {"ip-address": "any"},
            "translated-source": {"ip-address": "original"},
            "translated-destination": {"ip-address": "original"},
        },
    ]
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/nat?domain=D1&ip=10.1.1.1")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["results"]) == 1
    assert data["results"][0]["rule-number"] == 1


def test_interfaces_api(rr_client):
    mock_client = MagicMock()
    mock_client.get_gateways.return_value = [{"name": "gw1"}]
    mock_client.get_clusters.return_value = []
    mock_client.get_gateway_full.return_value = {
        "name": "gw1",
        "interfaces": [
            {"name": "eth0", "ipv4-address": "10.0.0.1",
             "ipv4-network-mask": "255.255.255.0", "subnet4": "10.0.0.0"}
        ],
    }
    with patch("app.routes.rule_review_routes.make_client", return_value=_make_cm(mock_client)):
        r = rr_client.get("/api/rule-review/interfaces?domain=D1&ips=10.0.0.1")
    assert r.status_code == 200
    data = r.get_json()
    assert any(res["ip"] == "10.0.0.1" for res in data["results"])


def test_rule_review_upstream_error(rr_client):
    bad_cm = MagicMock()
    bad_cm.__enter__.side_effect = ConnectionError("MDS down")
    with patch("app.routes.rule_review_routes.make_client", return_value=bad_cm):
        r = rr_client.get("/api/rule-review/packages?domain=D1")
    assert r.status_code == 502
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_rule_review_routes.py -v
```

Expected: ImportError or 404 — blueprint not yet registered.

- [ ] **Step 3: Create `app/routes/rule_review_routes.py`**

```python
from flask import Blueprint, jsonify, render_template, request

from app import registry
from app.cp_helpers import make_client
from app.decorators import check_domain_access, login_required, tab_required
from app.security import upstream_api_error

registry.register("rule_review", "Rule Review", "rule_review.rule_review_page", icon="📋")

bp = Blueprint("rule_review", __name__)

_RULE_FIELDS = (
    "type", "name", "rule-number", "source", "destination",
    "service", "action", "track", "enabled", "comments",
)


@bp.route("/rule-review")
@login_required
@tab_required("rule_review")
def rule_review_page():
    return render_template("rule_review.html")


@bp.route("/api/rule-review/packages")
@login_required
@tab_required("rule_review")
def api_rr_packages():
    domain = request.args.get("domain", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            pkgs = client.get_packages()
        names = sorted(p.get("name", "") for p in pkgs if p.get("name"))
        return jsonify({"packages": names})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


@bp.route("/api/rule-review/rules")
@login_required
@tab_required("rule_review")
def api_rr_rules():
    domain = request.args.get("domain", "").strip()
    package = request.args.get("package", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not package:
        return jsonify({"error": "package is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            rulebase = client.get_access_rulebase(package)
        rules = [
            {k: r.get(k) for k in _RULE_FIELDS}
            for r in rulebase
            if r.get("type") == "access-rule"
        ][:2000]
        return jsonify({"rules": rules, "total": len(rules)})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


@bp.route("/api/rule-review/objects")
@login_required
@tab_required("rule_review")
def api_rr_objects():
    domain = request.args.get("domain", "").strip()
    name = request.args.get("name", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        with make_client(domain=domain) as client:
            objects = client.get_objects(name)
        return jsonify({"objects": objects})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


def _extract_interfaces(gw_name: str, details: dict) -> list[dict]:
    results = []
    for iface in details.get("interfaces", []):
        ip = iface.get("ipv4-address", "")
        if ip:
            results.append({
                "gateway": gw_name,
                "interface": iface.get("name", ""),
                "ip": ip,
                "subnet": iface.get("subnet4", ""),
                "mask": iface.get("ipv4-network-mask", ""),
            })
    return results


@bp.route("/api/rule-review/interfaces")
@login_required
@tab_required("rule_review")
def api_rr_interfaces():
    domain = request.args.get("domain", "").strip()
    ips_raw = request.args.get("ips", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not ips_raw:
        return jsonify({"error": "ips is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    target_ips = {ip.strip() for ip in ips_raw.split(",") if ip.strip()}
    try:
        with make_client(domain=domain) as client:
            gateways = client.get_gateways()
            clusters = client.get_clusters()
            results = []
            for gw in gateways:
                name = gw.get("name", "")
                details = client.get_gateway_full(name)
                for entry in _extract_interfaces(name, details):
                    if entry["ip"] in target_ips:
                        results.append(entry)
            for cl in clusters:
                name = cl.get("name", "")
                details = client.get_cluster_full(name)
                for entry in _extract_interfaces(name, details):
                    if entry["ip"] in target_ips:
                        results.append(entry)
        return jsonify({"results": results})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)


def _nat_matches_ip(rule: dict, ip: str) -> bool:
    for field in (
        "original-source", "original-destination",
        "translated-source", "translated-destination",
    ):
        obj = rule.get(field)
        if isinstance(obj, dict) and obj.get("ip-address") == ip:
            return True
    return False


@bp.route("/api/rule-review/nat")
@login_required
@tab_required("rule_review")
def api_rr_nat():
    domain = request.args.get("domain", "").strip()
    ip = request.args.get("ip", "").strip()
    if not domain:
        return jsonify({"error": "domain is required"}), 400
    if not ip:
        return jsonify({"error": "ip is required"}), 400
    err = check_domain_access(domain)
    if err:
        return err
    try:
        results = []
        with make_client(domain=domain) as client:
            packages = client.get_packages()
            for pkg in packages:
                pkg_name = pkg.get("name", "")
                nat_rules = client.get_nat_rulebase(pkg_name)
                for rule in nat_rules:
                    if _nat_matches_ip(rule, ip):
                        results.append({"package": pkg_name, **rule})
        return jsonify({"results": results})
    except Exception as exc:
        return upstream_api_error("rule_review", exc)
```

- [ ] **Step 4: Add `"app.routes.rule_review_routes"` to `_BLUEPRINT_MODULES` in `app/__init__.py`**

Edit `app/__init__.py` — update `_BLUEPRINT_MODULES`:

```python
_BLUEPRINT_MODULES = [
    "app.routes.auth_routes",
    "app.routes.admin_routes",
    "app.routes.dashboard_routes",
    "app.routes.firewall_routes",
    "app.routes.rule_review_routes",
]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_rule_review_routes.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/routes/rule_review_routes.py app/__init__.py tests/test_rule_review_routes.py
git commit -m "feat: add rule review blueprint with packages, rules, objects, interfaces, and NAT API endpoints

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Rule Review template + JS

**Files:**
- Create: `app/templates/rule_review.html`
- Create: `app/static/js/rule_review.js`

No automated tests for templates or JS; full suite is the regression guard.

- [ ] **Step 1: Create `app/templates/rule_review.html`**

```html
{% extends "base.html" %}
{% block title %}Rule Review — check.health{% endblock %}

{% block content %}
<div class="page-header">
  <h2>📋 Rule Review</h2>
</div>

<!-- ── Section 1: Policy Rules ───────────────────────────────────────────── -->
<div class="rule-review-section card">
  <h3 style="margin-top:0;font-size:1rem">Policy Rules</h3>
  <div class="d-flex gap-2" style="flex-wrap:wrap;align-items:flex-end;margin-bottom:1rem">
    <div class="form-group" style="margin-bottom:0;min-width:200px">
      <label class="form-label">Domain</label>
      <select id="rulesDomainSelect" class="form-select">
        <option value="">— select domain —</option>
      </select>
    </div>
    <div class="form-group" style="margin-bottom:0;min-width:200px">
      <label class="form-label">Package</label>
      <select id="rulesPackageSelect" class="form-select" disabled>
        <option value="">— select package —</option>
      </select>
    </div>
    <button id="rulesLoadBtn" class="btn btn-primary" disabled>Load</button>
    <span id="rulesStatus" class="text-muted" style="font-size:.82rem;align-self:center"></span>
  </div>
  <div id="rulesTableSection" style="display:none">
    <div class="table-wrapper" style="max-height:500px;overflow-y:auto">
      <table class="data-table">
        <thead>
          <tr>
            <th>#</th><th>Name</th><th>Source</th><th>Destination</th>
            <th>Service</th><th>Action</th><th>Enabled</th><th>Comments</th>
          </tr>
        </thead>
        <tbody id="rulesTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── Section 2: Object Lookup ──────────────────────────────────────────── -->
<div class="rule-review-section card">
  <h3 style="margin-top:0;font-size:1rem">Object Lookup</h3>
  <div class="d-flex gap-2" style="flex-wrap:wrap;align-items:flex-end;margin-bottom:1rem">
    <div class="form-group" style="margin-bottom:0;min-width:200px">
      <label class="form-label">Domain</label>
      <select id="objDomainSelect" class="form-select">
        <option value="">— select domain —</option>
      </select>
    </div>
    <div class="form-group" style="margin-bottom:0;min-width:200px">
      <label class="form-label">Object Name</label>
      <input type="text" id="objNameInput" class="form-control" placeholder="e.g. web-server">
    </div>
    <button id="objSearchBtn" class="btn btn-primary">Search</button>
    <span id="objStatus" class="text-muted" style="font-size:.82rem;align-self:center"></span>
  </div>
  <div id="objTableSection" style="display:none">
    <div class="table-wrapper">
      <table class="data-table">
        <thead><tr><th>Name</th><th>Type</th><th>IP / Range</th><th>Comments</th></tr></thead>
        <tbody id="objTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── Section 3: Interface Lookup ───────────────────────────────────────── -->
<div class="rule-review-section card">
  <h3 style="margin-top:0;font-size:1rem">Interface Lookup</h3>
  <div class="d-flex gap-2" style="flex-wrap:wrap;align-items:flex-end;margin-bottom:1rem">
    <div class="form-group" style="margin-bottom:0;min-width:200px">
      <label class="form-label">Domain</label>
      <select id="ifDomainSelect" class="form-select">
        <option value="">— select domain —</option>
      </select>
    </div>
    <div class="form-group" style="margin-bottom:0;min-width:260px">
      <label class="form-label">IP Address(es) — comma-separated</label>
      <input type="text" id="ifIpsInput" class="form-control" placeholder="e.g. 10.0.0.1,10.0.0.2">
    </div>
    <button id="ifSearchBtn" class="btn btn-primary">Search</button>
    <span id="ifStatus" class="text-muted" style="font-size:.82rem;align-self:center"></span>
  </div>
  <div id="ifTableSection" style="display:none">
    <div class="table-wrapper">
      <table class="data-table">
        <thead><tr><th>Gateway / Cluster</th><th>Interface</th><th>IP</th><th>Subnet</th><th>Mask</th></tr></thead>
        <tbody id="ifTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── Section 4: NAT Lookup ─────────────────────────────────────────────── -->
<div class="rule-review-section card">
  <h3 style="margin-top:0;font-size:1rem">NAT Lookup</h3>
  <div class="d-flex gap-2" style="flex-wrap:wrap;align-items:flex-end;margin-bottom:1rem">
    <div class="form-group" style="margin-bottom:0;min-width:200px">
      <label class="form-label">Domain</label>
      <select id="natDomainSelect" class="form-select">
        <option value="">— select domain —</option>
      </select>
    </div>
    <div class="form-group" style="margin-bottom:0;min-width:200px">
      <label class="form-label">IP Address</label>
      <input type="text" id="natIpInput" class="form-control" placeholder="e.g. 10.1.2.3">
    </div>
    <button id="natSearchBtn" class="btn btn-primary">Search</button>
    <span id="natStatus" class="text-muted" style="font-size:.82rem;align-self:center"></span>
  </div>
  <div id="natTableSection" style="display:none">
    <div class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Package</th><th>#</th>
            <th>Orig Src</th><th>Orig Dst</th><th>Orig Svc</th>
            <th>Trans Src</th><th>Trans Dst</th><th>Trans Svc</th>
          </tr>
        </thead>
        <tbody id="natTbody"></tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/rule_review.js') }}?v=1"></script>
{% endblock %}
```

- [ ] **Step 2: Create `app/static/js/rule_review.js`**

```javascript
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function objName(obj) {
  if (!obj) return '';
  if (typeof obj === 'string') return obj;
  return obj.name || obj['ip-address'] || JSON.stringify(obj);
}

function nameList(arr) {
  if (!Array.isArray(arr)) return esc(objName(arr));
  return arr.map(o => esc(objName(o))).join(', ') || '—';
}

// ── Shared domain loader ──────────────────────────────────────────────────
async function populateDomainSelect(selectId, onChangeCb) {
  const r = await fetch('/api/firewalls/domains');
  if (!r.ok) return;
  const data = await r.json();
  const sel = document.getElementById(selectId);
  (data.domains || []).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    sel.appendChild(opt);
  });
  if (onChangeCb) sel.addEventListener('change', onChangeCb);
}

// ── Section 1: Policy Rules ───────────────────────────────────────────────
populateDomainSelect('rulesDomainSelect', async () => {
  const domain = document.getElementById('rulesDomainSelect').value;
  const pkgSel = document.getElementById('rulesPackageSelect');
  const loadBtn = document.getElementById('rulesLoadBtn');
  pkgSel.innerHTML = '<option value="">— select package —</option>';
  pkgSel.disabled = true;
  loadBtn.disabled = true;
  if (!domain) return;
  const r = await fetch('/api/rule-review/packages?domain=' + encodeURIComponent(domain));
  if (!r.ok) return;
  const data = await r.json();
  (data.packages || []).forEach(p => {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    pkgSel.appendChild(opt);
  });
  pkgSel.disabled = false;
  pkgSel.addEventListener('change', () => {
    loadBtn.disabled = !pkgSel.value;
  });
});

document.getElementById('rulesLoadBtn').addEventListener('click', async () => {
  const domain = document.getElementById('rulesDomainSelect').value;
  const pkg = document.getElementById('rulesPackageSelect').value;
  if (!domain || !pkg) return;
  document.getElementById('rulesStatus').textContent = 'Loading…';
  document.getElementById('rulesLoadBtn').disabled = true;
  document.getElementById('rulesTableSection').style.display = 'none';
  try {
    const r = await fetch(
      `/api/rule-review/rules?domain=${encodeURIComponent(domain)}&package=${encodeURIComponent(pkg)}`
    );
    if (!r.ok) { document.getElementById('rulesStatus').textContent = 'Error.'; return; }
    const data = await r.json();
    const total = data.total || 0;
    document.getElementById('rulesStatus').textContent =
      `${total} rule(s)` + (total >= 2000 ? ' (capped at 2000)' : '');
    document.getElementById('rulesTbody').innerHTML = (data.rules || []).map(rule => {
      const action = (rule.action || {}).name || '';
      const actionBadge = action.toLowerCase() === 'accept'
        ? `<span class="badge badge-action-accept">${esc(action)}</span>`
        : `<span class="badge badge-action-drop">${esc(action)}</span>`;
      return `<tr>
        <td>${esc(rule['rule-number'])}</td>
        <td>${esc(rule.name)}</td>
        <td class="truncate-cell" title="${nameList(rule.source)}">${nameList(rule.source)}</td>
        <td class="truncate-cell" title="${nameList(rule.destination)}">${nameList(rule.destination)}</td>
        <td class="truncate-cell" title="${nameList(rule.service)}">${nameList(rule.service)}</td>
        <td>${actionBadge}</td>
        <td>${rule.enabled ? 'Yes' : 'No'}</td>
        <td class="truncate-cell" title="${esc(rule.comments)}">${esc(rule.comments)}</td>
      </tr>`;
    }).join('');
    document.getElementById('rulesTableSection').style.display = '';
  } finally {
    document.getElementById('rulesLoadBtn').disabled = false;
  }
});

// ── Section 2: Object Lookup ──────────────────────────────────────────────
populateDomainSelect('objDomainSelect');

document.getElementById('objSearchBtn').addEventListener('click', async () => {
  const domain = document.getElementById('objDomainSelect').value;
  const name = document.getElementById('objNameInput').value.trim();
  if (!domain || !name) {
    document.getElementById('objStatus').textContent = 'Domain and name are required.';
    return;
  }
  document.getElementById('objStatus').textContent = 'Searching…';
  document.getElementById('objTableSection').style.display = 'none';
  const r = await fetch(
    `/api/rule-review/objects?domain=${encodeURIComponent(domain)}&name=${encodeURIComponent(name)}`
  );
  if (!r.ok) { document.getElementById('objStatus').textContent = 'Error.'; return; }
  const data = await r.json();
  document.getElementById('objStatus').textContent = `${(data.objects || []).length} result(s)`;
  document.getElementById('objTbody').innerHTML = (data.objects || []).map(obj => {
    const ip = obj['ipv4-address'] || obj['ipv6-address'] || obj['ip-range'] || '';
    return `<tr>
      <td>${esc(obj.name)}</td>
      <td>${esc(obj.type)}</td>
      <td>${esc(ip)}</td>
      <td class="truncate-cell" title="${esc(obj.comments)}">${esc(obj.comments)}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="4" class="text-muted">No results.</td></tr>';
  document.getElementById('objTableSection').style.display = '';
});

// ── Section 3: Interface Lookup ───────────────────────────────────────────
populateDomainSelect('ifDomainSelect');

document.getElementById('ifSearchBtn').addEventListener('click', async () => {
  const domain = document.getElementById('ifDomainSelect').value;
  const ips = document.getElementById('ifIpsInput').value.trim();
  if (!domain || !ips) {
    document.getElementById('ifStatus').textContent = 'Domain and IPs are required.';
    return;
  }
  document.getElementById('ifStatus').textContent = 'Searching…';
  document.getElementById('ifTableSection').style.display = 'none';
  const r = await fetch(
    `/api/rule-review/interfaces?domain=${encodeURIComponent(domain)}&ips=${encodeURIComponent(ips)}`
  );
  if (!r.ok) { document.getElementById('ifStatus').textContent = 'Error.'; return; }
  const data = await r.json();
  document.getElementById('ifStatus').textContent = `${(data.results || []).length} match(es)`;
  document.getElementById('ifTbody').innerHTML = (data.results || []).map(res => `<tr>
    <td>${esc(res.gateway)}</td>
    <td>${esc(res.interface)}</td>
    <td>${esc(res.ip)}</td>
    <td>${esc(res.subnet)}</td>
    <td>${esc(res.mask)}</td>
  </tr>`).join('') || '<tr><td colspan="5" class="text-muted">No matches.</td></tr>';
  document.getElementById('ifTableSection').style.display = '';
});

// ── Section 4: NAT Lookup ─────────────────────────────────────────────────
populateDomainSelect('natDomainSelect');

document.getElementById('natSearchBtn').addEventListener('click', async () => {
  const domain = document.getElementById('natDomainSelect').value;
  const ip = document.getElementById('natIpInput').value.trim();
  if (!domain || !ip) {
    document.getElementById('natStatus').textContent = 'Domain and IP are required.';
    return;
  }
  document.getElementById('natStatus').textContent = 'Searching…';
  document.getElementById('natTableSection').style.display = 'none';
  const r = await fetch(
    `/api/rule-review/nat?domain=${encodeURIComponent(domain)}&ip=${encodeURIComponent(ip)}`
  );
  if (!r.ok) { document.getElementById('natStatus').textContent = 'Error.'; return; }
  const data = await r.json();
  document.getElementById('natStatus').textContent = `${(data.results || []).length} match(es)`;
  document.getElementById('natTbody').innerHTML = (data.results || []).map(res => {
    const f = field => esc(objName(res[field]));
    return `<tr>
      <td>${esc(res.package)}</td>
      <td>${esc(res['rule-number'])}</td>
      <td>${f('original-source')}</td>
      <td>${f('original-destination')}</td>
      <td>${f('original-service')}</td>
      <td>${f('translated-source')}</td>
      <td>${f('translated-destination')}</td>
      <td>${f('translated-service')}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="8" class="text-muted">No matches.</td></tr>';
  document.getElementById('natTableSection').style.display = '';
});
```

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/templates/rule_review.html app/static/js/rule_review.js
git commit -m "feat: add rule review template and JS (policy rules, object lookup, interface lookup, NAT lookup)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Plan Complete

**What this plan delivers:**
- `CPClient._fetch_all` key parameter — fixes `get_packages` and `get_access_rulebase`; enables `get_nat_rulebase`, `get_objects`, `get_gateway_full`, `get_cluster_full`
- Firewalls tab — domain selector, sortable gateway/cluster table, click-to-detail modal with policy packages + software blades
- `/api/firewalls/domains` — user-scoped domain list
- `/api/firewalls/gateways` — sorted short-form gateway + cluster list per domain
- `/api/firewalls/gateway` — full details for a named gateway or cluster
- Rule Review tab — four independent sections in a single page
- `/api/rule-review/packages` — policy package names for a domain
- `/api/rule-review/rules` — access rules (filtered to `access-rule` type, capped at 2000)
- `/api/rule-review/objects` — object search by name
- `/api/rule-review/interfaces` — interface IP lookup across all gateways and clusters
- `/api/rule-review/nat` — NAT rule search by IP (exact match on source/destination fields)
- All new API routes: `login_required` + `tab_required`, `check_domain_access` on every domain-scoped handler
- All user-supplied data in HTML through `esc()`

**Test count added:** ~24 new tests (8 cp_client + 9 firewall_routes + 11 rule_review_routes), bringing total from 84 to ~108.

**Next plans:** Plan 4 could add export functionality (Excel/CSV) for rules tables, or a Certificates tab for tracking gateway certificate expiry.
