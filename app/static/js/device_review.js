const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let _allDevices = [];
let _sortCol = 'name';
let _sortAsc = true;

// ── Domain loader ─────────────────────────────────────────────────────────
async function loadDomains() {
  const r = await fetch('/api/firewalls/domains');
  if (!r.ok) return;
  const data = await r.json();
  const sel = document.getElementById('drDomainSelect');
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
  ['drVersionSection', 'drBladesSection', 'drTableSection'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });
  try {
    const r = await fetch('/api/device-review/devices?domain=' + encodeURIComponent(domain));
    if (!r.ok) {
      status.textContent = 'Error loading data.';
      return;
    }
    const data = await r.json();
    _allDevices = data.devices || [];
    status.textContent = `${_allDevices.length} device(s) loaded.`;
    renderVersionBars();
    renderBladesGrid();
    applyFilter();
    ['drVersionSection', 'drBladesSection', 'drTableSection'].forEach(id => {
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
        <div class="dr-ver-bar" style="width:${barW}%"></div>
      </div>
      <span class="dr-ver-count">${cnt} device${cnt !== 1 ? 's' : ''}</span>
      <span class="dr-ver-pct">${pct}%</span>
    </div>`;
  }).join('');
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
    if (!q) return true;
    return (
      d.name.toLowerCase().includes(q) ||
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
  document.getElementById('drCount').textContent =
    `${filtered.length} of ${_allDevices.length}`;
  renderTable(filtered);
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

function typeBadge(type) {
  return `<span class="badge badge-type">${esc(type)}</span>`;
}

function renderTable(rows) {
  document.getElementById('drTbody').innerHTML = rows.map((d, i) => {
    const blades = (d.blades || []).map(bladePill).join('');
    const members = d.type === 'Cluster' && d.member_count
      ? ` <span style="font-size:.75rem;color:var(--text-muted)">(${d.member_count} members)</span>` : '';
    return `<tr>
      <td style="color:var(--text-muted);font-size:.78rem">${i + 1}</td>
      <td><strong>${esc(d.name)}</strong>${members}</td>
      <td>${typeBadge(d.type)}</td>
      <td><code style="font-size:.82rem">${esc(d.version)}</code></td>
      <td style="font-size:.82rem">${esc(d.os)}</td>
      <td style="font-size:.82rem">${esc(d.hardware)}</td>
      <td class="dr-blades-cell">${blades}</td>
      <td style="font-size:.82rem;word-break:break-word;min-width:160px;max-width:280px">${esc(d.comments)}</td>
    </tr>`;
  }).join('');
}

// ── Global summary ────────────────────────────────────────────────────────
let _summaryUpdatedAt = null;

async function loadSummary() {
  try {
    const r = await fetch('/api/device-review/summary');
    if (!r.ok) return;
    const d = await r.json();
    renderSummary(d);
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
      <div class="dr-ver-track"><div class="dr-ver-bar" style="width:${barW}%"></div></div>
      <span class="dr-ver-count">${b.count} device${b.count !== 1 ? 's' : ''}</span>
      <span class="dr-ver-pct">${b.pct}%</span>
    </div>
    <div class="dr-ver-panel" id="drVerPanel${i}" style="display:none"></div>`;
  }).join('');

  // Store device data for click handlers
  container._versionData = bars;

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

// ── Init ──────────────────────────────────────────────────────────────────
loadDomains();
loadSummary();
