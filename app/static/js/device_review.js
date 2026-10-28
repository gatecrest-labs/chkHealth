const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let _allDevices = [];
let _filteredDevices = [];
let _sortCol = 'name';
let _sortAsc = true;
let _drPage = 1;
let _selModel = null;

function _drPageSize() {
  return parseInt(document.getElementById('drPageSize').value, 10);
}

// ── Domain loader ─────────────────────────────────────────────────────────
async function loadDomains(attempt) {
  attempt = attempt || 0;
  const r = await fetch('/api/firewalls/domains');
  if (!r.ok) return;
  const data = await r.json();
  const sel = document.getElementById('drDomainSelect');
  if (data.status !== 'ok' && attempt < 8) {
    setTimeout(() => loadDomains(attempt + 1), 5000);
    return;
  }
  (data.domains || []).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    sel.appendChild(opt);
  });
  sel.addEventListener('change', () => {
    document.getElementById('drLoadBtn').disabled = !sel.value;
  });
}

// ── Load devices ──────────────────────────────────────────────────────────
document.getElementById('drLoadBtn').addEventListener('click', async () => {
  const domain = document.getElementById('drDomainSelect').value;
  if (!domain) return;
  const status = document.getElementById('drStatus');
  status.textContent = 'Loading…';
  document.getElementById('drLoadBtn').disabled = true;
  ['drVersionSection', 'drModelSection', 'drBladesSection', 'drTableSection'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });
  _selModel = null;
  try {
    const r = await fetch('/api/device-review/devices?domain=' + encodeURIComponent(domain));
    if (!r.ok) {
      status.textContent = 'Error loading data.';
      return;
    }
    const data = await r.json();
    _allDevices = data.devices || [];
    const nUnits = _allDevices.reduce((n, d) => n + _units(d), 0);
    status.textContent = `${nUnits} device(s) loaded` +
      (nUnits !== _allDevices.length ? ` (${_allDevices.length} objects).` : '.');
    renderVersionBars();
    renderModelBars();
    renderBladesGrid();
    applyFilter();
    ['drVersionSection', 'drModelSection', 'drBladesSection', 'drTableSection'].forEach(id => {
      document.getElementById(id).style.display = '';
    });
  } finally {
    document.getElementById('drLoadBtn').disabled = false;
  }
});

// ── Version bars ──────────────────────────────────────────────────────────
function renderVersionBars() {
  const counts = {};
  _allDevices.forEach(d => {
    const v = d.version || 'Unknown';
    counts[v] = (counts[v] || 0) + 1;
  });
  const total = _allDevices.length;
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = sorted[0]?.[1] || 1;
  document.getElementById('drVersionBars').innerHTML = sorted.map(([ver, cnt]) => {
    const pct = ((cnt / total) * 100).toFixed(1);
    const barW = ((cnt / max) * 100).toFixed(1);
    return `<div class="dr-ver-row">
      <span class="dr-ver-label">${esc(ver)}</span>
      <div class="dr-ver-track">
        <div class="dr-ver-bar" style="width:${barW}%;background:${verBarColor(ver)}"></div>
      </div>
      <span class="dr-ver-count">${cnt} device${cnt !== 1 ? 's' : ''}</span>
      <span class="dr-ver-pct">${pct}%</span>
    </div>`;
  }).join('');
}

// ── Hardware model bars ───────────────────────────────────────────────────
// A cluster counts as one device per member (see device_units in the backend).
function _units(d) {
  return d.units > 0 ? d.units : 1;
}

function modelBucket(d) {
  const h = String(d.hardware ?? '').trim();
  return (!h || h.toLowerCase() === 'n/a') ? 'Unknown' : h;
}

function modelCounts(devices) {
  const counts = {};
  devices.forEach(d => {
    const m = modelBucket(d);
    counts[m] = (counts[m] || 0) + _units(d);
  });
  // Largest first; "Unknown" always last
  return Object.entries(counts).sort((a, b) =>
    (a[0] === 'Unknown') - (b[0] === 'Unknown') || b[1] - a[1] ||
    a[0].localeCompare(b[0], undefined, { numeric: true }));
}

function modelRowHtml(model, cnt, total, max, extraCls, attrs) {
  const pct = total ? ((cnt / total) * 100).toFixed(1) : '0.0';
  // Scale to the largest bucket (min 2%) so small models stay visible
  const barW = Math.max(2, Math.round((cnt / max) * 100));
  return `<div class="dr-ver-row dr-ver-clickable ${extraCls}" ${attrs} style="cursor:pointer" title="${esc(model)}">
      <span class="dr-ver-label dr-model-label">${esc(model)}</span>
      <div class="dr-ver-track"><div class="dr-ver-bar" style="width:${barW}%"></div></div>
      <span class="dr-ver-count">${cnt} device${cnt !== 1 ? 's' : ''}</span>
      <span class="dr-ver-pct">${pct}%</span>
    </div>`;
}

function renderModelBars() {
  const entries = modelCounts(_allDevices);
  const total = entries.reduce((n, e) => n + e[1], 0);
  const max = Math.max(1, ...entries.map(e => e[1]));
  const box = document.getElementById('drModelBars');
  box.innerHTML = entries.map(([model, cnt]) =>
    modelRowHtml(model, cnt, total, max, model === _selModel ? 'dr-row-active' : '',
      `data-model="${esc(model)}"`)).join('');
  box.querySelectorAll('[data-model]').forEach(row => {
    row.addEventListener('click', () => {
      _selModel = _selModel === row.dataset.model ? null : row.dataset.model;
      renderModelBars();
      applyFilter();
    });
  });
}

// ── Blades grid ───────────────────────────────────────────────────────────
function renderBladesGrid() {
  const counts = {};
  _allDevices.forEach(d => {
    (d.blades || []).forEach(b => {
      counts[b] = (counts[b] || 0) + 1;
    });
  });
  const total = _allDevices.length;
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!sorted.length) {
    document.getElementById('drBladesGrid').innerHTML =
      '<p class="text-muted" style="font-size:.82rem">No blade data available.</p>';
    return;
  }
  document.getElementById('drBladesGrid').innerHTML = sorted.map(([blade, cnt]) => {
    const pct = Math.round((cnt / total) * 100);
    return `<div class="dr-blade-item">
      <span class="dr-blade-name">${esc(blade)}</span>
      <div class="dr-blade-track">
        <div class="dr-blade-bar" style="width:${pct}%"></div>
      </div>
      <span class="dr-blade-stat">${cnt}/${total}</span>
    </div>`;
  }).join('');
}

// ── Filter + sort + render ─────────────────────────────────────────────────
document.getElementById('drSearch').addEventListener('input', applyFilter);
document.getElementById('drTypeFilter').addEventListener('change', applyFilter);
document.getElementById('drPageSize').addEventListener('change', () => { _drPage = 1; renderTable(); });

document.querySelectorAll('.dr-sortable').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.col;
    if (_sortCol === col) { _sortAsc = !_sortAsc; }
    else { _sortCol = col; _sortAsc = true; }
    applyFilter();
  });
});

function applyFilter() {
  const q = document.getElementById('drSearch').value.toLowerCase();
  const typeF = document.getElementById('drTypeFilter').value;
  let filtered = _allDevices.filter(d => {
    if (typeF && d.type !== typeF) return false;
    if (_selModel && modelBucket(d) !== _selModel) return false;
    if (!q) return true;
    return (
      d.name.toLowerCase().includes(q) ||
      (d.ip || '').toLowerCase().includes(q) ||
      (d.version || '').toLowerCase().includes(q) ||
      (d.os || '').toLowerCase().includes(q) ||
      (d.hardware || '').toLowerCase().includes(q) ||
      (d.comments || '').toLowerCase().includes(q) ||
      (d.blades || []).some(b => b.toLowerCase().includes(q))
    );
  });
  filtered = filtered.sort((a, b) => {
    const av = (a[_sortCol] || '').toLowerCase();
    const bv = (b[_sortCol] || '').toLowerCase();
    return _sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  _filteredDevices = filtered;
  _drPage = 1;
  const fUnits = filtered.reduce((n, d) => n + _units(d), 0);
  document.getElementById('drCount').textContent =
    `${filtered.length} of ${_allDevices.length}` +
    (fUnits !== filtered.length ? ` (${fUnits} devices)` : '') +
    (_selModel ? ` — model: ${_selModel}` : '');
  renderTable();
}

// ── Blade color map ───────────────────────────────────────────────────────
const _BLADE_COLORS = {
  'Firewall': '#2563eb', 'VPN': '#7c3aed', 'IPS': '#dc2626',
  'App Control': '#d97706', 'URL Filtering': '#059669',
  'Anti-Bot': '#0891b2', 'Anti-Virus': '#16a34a',
  'Threat Emulation': '#9333ea', 'Threat Extraction': '#c026d3',
  'Content Awareness': '#0284c7', 'Identity Awareness': '#ea580c',
  'Mobile Access': '#65a30d', 'DLP': '#e11d48',
  'Anti-Spam': '#0f766e', 'QoS': '#78716c',
  'Monitoring': '#475569', 'Policy Server': '#854d0e',
};

function bladePill(name) {
  const bg = _BLADE_COLORS[name] || '#6b7280';
  return `<span class="dr-blade-pill" style="background:${bg}">${esc(name)}</span>`;
}

function verBarColor(ver) {
  const v = (ver || '').toLowerCase();
  if (v.startsWith('r82') || v === 'r81.20') return '#3b82f6';
  if (v.startsWith('r81')) return '#6366f1';
  if (v.startsWith('r80')) return '#9ca3af';
  return '#d1d5db';
}

function typeBadge(type) {
  const cls = type === 'Cluster' ? 'badge-type-cluster' : 'badge-type';
  return `<span class="badge ${cls}">${esc(type)}</span>`;
}

function renderTable() {
  const ps = _drPageSize();
  const total = _filteredDevices.length;
  const pages = ps > 0 ? Math.ceil(total / ps) : 1;
  if (_drPage > pages) _drPage = pages || 1;

  const slice = ps > 0
    ? _filteredDevices.slice((_drPage - 1) * ps, _drPage * ps)
    : _filteredDevices;

  const pageInfo = document.getElementById('drPageInfo');
  pageInfo.textContent = (ps > 0 && pages > 1)
    ? `${total} device(s) — page ${_drPage} of ${pages}`
    : '';

  document.getElementById('drTbody').innerHTML = slice.map((d, i) => {
    const rowNum = ps > 0 ? ((_drPage - 1) * ps) + i + 1 : i + 1;
    const blades = (d.blades || []).map(bladePill).join('');
    const members = d.type === 'Cluster' && d.member_count
      ? ` <span style="font-size:.75rem;color:var(--text-muted)">(${d.member_count} members)</span>` : '';
    return `<tr>
      <td style="color:var(--text-muted);font-size:.78rem">${rowNum}</td>
      <td><strong>${esc(d.name)}</strong>${members}</td>
      <td style="font-size:.82rem">${esc(d.ip)}</td>
      <td>${typeBadge(d.type)}</td>
      <td><code style="font-size:.82rem">${esc(d.version)}</code></td>
      <td style="font-size:.82rem">${esc(d.os)}</td>
      <td style="font-size:.82rem">${esc(d.hardware)}</td>
      <td class="dr-blades-cell">${blades}</td>
      <td style="font-size:.82rem;word-break:break-word;min-width:160px;max-width:280px">${esc(d.comments)}</td>
    </tr>`;
  }).join('');

  renderPagination('drPagination', total, _drPage, ps, p => { _drPage = p; renderTable(); });
}

function renderPagination(containerId, total, page, pageSize, onPage) {
  const el = document.getElementById(containerId);
  if (pageSize === 0 || total === 0) { el.innerHTML = ''; return; }
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) { el.innerHTML = ''; return; }
  const btn = (label, p, disabled) =>
    `<button class="btn btn-sm btn-secondary rr-pg-btn" data-page="${p}"${disabled ? ' disabled' : ''}>${label}</button>`;
  el.innerHTML =
    btn('«', 1, page <= 1) + btn('‹', page - 1, page <= 1) +
    `<span class="rr-pg-label">${page} / ${pages}</span>` +
    btn('›', page + 1, page >= pages) + btn('»', pages, page >= pages);
  el.querySelectorAll('.rr-pg-btn').forEach(b => {
    b.addEventListener('click', () => onPage(parseInt(b.dataset.page, 10)));
  });
}

// ── Global summary ────────────────────────────────────────────────────────
let _summaryUpdatedAt = null;

async function loadSummary() {
  try {
    const r = await fetch('/api/device-review/summary');
    if (!r.ok) return;
    const d = await r.json();
    renderSummary(d);
    return d.status;
  } catch { /* silently skip if not available */ }
}

function renderSummary(d) {
  _summaryUpdatedAt = d.last_updated ? new Date(d.last_updated) : null;
  updateSummaryAge();

  const total = d.total || 0;
  const dc = d.domains_ok || d.domain_count || 0;
  const status = d.status || 'empty';

  if (status === 'empty') {
    document.getElementById('drSummaryHeadline').textContent =
      'Version summary building… check back shortly.';
    document.getElementById('drSummaryBars').innerHTML = '';
    document.getElementById('drSummaryModelSection').style.display = 'none';
    return;
  }

  const collecting = status === 'collecting';
  document.getElementById('drSummaryHeadline').innerHTML =
    `<strong style="font-size:1.5rem">${total}</strong> `+
    `<span style="font-size:.9rem">devices — All Domains (${dc} domain${dc !== 1 ? 's' : ''})</span>`+
    (collecting ? `<span style="font-size:.78rem;color:var(--text-muted);margin-left:.5rem">collecting…</span>` : '');

  const bars = d.by_version || [];
  const max = bars[0]?.count || 1;
  const container = document.getElementById('drSummaryBars');
  container.innerHTML = bars.map((b, i) => {
    const barW = ((b.count / max) * 100).toFixed(1);
    return `<div class="dr-ver-row dr-ver-clickable" data-idx="${i}" style="cursor:pointer" title="Click to see devices on ${esc(b.version)}">
      <span class="dr-ver-label">${esc(b.version)}</span>
      <div class="dr-ver-track"><div class="dr-ver-bar" style="width:${barW}%;background:${verBarColor(b.version)}"></div></div>
      <span class="dr-ver-count">${b.count} device${b.count !== 1 ? 's' : ''}</span>
      <span class="dr-ver-pct">${b.pct}%</span>
    </div>
    <div class="dr-ver-panel" id="drVerPanel${i}" style="display:none"></div>`;
  }).join('');

  // Store device data for click handlers
  container._versionData = bars;
  renderSummaryModels(bars);

  container.querySelectorAll('.dr-ver-clickable').forEach(row => {
    row.addEventListener('click', () => {
      const idx = parseInt(row.dataset.idx);
      const panel = document.getElementById('drVerPanel' + idx);
      if (panel.style.display !== 'none') {
        panel.style.display = 'none';
        return;
      }
      const devs = (container._versionData[idx]?.devices || []);
      panel.innerHTML = `<table class="data-table dr-ver-device-table">
        <thead><tr><th>#</th><th>Name</th><th>Domain</th><th>Type</th><th>Management IP</th></tr></thead>
        <tbody>${devs.map((d, n) => `<tr>
          <td style="color:var(--text-muted);font-size:.78rem">${n+1}</td>
          <td><strong>${esc(d.name)}</strong></td>
          <td>${esc(d.domain)}</td>
          <td><span class="badge badge-type">${esc(d.type)}</span></td>
          <td style="font-size:.82rem">${esc(d.ip)}</td>
        </tr>`).join('')}</tbody>
      </table>`;
      panel.style.display = '';
      // close other open panels
      container.querySelectorAll('.dr-ver-panel').forEach((p, j) => {
        if (j !== idx) p.style.display = 'none';
      });
    });
  });
}

function renderSummaryModels(bars) {
  const all = bars.flatMap(b => (b.devices || []).map(d => ({ ...d, version: b.version })));
  const section = document.getElementById('drSummaryModelSection');
  const box = document.getElementById('drSummaryModelBars');
  if (!all.length) { section.style.display = 'none'; return; }
  const entries = modelCounts(all);
  const total = entries.reduce((n, e) => n + e[1], 0);
  const max = Math.max(1, ...entries.map(e => e[1]));
  const open = box._open;  // keep the open panel across the auto-refresh polls
  const openModel = open != null ? box._entries?.[open]?.model : null;
  box._entries = entries.map(([model]) => ({
    model,
    devices: all.filter(d => modelBucket(d) === model)
      .sort((a, b) => (a.domain || '').localeCompare(b.domain || '') || a.name.localeCompare(b.name)),
  }));
  box.innerHTML = entries.map(([model, cnt], i) =>
    modelRowHtml(model, cnt, total, max, '', `data-midx="${i}"`) +
    `<div class="dr-ver-panel dr-model-panel" id="drModelPanel${i}" style="display:none"></div>`).join('');
  section.style.display = '';

  const showPanel = idx => {
    box.querySelectorAll('.dr-ver-panel').forEach(p => { p.style.display = 'none'; });
    box.querySelectorAll('.dr-ver-row').forEach(r => r.classList.remove('dr-row-active'));
    box._open = idx;
    if (idx == null) return;
    const entry = box._entries[idx];
    const panel = document.getElementById('drModelPanel' + idx);
    panel.innerHTML = `<table class="data-table dr-ver-device-table">
      <thead><tr><th>#</th><th>Name</th><th>Domain</th><th>Type</th><th>Version</th><th>Devices</th><th>Management IP</th></tr></thead>
      <tbody>${entry.devices.map((d, n) => `<tr>
        <td style="color:var(--text-muted);font-size:.78rem">${n + 1}</td>
        <td><strong>${esc(d.name)}</strong></td>
        <td>${esc(d.domain)}</td>
        <td><span class="badge ${d.type === 'Cluster' ? 'badge-type-cluster' : 'badge-type'}">${esc(d.type)}</span></td>
        <td><code style="font-size:.82rem">${esc(d.version)}</code></td>
        <td>${_units(d)}</td>
        <td style="font-size:.82rem">${esc(d.ip)}</td>
      </tr>`).join('')}</tbody>
    </table>`;
    panel.style.display = '';
    box.querySelector(`[data-midx="${idx}"]`).classList.add('dr-row-active');
  };

  box.querySelectorAll('[data-midx]').forEach(row => {
    row.addEventListener('click', () => {
      const idx = parseInt(row.dataset.midx, 10);
      showPanel(box._open === idx ? null : idx);
    });
  });
  const reopen = openModel == null ? -1 : entries.findIndex(e => e[0] === openModel);
  if (reopen >= 0) showPanel(reopen); else box._open = null;
}

function updateSummaryAge() {
  const el = document.getElementById('drSummaryUpdated');
  if (!_summaryUpdatedAt) { el.textContent = ''; return; }
  const secs = Math.round((Date.now() - _summaryUpdatedAt.getTime()) / 1000);
  if (secs < 60) el.textContent = `Last updated: ${secs}s ago`;
  else if (secs < 3600) el.textContent = `Last updated: ${Math.round(secs/60)}m ago`;
  else el.textContent = `Last updated: ${Math.round(secs/3600)}h ago`;
}
setInterval(updateSummaryAge, 10000);

let _refreshPolling = null;

document.getElementById('drSummaryRefreshBtn').addEventListener('click', async () => {
  const btn = document.getElementById('drSummaryRefreshBtn');
  btn.disabled = true;
  btn.textContent = '↺ Refreshing…';
  document.getElementById('drSummaryUpdated').textContent = 'Collecting from all domains…';
  await fetch('/api/device-review/refresh', { method: 'POST',
    headers: {'X-CSRF-Token': CSRF} });
  // Poll for updated data every 5s for up to 3 minutes
  let polls = 0;
  _refreshPolling = setInterval(async () => {
    polls++;
    await loadSummary();
    if (polls >= 36 || (_summaryUpdatedAt && Date.now() - _summaryUpdatedAt.getTime() < 10000)) {
      clearInterval(_refreshPolling);
      _refreshPolling = null;
      btn.disabled = false;
      btn.textContent = '↺ Refresh';
    }
  }, 5000);
});

// ── Auto-poll while collecting ────────────────────────────────────────────
let _autoSummaryPoll = null;

function _startSummaryPoll() {
  if (_autoSummaryPoll) return;
  let polls = 0;
  _autoSummaryPoll = setInterval(async () => {
    polls++;
    try {
      const r = await fetch('/api/device-review/summary');
      if (!r.ok) return;
      const d = await r.json();
      renderSummary(d);
      if (d.status === 'ok' || d.status === 'error' || polls >= 72) {
        clearInterval(_autoSummaryPoll);
        _autoSummaryPoll = null;
      }
    } catch { /* network hiccup — keep polling */ }
  }, 5000);
}

// ── Init ──────────────────────────────────────────────────────────────────
loadDomains();
loadSummary().then(status => {
  if (status === 'collecting' || status === 'empty') _startSummaryPoll();
});
