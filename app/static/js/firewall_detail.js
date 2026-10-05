// ── Helpers ──────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function errBanner(msg) {
  return `<div class="gaia-error-banner">&#9888; ${esc(msg)} <button class="btn btn-sm btn-secondary retry-btn" style="margin-left:.5rem">Retry</button></div>`;
}

// ── Tab switching ─────────────────────────────────────────────────────────────
const _loaded = {};

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
  document.querySelectorAll('.tab-pane').forEach(p => { p.style.display = p.id === 'tab-' + tabId ? '' : 'none'; });
  if (!_loaded[tabId]) {
    _loaded[tabId] = true;
    if (tabId === 'interfaces') loadInterfaces();
    if (tabId === 'routing') loadRouting();
    if (tabId === 'protocols') loadProtocols();
  }
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ── Base URL params ──────────────────────────────────────────────────────────
const _params = `domain=${encodeURIComponent(window._GW_DOMAIN)}&name=${encodeURIComponent(window._GW_NAME)}&type=${encodeURIComponent(window._GW_TYPE)}`;

// ── Interfaces ───────────────────────────────────────────────────────────────
async function loadInterfaces() {
  const el = document.getElementById('interfaces-content');
  try {
    const r = await fetch('/api/firewalls/gateway/interfaces?' + _params);
    if (!r.ok) { el.innerHTML = errBanner('Error loading interface data (' + r.status + ')'); return; }
    const d = await r.json();
    if (!d.available) {
      el.innerHTML = `<p class="text-muted">Interface data unavailable: ${esc(d.reason || 'unknown')}</p>`;
      return;
    }
    el.innerHTML = renderInterfaces(d);
    el.querySelectorAll('.retry-btn').forEach(b => b.addEventListener('click', () => { _loaded['interfaces'] = false; el.innerHTML = '<p class="text-muted">Loading…</p>'; loadInterfaces(); _loaded['interfaces'] = true; }));
  } catch (e) {
    el.innerHTML = errBanner('Failed to load interface data: ' + e.message);
  }
}

function renderInterfaces(d) {
  const member = d.target_member ? `<p class="text-muted" style="font-size:.8rem">Showing active member: <strong>${esc(d.target_member)}</strong></p>` : '';
  const groups = [
    ['Physical', d.physical || []],
    ['VLAN', d.vlan || []],
    ['Bond / LACP', d.bond || []],
    ['Loopback', d.loopback || []],
  ];
  let html = member;
  for (const [label, ifaces] of groups) {
    if (!ifaces.length) continue;
    html += `<h4 style="font-size:.85rem;margin:1rem 0 .4rem">${esc(label)} Interfaces</h4>`;
    html += `<table class="data-table" style="font-size:.82rem;margin-bottom:.5rem">
      <thead><tr><th>Name</th><th>IP / Prefix</th><th>MAC</th><th>Link</th><th>Speed</th><th>Enabled</th></tr></thead>
      <tbody>`;
    for (const i of ifaces) {
      const ip = i['ipv4-address'] || i['ipv4_address'] || '';
      const mask = i['ipv4-mask-length'] || i['ipv4_mask_length'] || '';
      const ipStr = ip ? `${ip}/${mask}` : '—';
      const status = i.status || {};
      const link = status['link-state'] ?? status.link_state;
      const linkBadge = link === true ? '<span class="badge badge-sic-ok">Up</span>' : link === false ? '<span class="badge badge-sic-bad">Down</span>' : '—';
      const speed = status.speed || '—';
      const mac = i['mac-addr'] || i.mac_addr || '—';
      const enabled = i.enabled !== false ? '✓' : '✗';
      html += `<tr><td>${esc(i.name)}</td><td>${esc(ipStr)}</td><td style="font-family:monospace;font-size:.78rem">${esc(mac)}</td><td>${linkBadge}</td><td>${esc(speed)}</td><td style="text-align:center">${enabled}</td></tr>`;
    }
    html += '</tbody></table>';
  }
  if (!html.replace(member, '').trim()) html += '<p class="text-muted">No interface data returned.</p>';
  return html;
}

// ── Routing Table ─────────────────────────────────────────────────────────────
let _routes = [];
let _routeFilter = '';
let _protoFilter = 'all';
let _routePage = 0;
const _routePageSize = 100;

async function loadRouting() {
  const el = document.getElementById('routing-content');
  try {
    const r = await fetch('/api/firewalls/gateway/routing?' + _params);
    if (!r.ok) { el.innerHTML = errBanner('Error loading routing table (' + r.status + ')'); return; }
    const d = await r.json();
    if (!d.available) {
      const reason = d.reason === 'requires_r81_20'
        ? `Routing table requires R81.20 or later. This gateway is running <strong>${esc(d.current_version || 'unknown')}</strong>.`
        : `Routing table unavailable: ${esc(d.reason || 'unknown')}`;
      el.innerHTML = `<p class="text-muted">${reason}</p>`;
      return;
    }
    _routes = d.routes || [];
    _routePage = 0;
    el.innerHTML = buildRoutingUI(d);
    document.getElementById('routeFilter').addEventListener('input', e => { _routeFilter = e.target.value.toLowerCase(); _routePage = 0; renderRouteTable(); });
    document.getElementById('protoFilter').addEventListener('change', e => { _protoFilter = e.target.value; _routePage = 0; renderRouteTable(); });
    document.getElementById('routePrev').addEventListener('click', () => { if (_routePage > 0) { _routePage--; renderRouteTable(); } });
    document.getElementById('routeNext').addEventListener('click', () => { if ((_routePage + 1) * _routePageSize < filteredRoutes().length) { _routePage++; renderRouteTable(); } });
    renderRouteTable();
  } catch (e) {
    el.innerHTML = errBanner('Failed to load routing table: ' + e.message);
  }
}

function buildRoutingUI(d) {
  const protocols = ['all', ...Object.keys(d.protocol_counts || {}).sort()];
  const protoOpts = protocols.map(p => `<option value="${esc(p)}">${p === 'all' ? 'All Protocols' : esc(p.charAt(0).toUpperCase() + p.slice(1))}</option>`).join('');
  const member = d.target_member ? `<p class="text-muted" style="font-size:.8rem">Showing active member: <strong>${esc(d.target_member)}</strong></p>` : '';
  return `${member}
    <div class="d-flex gap-2" style="margin-bottom:.75rem;flex-wrap:wrap;align-items:flex-end">
      <div class="form-group" style="margin-bottom:0;min-width:240px">
        <label class="form-label" for="routeFilter">Filter</label>
        <input id="routeFilter" class="form-control" placeholder="prefix, next-hop, or interface…">
      </div>
      <div class="form-group" style="margin-bottom:0">
        <label class="form-label" for="protoFilter">Protocol</label>
        <select id="protoFilter" class="form-select">${protoOpts}</select>
      </div>
      <span id="routeCount" class="text-muted" style="font-size:.82rem;align-self:center"></span>
    </div>
    <div class="table-wrapper">
      <table class="data-table" style="font-size:.82rem" id="routeTable">
        <thead><tr>
          <th>Destination</th><th>Len</th><th>Next Hop</th><th>Interface</th><th>Protocol</th><th>Metric</th>
        </tr></thead>
        <tbody id="routeTbody"></tbody>
      </table>
    </div>
    <div style="display:flex;justify-content:flex-end;align-items:center;gap:.5rem;margin-top:.5rem">
      <button id="routePrev" class="btn btn-sm btn-secondary">&#8592; Prev</button>
      <span id="routePageLabel" class="text-muted" style="font-size:.82rem"></span>
      <button id="routeNext" class="btn btn-sm btn-secondary">Next &#8594;</button>
    </div>`;
}

const _PROTO_BADGE = {
  static: 'badge-type', ospf: 'badge-ver-mid', bgp: 'badge-ver-current',
  connected: 'badge-sic-ok', kernel: 'badge-ver-old', aggregate: '',
};

function filteredRoutes() {
  return _routes.filter(r => {
    if (_protoFilter !== 'all' && r.protocol !== _protoFilter) return false;
    if (_routeFilter) {
      const hay = `${r.destination}/${r.mask_length} ${r.nexthop} ${r.interface}`.toLowerCase();
      if (!hay.includes(_routeFilter)) return false;
    }
    return true;
  });
}

function renderRouteTable() {
  const rows = filteredRoutes();
  const start = _routePage * _routePageSize;
  const page = rows.slice(start, start + _routePageSize);
  const totalPages = Math.max(1, Math.ceil(rows.length / _routePageSize));
  document.getElementById('routeCount').textContent = `${rows.length.toLocaleString()} route${rows.length !== 1 ? 's' : ''}`;
  document.getElementById('routePageLabel').textContent = `Page ${_routePage + 1} of ${totalPages}`;
  document.getElementById('routePrev').disabled = _routePage === 0;
  document.getElementById('routeNext').disabled = _routePage >= totalPages - 1;
  document.getElementById('routeTbody').innerHTML = page.map(r => {
    const bc = _PROTO_BADGE[r.protocol] || '';
    const proto = `<span class="badge ${bc}" style="font-size:.75rem">${esc(r.protocol)}</span>`;
    return `<tr>
      <td style="font-family:monospace">${esc(r.destination)}</td>
      <td style="text-align:center">/${r.mask_length}</td>
      <td style="font-family:monospace">${esc(r.nexthop || '—')}</td>
      <td>${esc(r.interface || '—')}</td>
      <td>${proto}</td>
      <td style="text-align:right">${r.metric}</td>
    </tr>`;
  }).join('');
}

// ── Routing Protocols ─────────────────────────────────────────────────────────
async function loadProtocols() {
  const el = document.getElementById('protocols-content');
  try {
    const r = await fetch('/api/firewalls/gateway/protocols?' + _params);
    if (!r.ok) { el.innerHTML = errBanner('Error loading protocol data (' + r.status + ')'); return; }
    const d = await r.json();
    el.innerHTML = renderProtocols(d);
  } catch (e) {
    el.innerHTML = errBanner('Failed to load protocol data: ' + e.message);
  }
}

function renderProtocols(d) {
  const member = d.target_member ? `<p class="text-muted" style="font-size:.8rem">Showing active member: <strong>${esc(d.target_member)}</strong></p>` : '';
  let html = member;

  // BGP
  html += '<h3 style="font-size:.9rem;margin-bottom:.5rem">BGP</h3>';
  const bgp = d.bgp || {};
  if (!bgp.available) {
    const msg = bgp.reason === 'requires_r82'
      ? `BGP peer details require R82 or later. This gateway is running <strong>${esc(window._GW_VERSION || 'unknown')}</strong>.`
      : `BGP unavailable: ${esc(bgp.reason || 'unknown')}`;
    html += `<p class="text-muted">${msg}</p>`;
  } else {
    const peers = bgp.peers || [];
    if (!peers.length) {
      html += '<p class="text-muted">No BGP peers configured.</p>';
    } else {
      html += `<table class="data-table" style="font-size:.82rem;margin-bottom:1rem">
        <thead><tr><th>Peer IP</th><th>Remote AS</th><th>State</th><th>Uptime</th><th>Routes Rcvd</th><th>Routes Active</th></tr></thead>
        <tbody>`;
      for (const p of peers) {
        const state = (p.state || '').toLowerCase();
        const cls = state === 'established' ? 'badge-sic-ok' : 'badge-sic-bad';
        const rcvd = p.received || {};
        html += `<tr>
          <td style="font-family:monospace">${esc(p.peer || '')}</td>
          <td>${esc(String(p['remote-as'] || ''))}</td>
          <td><span class="badge ${cls}">${esc(p.state || '—')}</span></td>
          <td>${esc(p.uptime || '—')}</td>
          <td style="text-align:right">${esc(String(rcvd['routes-received'] ?? '—'))}</td>
          <td style="text-align:right">${esc(String(rcvd['routes-received-active'] ?? '—'))}</td>
        </tr>`;
      }
      html += '</tbody></table>';
    }
  }

  // OSPF
  html += '<h3 style="font-size:.9rem;margin-bottom:.5rem;margin-top:1rem">OSPF</h3>';
  const ospf = d.ospf || {};
  if (ospf.note) {
    html += `<p class="text-muted" style="font-size:.82rem">${esc(ospf.note)}</p>`;
  } else {
    html += '<p class="text-muted">OSPF data unavailable.</p>';
  }

  return html;
}
