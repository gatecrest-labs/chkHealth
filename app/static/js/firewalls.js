function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let _allRows = [];   // [{name, type, ip, version, sic, comments, _raw}]
let _sortCol = 'name';
let _sortAsc = true;
let _currentDomain = '';

// ── Domain loader ─────────────────────────────────────────────────────────
async function loadDomains(attempt) {
  attempt = attempt || 0;
  const r = await fetch('/api/firewalls/domains');
  if (!r.ok) return;
  const data = await r.json();
  const sel = document.getElementById('domainSelect');
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

function _clusterSic(obj) {
  const members = obj['cluster-members'] || [];
  if (!members.length) return obj['sic-state'] || '';
  const states = members.map(m => (m['sic-state'] || '').toLowerCase());
  const ok = states.filter(s => s === 'communicating').length;
  if (ok === states.length) return 'communicating';
  if (ok > 0) return `${ok}/${states.length} communicating`;
  return states[0] || 'unknown';
}

function _toRow(obj, type) {
  const sic = type === 'Cluster' ? _clusterSic(obj) : (obj['sic-state'] || '');
  return {
    name: obj.name || '',
    type,
    ip: obj['ipv4-address'] || obj['ipv6-address'] || '',
    version: obj['version'] || '',
    sic,
    comments: obj.comments || '',
    _raw: obj,
  };
}

function verBadge(ver) {
  const v = (ver || '').toLowerCase();
  let cls = 'badge-ver-old';
  if (v.startsWith('r82') || v === 'r81.20') cls = 'badge-ver-current';
  else if (v.startsWith('r81')) cls = 'badge-ver-mid';
  return `<span class="badge ${cls}">${esc(ver || '—')}</span>`;
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
    let sicCell;
    if (row.type === 'Cluster') {
      const members = (row._raw['cluster-members'] || [])
        .slice().sort((a, b) => (a.priority || 9) - (b.priority || 9));
      if (members.length) {
        const ok = members.filter(m => (m['sic-state'] || '').toLowerCase() === 'communicating').length;
        const degraded = ok < members.length;
        const dots = members.map(m => {
          const s = (m['sic-state'] || '').toLowerCase();
          const cls = s === 'communicating' ? 'ha-dot-ok' : 'ha-dot-bad';
          return `<span class="ha-dot ${cls}" title="${esc(m.name || '')}: ${esc(m['sic-state'] || 'unknown')}"></span>`;
        }).join('');
        const countCls = degraded ? 'ha-count ha-count-warn' : 'ha-count';
        const countLabel = degraded ? `⚠ ${ok}/${members.length}` : `${ok}/${members.length}`;
        sicCell = `<span class="ha-status">${dots}<span class="${countCls}">${countLabel}</span></span>`;
      } else {
        sicCell = `<span class="badge badge-sic-bad">Unknown</span>`;
      }
    } else {
      const sicOk = row.sic.toLowerCase() === 'communicating';
      sicCell = sicOk
        ? `<span class="badge badge-sic-ok">${esc(row.sic)}</span>`
        : `<span class="badge badge-sic-bad">${esc(row.sic || 'Unknown')}</span>`;
    }
    const typeBadge = `<span class="badge ${row.type === 'Cluster' ? 'badge-type-cluster' : 'badge-type'}">${esc(row.type)}</span>`;
    const clusterDegraded = row.type === 'Cluster' && (() => {
      const m = (row._raw['cluster-members'] || []);
      return m.length > 0 && m.filter(x => (x['sic-state'] || '').toLowerCase() === 'communicating').length < m.length;
    })();
    return `<tr class="fw-row${clusterDegraded ? ' fw-row-degraded' : ''}" data-name="${esc(row.name)}" data-type="${esc(row.type.toLowerCase())}">
      <td>${esc(row.name)}</td>
      <td>${typeBadge}</td>
      <td>${esc(row.ip)}</td>
      <td>${verBadge(row.version)}</td>
      <td>${sicCell}</td>
      <td class="truncate-cell" title="${esc(row.comments)}">${esc(row.comments)}</td>
    </tr>`;
  }).join('');

  document.querySelectorAll('.fw-row').forEach(tr => {
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => {
      const url = '/firewalls/gateway?domain=' + encodeURIComponent(_currentDomain)
        + '&name=' + encodeURIComponent(tr.dataset.name)
        + '&type=' + encodeURIComponent(tr.dataset.type);
      window.location.href = url;
    });
  });
}

// ── Init ──────────────────────────────────────────────────────────────────
loadDomains();
