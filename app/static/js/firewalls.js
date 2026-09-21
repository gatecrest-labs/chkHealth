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
    const typeBadge = `<span class="badge badge-type">${esc(row.type)}</span>`;
    const clusterDegraded = row.type === 'Cluster' && (() => {
      const m = (row._raw['cluster-members'] || []);
      return m.length > 0 && m.filter(x => (x['sic-state'] || '').toLowerCase() === 'communicating').length < m.length;
    })();
    return `<tr class="fw-row${clusterDegraded ? ' fw-row-degraded' : ''}" data-name="${esc(row.name)}" data-type="${esc(row.type.toLowerCase())}">
      <td>${esc(row.name)}</td>
      <td>${typeBadge}</td>
      <td>${esc(row.ip)}</td>
      <td>${esc(row.version)}</td>
      <td>${sicCell}</td>
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

function _sicBadge(state) {
  const s = (state || '').toLowerCase();
  const ok = s === 'communicating';
  const partial = s.includes('/') && s.includes('communicating');
  const cls = ok || partial ? 'badge-sic-ok' : 'badge-sic-bad';
  return `<span class="badge ${cls}">${esc(state || 'Unknown')}</span>`;
}

function renderDetails(d) {
  const row = (label, val) =>
    `<tr><td style="color:var(--text-muted);width:40%;font-size:.82rem">${esc(label)}</td><td>${esc(val ?? '')}</td></tr>`;
  const members = d['cluster-members'] || [];
  const isCluster = members.length > 0;
  const sic = isCluster ? _clusterSic(d) : (d['sic-state'] || '');
  const ver = d['version'] || '';
  let html = `<table class="data-table" style="margin-bottom:1rem">
    <tbody>
      ${row('Name', d.name)}
      ${row('IPv4 Address (VIP)', d['ipv4-address'])}
      ${row('Version', ver)}
      ${row('OS', d['os-name'])}
      ${row('Hardware', d['hardware'])}
      ${row('Platform', d['platform'])}
      ${isCluster ? '' : row('SIC State', sic)}
      ${isCluster ? '' : row('SIC Name', d['sic-name'] || '')}
      ${row('Cluster Mode', d['cluster-mode'])}
      ${row('Comments', d.comments)}
    </tbody>
  </table>`;

  if (isCluster) {
    const membersSorted = members.sort((a,b) => (a.priority||9) - (b.priority||9));
    const anyDown = membersSorted.some(m => (m['sic-state'] || '').toLowerCase() !== 'communicating');
    html += `${anyDown ? '<div class="cluster-warn-banner">⚠ One or more cluster members are not communicating — cluster may be degraded</div>' : ''}
      <strong style="font-size:.85rem;display:block;margin-bottom:.4rem">HA Cluster Members</strong>
      <p style="font-size:.75rem;color:var(--text-muted);margin:.1rem 0 .6rem">Health shows SIC connectivity to the management server — the best indicator available via the API. For live HA state run <code>cphaprob stat</code> on the gateway.</p>
      <table class="data-table" style="margin-bottom:1rem;font-size:.82rem">
        <thead><tr><th>Priority</th><th>Name</th><th>Management IP</th><th>Member Health (SIC)</th></tr></thead>
        <tbody>${membersSorted.map(m => {
          const mSic = m['sic-state'] || 'unknown';
          const down = mSic.toLowerCase() !== 'communicating';
          return `<tr${down ? ' class="member-down"' : ''}>
            <td style="text-align:center">${esc(String(m.priority || ''))}</td>
            <td>${down ? '⚠ ' : ''}${esc(m.name || '')}</td>
            <td>${esc(m['ip-address'] || m['ipv4-address'] || '')}</td>
            <td>${_sicBadge(mSic)}</td>
          </tr>`;
        }).join('')}
        </tbody>
      </table>`;
  }

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
