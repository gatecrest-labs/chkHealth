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
    version: obj['version'] || '',
    sic: obj['sic-state'] || '',
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

const _BLADE_LABELS = {
  'firewall': 'Firewall', 'vpn': 'VPN', 'ips': 'IPS',
  'application-control': 'Application Control', 'url-filtering': 'URL Filtering',
  'anti-bot': 'Anti-Bot', 'anti-virus': 'Anti-Virus',
  'threat-emulation': 'Threat Emulation', 'threat-extraction': 'Threat Extraction',
  'content-awareness': 'Content Awareness', 'identity-awareness': 'Identity Awareness',
  'mobile-access': 'Mobile Access', 'data-loss-prevention': 'DLP',
  'anti-spam-and-email-security': 'Anti-Spam & Email', 'qos': 'QoS',
  'monitoring': 'Monitoring', 'policy-server': 'Policy Server', 'log-server': 'Log Server',
};

function renderDetails(d) {
  const row = (label, val) =>
    `<tr><td style="color:var(--text-muted);width:40%;font-size:.82rem">${esc(label)}</td><td>${esc(val ?? '')}</td></tr>`;
  const sic = d['sic-state'] || '';
  const ver = d['version'] || '';
  let html = `<table class="data-table" style="margin-bottom:1rem">
    <tbody>
      ${row('Name', d.name)}
      ${row('IPv4 Address', d['ipv4-address'])}
      ${row('Version', ver)}
      ${row('OS', d['os-name'])}
      ${row('Hardware', d['hardware'])}
      ${row('Platform', d['platform'])}
      ${row('SIC State', sic)}
      ${row('SIC Name', d['sic-name'])}
      ${row('Comments', d.comments)}
    </tbody>
  </table>`;

  const pkgs = d['fetch-policy'] || [];
  if (pkgs.length) {
    html += `<strong style="font-size:.85rem">Installed Policy</strong>
      <ul style="margin:.4rem 0 1rem;padding-left:1.2rem;font-size:.875rem">
        ${pkgs.map(p => `<li>${esc(p)}</li>`).join('')}
      </ul>`;
  }

  const activeBlades = Object.keys(_BLADE_LABELS).filter(k => d[k] === true);
  if (activeBlades.length) {
    html += `<strong style="font-size:.85rem">Active Software Blades</strong>
      <ul style="margin:.4rem 0 0;padding-left:1.2rem;font-size:.875rem;columns:2">
        ${activeBlades.map(b => `<li>${esc(_BLADE_LABELS[b])}</li>`).join('')}
      </ul>`;
  }

  const ifaces = d['interfaces'] || [];
  if (ifaces.length) {
    html += `<strong style="font-size:.85rem;display:block;margin-top:1rem">Interfaces</strong>
      <table class="data-table" style="margin:.4rem 0 0;font-size:.82rem">
        <thead><tr><th>Name</th><th>IPv4</th><th>Mask</th><th>Topology</th></tr></thead>
        <tbody>${ifaces.filter(i => i['ipv4-address']).map(i => `
          <tr>
            <td>${esc(i.name)}</td>
            <td>${esc(i['ipv4-address'])}</td>
            <td>${esc(i['ipv4-network-mask'] || '/' + i['ipv4-mask-length'] || '')}</td>
            <td>${esc((i['topology-automatic-calculation'] || i['topology'] || ''))}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
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
