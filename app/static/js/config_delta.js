'use strict';
// ── State ──────────────────────────────────────────────────────────────────
let allGateways = [];
let filteredGateways = [];
let currentPage = 1;
let pageSize = 25;
let filterText = '';
let pendingOnly = false;
let currentDomain = '';
let currentGateway = null;
let currentChanges = null;
const loadedChanges = new Map();
const exportQueue = [];

const CSRF = document.querySelector('meta[name="csrf-token"]').content;

// ── Bootstrap ─────────────────────────────────────────────────────────────
(async function init() {
  await loadDomains();
  document.getElementById('cdDomain').addEventListener('change', e => {
    currentDomain = e.target.value;
    if (currentDomain) loadGateways(currentDomain);
  });
  document.getElementById('cdSearch').addEventListener('input', e => {
    filterText = e.target.value.toLowerCase();
    currentPage = 1;
    applyFilters();
  });
  document.getElementById('cdPendingOnly').addEventListener('change', e => {
    pendingOnly = e.target.checked;
    currentPage = 1;
    applyFilters();
  });
  document.getElementById('cdPageSize').addEventListener('change', e => {
    pageSize = parseInt(e.target.value, 10);
    currentPage = 1;
    renderGatewayTable();
  });
  document.getElementById('cdExportCSV').addEventListener('click', () => downloadExport('csv'));
  document.getElementById('cdExportJSON').addEventListener('click', () => downloadExport('json'));
  document.getElementById('cdExportHTML').addEventListener('click', () => downloadExport('html'));
  document.getElementById('cdClearQueue').addEventListener('click', clearExportQueue);
}());

// ── Domains ───────────────────────────────────────────────────────────────
async function loadDomains() {
  const resp = await fetch('/api/config-delta/domains');
  if (!resp.ok) return;
  const data = await resp.json();
  const sel = document.getElementById('cdDomain');
  sel.innerHTML = '<option value="">— select domain —</option>' +
    (data.domains || []).map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
}

// ── Gateways ──────────────────────────────────────────────────────────────
async function loadGateways(domain) {
  document.getElementById('cdGwTbody').innerHTML =
    '<tr><td colspan="4" class="text-muted">Loading…</td></tr>';
  const resp = await fetch(`/api/config-delta/domains/${encodeURIComponent(domain)}/gateways`);
  if (!resp.ok) {
    document.getElementById('cdGwTbody').innerHTML =
      '<tr><td colspan="4" class="text-danger">Failed to load gateways.</td></tr>';
    return;
  }
  const data = await resp.json();
  allGateways = data.gateways || [];
  currentPage = 1;
  applyFilters();
}

function applyFilters() {
  filteredGateways = allGateways.filter(gw => {
    if (pendingOnly && gw.install_status !== 'pending') return false;
    if (filterText) {
      const name = (gw.name || '').toLowerCase();
      const ip = (gw.ip || '').toLowerCase();
      if (!name.includes(filterText) && !ip.includes(filterText)) return false;
    }
    return true;
  });
  renderGatewayTable();
}

function renderGatewayTable() {
  const total = filteredGateways.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (currentPage > pages) currentPage = pages;
  const start = (currentPage - 1) * pageSize;
  const slice = filteredGateways.slice(start, start + pageSize);

  document.getElementById('cdGwStatus').textContent = `${total} gateway(s)`;
  document.getElementById('cdGwTbody').innerHTML = slice.length
    ? slice.map(gw => `
      <tr class="cd-gw-row ${currentGateway && currentGateway.name === gw.name ? 'cd-row-selected' : ''}"
          data-name="${esc(gw.name)}">
        <td><strong>${esc(gw.name)}</strong></td>
        <td><code>${esc(gw.ip)}</code></td>
        <td>${esc(gw.policy_package)}</td>
        <td>${statusBadge(gw.install_status)}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" class="text-muted">No gateways match the current filter.</td></tr>';

  document.querySelectorAll('.cd-gw-row').forEach(row => {
    row.addEventListener('click', () => {
      const name = row.dataset.name;
      const gw = filteredGateways.find(g => g.name === name);
      if (gw) selectGateway(gw);
    });
  });

  const pager = document.getElementById('cdPager');
  pager.innerHTML = buildPager(currentPage, pages);
  pager.querySelectorAll('.cd-pg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      currentPage = parseInt(btn.dataset.page, 10);
      renderGatewayTable();
    });
  });
}

function statusBadge(status) {
  if (status === 'pending') return '<span class="badge badge-amber">Pending Install</span>';
  if (status === 'insync')  return '<span class="badge badge-green">In Sync</span>';
  return '<span class="badge badge-gray">Unknown</span>';
}

// ── Detail panel ──────────────────────────────────────────────────────────
async function selectGateway(gw) {
  currentGateway = gw;
  renderGatewayTable(); // re-render to update selected row highlight

  if (loadedChanges.has(gw.name)) {
    renderDetailPanel(loadedChanges.get(gw.name));
    return;
  }

  renderDetailLoading('Fetching gateway info…');
  const startResp = await fetch(
    `/api/config-delta/domains/${encodeURIComponent(currentDomain)}/gateway/${encodeURIComponent(gw.name)}/changes`,
    { method: 'POST', headers: { 'X-CSRF-Token': CSRF } }
  );
  if (!startResp.ok) {
    renderDetailError('Failed to start change fetch.');
    return;
  }
  const { task_id } = await startResp.json();
  pollTask(task_id, gw.name);
}

function pollTask(taskId, gwName) {
  const interval = setInterval(async () => {
    const resp = await fetch(`/api/config-delta/task/${taskId}`);
    if (!resp.ok) {
      clearInterval(interval);
      renderDetailError('Task not found. Please try again.');
      return;
    }
    const data = await resp.json();
    if (data.status === 'running') {
      renderDetailLoading(data.step || 'Loading…');
      return;
    }
    clearInterval(interval);
    if (data.status === 'done') {
      loadedChanges.set(gwName, data.result);
      if (currentGateway && currentGateway.name === gwName) {
        renderDetailPanel(data.result);
      }
    } else {
      renderDetailError(data.error || 'Unknown error.');
    }
  }, 500);
}

function renderDetailLoading(step) {
  document.getElementById('cdDetailPanel').innerHTML = `
    <div class="cd-detail-loading">
      <div class="spinner"></div>
      <span>${esc(step)}</span>
    </div>`;
}

function renderDetailError(message) {
  document.getElementById('cdDetailPanel').innerHTML = `
    <div class="cd-detail-error">
      <p class="text-danger">${esc(message)}</p>
      <button class="btn btn-sm btn-secondary" id="cdDetailRetry">Retry</button>
    </div>`;
  const retryBtn = document.getElementById('cdDetailRetry');
  if (retryBtn && currentGateway) {
    retryBtn.addEventListener('click', () => selectGateway(currentGateway));
  }
}

function renderDetailPanel(result) {
  if (!result) { renderDetailError('No result data.'); return; }
  const inQueue = exportQueue.includes(result.gateway);
  const addBtn = !inQueue
    ? `<button class="btn btn-sm btn-secondary" id="cdAddToQueue">Add to Export Queue</button>`
    : `<span class="text-muted small">In export queue</span>`;

  const tiles = Object.entries(result.summary || {})
    .filter(([, count]) => count > 0)
    .map(([key, count]) =>
      `<span class="cd-summary-tile">${count} ${categoryLabel(key)}</span>`
    ).join('');

  const CATEGORIES = ['access_rules','address_objects','nat_rules','services','system','other'];
  const sections = CATEGORIES.map(cat => {
    const items = (result.changes || []).filter(c => c.category === cat);
    const open = items.length > 0 ? 'open' : '';
    const rows = items.length
      ? items.map(c => `<tr>
          <td>${changeTypeBadge(c.change_type)}</td>
          <td>${esc(c.name)}</td>
          <td class="text-muted small">${formatProps(c.properties)}</td>
        </tr>`).join('')
      : '<tr><td colspan="3" class="text-muted">No changes.</td></tr>';
    return `
      <details ${open} class="cd-section">
        <summary class="cd-section-summary">${categoryLabel(cat)}
          ${items.length > 0 ? `<span class="badge badge-gray">${items.length}</span>` : ''}
        </summary>
        <table class="table table-sm">
          <thead><tr><th>Type</th><th>Name</th><th>Properties</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </details>`;
  }).join('');

  document.getElementById('cdDetailPanel').innerHTML = `
    <div class="cd-detail-header">
      <h4>${esc(result.gateway)}</h4>
      <code>${esc(result.ip)}</code>
      <div class="cd-detail-badges">
        ${statusBadge(result.install_status)}
      </div>
      ${addBtn}
    </div>
    <div class="cd-summary-tiles">${tiles || '<span class="text-muted">No pending changes.</span>'}</div>
    ${sections}`;

  const addBtnEl = document.getElementById('cdAddToQueue');
  if (addBtnEl) {
    addBtnEl.addEventListener('click', () => {
      addToExportQueue(result.gateway);
      renderDetailPanel(result);
    });
  }
}

function changeTypeBadge(type) {
  if (type === 'added')    return '<span class="badge badge-green">add</span>';
  if (type === 'deleted')  return '<span class="badge badge-red">delete</span>';
  return '<span class="badge badge-amber">modify</span>';
}

function categoryLabel(key) {
  return {
    access_rules: 'Access Rules', address_objects: 'Address Objects',
    nat_rules: 'NAT Rules', services: 'Services', system: 'System', other: 'Other'
  }[key] || key;
}

function formatProps(props) {
  if (!props || Object.keys(props).length === 0) return '—';
  return Object.entries(props).map(([k, v]) => `${esc(k)}: ${esc(String(v))}`).join(', ');
}

// ── Export queue ──────────────────────────────────────────────────────────
function addToExportQueue(gwName) {
  if (!exportQueue.includes(gwName)) {
    exportQueue.push(gwName);
    renderExportQueue();
  }
}

function clearExportQueue() {
  exportQueue.length = 0;
  renderExportQueue();
}

function renderExportQueue() {
  const bar = document.getElementById('cdExportQueue');
  const chips = document.getElementById('cdQueueChips');
  if (exportQueue.length === 0) { bar.style.display = 'none'; return; }
  bar.style.display = '';
  chips.innerHTML = exportQueue.map(name =>
    `<span class="cd-queue-chip">${esc(name)}
       <button class="cd-chip-remove" data-name="${esc(name)}">×</button>
     </span>`
  ).join('');
  chips.querySelectorAll('.cd-chip-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = exportQueue.indexOf(btn.dataset.name);
      if (idx !== -1) exportQueue.splice(idx, 1);
      renderExportQueue();
    });
  });
}

function downloadExport(format) {
  const rows = exportQueue.map(name => loadedChanges.get(name)).filter(Boolean);
  if (!rows.length) return;
  const date = new Date().toISOString().slice(0, 10);

  if (format === 'json') {
    downloadFile(`config-delta-${currentDomain}-${date}.json`,
      'application/json', JSON.stringify(rows, null, 2));
  } else if (format === 'csv') {
    const lines = ['domain,gateway,ip,install_status,category,change_type,name,properties'];
    rows.forEach(r => {
      (r.changes || []).forEach(c => {
        lines.push([
          currentDomain, r.gateway, r.ip, r.install_status,
          c.category, c.change_type, c.name,
          JSON.stringify(c.properties || {})
        ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
      });
    });
    downloadFile(`config-delta-${currentDomain}-${date}.csv`, 'text/csv', lines.join('\n'));
  } else if (format === 'html') {
    downloadFile(`config-delta-${currentDomain}-${date}.html`,
      'text/html', buildHtmlExport(rows, currentDomain, date));
  }
}

function buildHtmlExport(rows, domain, date) {
  const sections = rows.map(r => `
    <h2>${esc(r.gateway)} <small>(${esc(r.ip)})</small></h2>
    <p>Status: ${esc(r.install_status)} | Package: ${esc(r.policy_package || '')}</p>
    ${Object.entries(r.summary || {}).filter(([, v]) => v > 0)
      .map(([k, v]) => `<span style="background:#e2e8f0;padding:2px 8px;border-radius:4px;margin-right:4px">${v} ${categoryLabel(k)}</span>`).join('')}
    <table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;width:100%;margin-top:8px">
      <thead><tr><th>Type</th><th>Name</th><th>Properties</th></tr></thead>
      <tbody>
      ${(r.changes || []).map(c => `<tr>
        <td>${esc(c.change_type)}</td>
        <td>${esc(c.name)}</td>
        <td>${esc(formatProps(c.properties))}</td>
      </tr>`).join('')}
      </tbody>
    </table>`).join('<hr>');
  return `<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Config-Delta ${esc(domain)} ${esc(date)}</title>
    <style>body{font-family:sans-serif;padding:20px}h2{margin-top:24px}table{margin-top:8px}</style>
    </head><body>
    <h1>Config-Delta: ${esc(domain)} — ${esc(date)}</h1>${sections}</body></html>`;
}

// ── Pagination ────────────────────────────────────────────────────────────
function buildPager(current, total) {
  if (total <= 1) return '';
  const btn = (label, page, disabled) =>
    `<button class="btn btn-sm btn-secondary cd-pg-btn" data-page="${page}"${disabled ? ' disabled' : ''}>${label}</button>`;
  const nbtn = (page, active) =>
    `<button class="btn btn-sm ${active ? 'btn-primary' : 'btn-secondary'} cd-pg-btn" data-page="${page}">${page}</button>`;
  const ellipsis = '<span class="cd-pg-ellipsis">…</span>';
  let pages = '';
  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages += nbtn(i, i === current);
  } else {
    pages += nbtn(1, current === 1);
    if (current > 4) pages += ellipsis;
    const from = Math.max(2, current - 2);
    const to = Math.min(total - 1, current + 2);
    for (let i = from; i <= to; i++) pages += nbtn(i, i === current);
    if (current < total - 3) pages += ellipsis;
    pages += nbtn(total, current === total);
  }
  return btn('«', 1, current <= 1) + btn('‹', current - 1, current <= 1) +
    pages +
    btn('›', current + 1, current >= total) + btn('»', total, current >= total);
}

// ── Utilities ─────────────────────────────────────────────────────────────
function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function downloadFile(filename, mime, content) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], { type: mime }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
