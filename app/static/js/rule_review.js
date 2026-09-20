function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
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

function nameStack(arr) {
  if (!Array.isArray(arr)) {
    const s = objName(arr);
    return s ? `<div>${esc(s)}</div>` : '<div class="text-muted">—</div>';
  }
  if (!arr.length) return '<div class="text-muted">—</div>';
  return arr.map(o => `<div>${esc(objName(o))}</div>`).join('');
}

function downloadFile(filename, type, content) {
  const blob = new Blob([content], {type});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Shared domain loader ──────────────────────────────────────────────────
async function populateDomainSelect(selectId, onChangeCb) {
  const r = await fetch('/api/firewalls/domains');
  if (!r.ok) return;
  const data = await r.json();
  const sel = document.getElementById(selectId);
  (data.domains || []).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    sel.appendChild(opt);
  });
  if (onChangeCb) sel.addEventListener('change', onChangeCb);
}

// ── Section 1: Policy Rules ───────────────────────────────────────────────
let _allRules = [];
let _filteredRules = [];
let _rulesPage = 1;
let _rulesExportName = 'rules';

function _rulesPageSize() {
  return parseInt(document.getElementById('rulesPageSize').value, 10);
}

function _matchesRuleFilter(rule, query, field, useRegex) {
  if (!query) return true;
  let rx = null;
  if (useRegex) {
    try { rx = new RegExp(query, 'i'); } catch { return false; }
  }
  const test = v => {
    const s = String(v ?? '');
    return rx ? rx.test(s) : s.toLowerCase().includes(query.toLowerCase());
  };
  const testList = arr => {
    if (!Array.isArray(arr)) return test(arr);
    return arr.some(x => test(x));
  };
  if (field === 'name')        return test(rule.name);
  if (field === 'source')      return testList(rule.source);
  if (field === 'destination') return testList(rule.destination);
  if (field === 'service')     return testList(rule.service);
  if (field === 'comments')    return test(rule.comments);
  return test(rule.name) || testList(rule.source) || testList(rule.destination) ||
         testList(rule.service) || test(rule.comments);
}

function applyRulesFilter() {
  const q     = document.getElementById('rulesSearch').value;
  const field = document.getElementById('rulesSearchField').value;
  const regex = document.getElementById('rulesRegex').checked;
  _filteredRules = _allRules.filter(r => _matchesRuleFilter(r, q, field, regex));
  _rulesPage = 1;
  renderRulesTable();
}

function renderRulesTable() {
  const ps = _rulesPageSize();
  const total = _filteredRules.length;
  const pages = ps > 0 ? Math.ceil(total / ps) : 1;
  if (_rulesPage > pages) _rulesPage = pages || 1;

  const slice = ps > 0
    ? _filteredRules.slice((_rulesPage - 1) * ps, _rulesPage * ps)
    : _filteredRules;

  document.getElementById('rulesPageInfo').textContent =
    `${total} rule(s) — page ${_rulesPage} of ${pages}`;

  document.getElementById('rulesTbody').innerHTML = slice.map(rule => {
    const action = objName(rule.action);
    const actionCls = action.toLowerCase() === 'accept' ? 'badge-action-accept' : 'badge-action-drop';
    const trackType = objName((rule.track || {}).type);
    return `<tr>
      <td style="white-space:nowrap;font-size:.8rem;color:var(--text-muted)">${esc(rule['rule-number'])}</td>
      <td><strong>${esc(rule.name || '')}</strong></td>
      <td class="rr-list-cell">${nameStack(rule.source)}</td>
      <td class="rr-list-cell">${nameStack(rule.destination)}</td>
      <td class="rr-list-cell">${nameStack(rule.service)}</td>
      <td><span class="badge ${esc(actionCls)}">${esc(action)}</span></td>
      <td style="font-size:.82rem">${esc(trackType)}</td>
      <td style="font-size:.82rem">${rule.enabled ? 'Yes' : 'No'}</td>
      <td style="font-size:.82rem">${esc(rule.comments || '')}</td>
    </tr>`;
  }).join('');

  renderPagination('rulesPagination', total, _rulesPage, ps, p => { _rulesPage = p; renderRulesTable(); });
}

// ── Rules export ──────────────────────────────────────────────────────────
document.getElementById('rulesExportCSV').addEventListener('click', () => {
  const hdr = ['#','Name','Source','Destination','Service','Action','Track','Enabled','Comments'];
  const rows = _filteredRules.map(r => [
    r['rule-number'], r.name || '',
    (r.source||[]).join('; '), (r.destination||[]).join('; '), (r.service||[]).join('; '),
    objName(r.action), objName((r.track||{}).type), r.enabled ? 'Yes' : 'No', r.comments||'',
  ]);
  const csv = [hdr,...rows].map(row => row.map(c => `"${String(c).replace(/"/g,'""')}"`).join(',')).join('\n');
  downloadFile(_rulesExportName + '.csv', 'text/csv;charset=utf-8;', '﻿' + csv);
});

document.getElementById('rulesExportJSON').addEventListener('click', () => {
  downloadFile(_rulesExportName + '.json', 'application/json', JSON.stringify(_filteredRules, null, 2));
});

document.getElementById('rulesExportHTML').addEventListener('click', () => {
  const hdr = ['#','Name','Source','Destination','Service','Action','Track','Enabled','Comments'];
  const bodyRows = _filteredRules.map(r => {
    const action = objName(r.action);
    const span = `<span class="${action.toLowerCase()==='accept'?'accept':'drop'}">${esc(action)}</span>`;
    return `<tr>
      <td>${r['rule-number']}</td><td><strong>${esc(r.name||'')}</strong></td>
      <td>${(r.source||[]).map(esc).join('<br>')}</td>
      <td>${(r.destination||[]).map(esc).join('<br>')}</td>
      <td>${(r.service||[]).map(esc).join('<br>')}</td>
      <td>${span}</td>
      <td>${esc(objName((r.track||{}).type))}</td>
      <td>${r.enabled?'Yes':'No'}</td>
      <td>${esc(r.comments||'')}</td>
    </tr>`;
  }).join('');
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8">
<title>${esc(_rulesExportName)}</title>
<style>
body{font-family:system-ui,sans-serif;font-size:13px;padding:20px;color:#1a1a2e}
h2{margin-bottom:.25rem}p{color:#666;margin-bottom:1rem;font-size:.85rem}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:5px 9px;text-align:left;vertical-align:top}
th{background:#f2f4f8;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
tr:nth-child(even){background:#fafbfd}
.accept{background:#d1e7dd;color:#0a3622;padding:2px 7px;border-radius:3px;font-size:11px;white-space:nowrap}
.drop{background:#f8d7da;color:#842029;padding:2px 7px;border-radius:3px;font-size:11px;white-space:nowrap}
</style></head><body>
<h2>${esc(_rulesExportName)}</h2>
<p>${_filteredRules.length} rule(s) exported ${new Date().toLocaleString()}</p>
<table><thead><tr>${hdr.map(h=>`<th>${h}</th>`).join('')}</tr></thead>
<tbody>${bodyRows}</tbody></table>
</body></html>`;
  downloadFile(_rulesExportName + '.html', 'text/html;charset=utf-8', html);
});

// ── Rules load ────────────────────────────────────────────────────────────
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
    opt.value = p; opt.textContent = p;
    pkgSel.appendChild(opt);
  });
  pkgSel.disabled = false;
  pkgSel.addEventListener('change', () => { loadBtn.disabled = !pkgSel.value; });
});

document.getElementById('rulesLoadBtn').addEventListener('click', async () => {
  const domain = document.getElementById('rulesDomainSelect').value;
  const pkg    = document.getElementById('rulesPackageSelect').value;
  if (!domain || !pkg) return;
  _rulesExportName = `${domain}_${pkg}`;
  document.getElementById('rulesStatus').textContent = 'Loading…';
  document.getElementById('rulesLoadBtn').disabled = true;
  document.getElementById('rulesTableSection').style.display = 'none';
  try {
    const r = await fetch(`/api/rule-review/rules?domain=${encodeURIComponent(domain)}&package=${encodeURIComponent(pkg)}`);
    if (!r.ok) { document.getElementById('rulesStatus').textContent = 'Error loading.'; return; }
    const data = await r.json();
    _allRules = data.rules || [];
    document.getElementById('rulesStatus').textContent = `${_allRules.length} rule(s) loaded`;
    document.getElementById('rulesTableSection').style.display = '';
    applyRulesFilter();
  } finally {
    document.getElementById('rulesLoadBtn').disabled = false;
  }
});

['rulesSearch','rulesSearchField','rulesRegex','rulesPageSize'].forEach(id => {
  const el = document.getElementById(id);
  el.addEventListener(el.tagName === 'SELECT' ? 'change' : el.type === 'checkbox' ? 'change' : 'input', applyRulesFilter);
});

// ── Section 2: Object Lookup ──────────────────────────────────────────────
let _allObjects = [];
let _filteredObjects = [];
let _objPage = 1;
let _objExportName = 'objects';

function _objPageSize() {
  return parseInt(document.getElementById('objPageSize').value, 10);
}

function applyObjFilter() {
  const q = document.getElementById('objFilter').value.toLowerCase();
  _filteredObjects = q
    ? _allObjects.filter(o => (o.name||'').toLowerCase().includes(q) || (o.comments||'').toLowerCase().includes(q))
    : [..._allObjects];
  _objPage = 1;
  renderObjTable();
}

function renderObjTable() {
  const ps = _objPageSize();
  const total = _filteredObjects.length;
  const pages = ps > 0 ? Math.ceil(total / ps) : 1;
  if (_objPage > pages) _objPage = pages || 1;

  const slice = ps > 0
    ? _filteredObjects.slice((_objPage - 1) * ps, _objPage * ps)
    : _filteredObjects;

  const offset = ps > 0 ? (_objPage - 1) * ps : 0;

  document.getElementById('objPageInfo').textContent =
    `${total} object(s) — page ${_objPage} of ${pages}`;

  const typeColors = {
    host: '#cfe2ff', network: '#d1e7dd', group: '#fff3cd',
    'address-range': '#f8d7da', 'service-tcp': '#e2d9f3',
    'service-udp': '#e2d9f3', 'service-group': '#fde8ce',
  };

  document.getElementById('objTbody').innerHTML = slice.map((obj, i) => {
    const bg = typeColors[obj.type] || '#e9ecef';
    const typeBadge = `<span class="badge" style="background:${bg};color:#1a1a2e;font-size:.75rem">${esc(obj.type||'')}</span>`;

    let detailHtml = '';
    if (obj.members && obj.members.length) {
      detailHtml = obj.members.map(m => `<div style="font-size:.8rem">${esc(m)}</div>`).join('');
    } else if (obj.detail) {
      detailHtml = `<span style="font-size:.82rem">${esc(obj.detail)}</span>`;
    }

    const domain = document.getElementById('objDomainSelect').value;
    return `<tr>
      <td style="color:var(--text-muted);font-size:.8rem">${offset + i + 1}</td>
      <td><strong>${esc(obj.name||'')}</strong></td>
      <td>${typeBadge}</td>
      <td style="font-size:.82rem">${esc(obj.category||'')}</td>
      <td>${detailHtml}</td>
      <td style="font-size:.82rem">${esc(obj.comments||'')}</td>
      <td><button class="btn btn-sm btn-secondary wu-btn"
            data-uid="${esc(obj.uid||'')}"
            data-name="${esc(obj.name||'')}"
            data-domain="${esc(domain)}">Where Used</button></td>
    </tr>`;
  }).join('');

  document.querySelectorAll('.wu-btn').forEach(btn => {
    btn.addEventListener('click', () => openWhereUsed(btn.dataset.uid, btn.dataset.name, btn.dataset.domain));
  });

  renderPagination('objPagination', total, _objPage, ps, p => { _objPage = p; renderObjTable(); });
}

populateDomainSelect('objDomainSelect');

document.getElementById('objSearchBtn').addEventListener('click', async () => {
  const domain = document.getElementById('objDomainSelect').value;
  const name   = document.getElementById('objNameInput').value.trim();
  if (!domain || !name) {
    document.getElementById('objStatus').textContent = 'Domain and name are required.';
    return;
  }
  _objExportName = `objects_${domain}_${name}`;
  document.getElementById('objStatus').textContent = 'Searching…';
  document.getElementById('objTableSection').style.display = 'none';
  const r = await fetch(`/api/rule-review/objects?domain=${encodeURIComponent(domain)}&name=${encodeURIComponent(name)}`);
  if (!r.ok) { document.getElementById('objStatus').textContent = 'Error.'; return; }
  const data = await r.json();
  _allObjects = data.objects || [];
  document.getElementById('objStatus').textContent = `${_allObjects.length} result(s)`;
  document.getElementById('objFilter').value = '';
  document.getElementById('objTableSection').style.display = '';
  applyObjFilter();
});

document.getElementById('objNameInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('objSearchBtn').click();
});

document.getElementById('objFilter').addEventListener('input', applyObjFilter);
document.getElementById('objPageSize').addEventListener('change', applyObjFilter);

// ── Object export ─────────────────────────────────────────────────────────
document.getElementById('objExportCSV').addEventListener('click', () => {
  const hdr = ['Name','Type','Category','Detail','Members','Comments'];
  const rows = _filteredObjects.map(o => [
    o.name||'', o.type||'', o.category||'', o.detail||'',
    (o.members||[]).join('; '), o.comments||'',
  ]);
  const csv = [hdr,...rows].map(row => row.map(c => `"${String(c).replace(/"/g,'""')}"`).join(',')).join('\n');
  downloadFile(_objExportName + '.csv', 'text/csv;charset=utf-8;', '﻿' + csv);
});

document.getElementById('objExportJSON').addEventListener('click', () => {
  downloadFile(_objExportName + '.json', 'application/json', JSON.stringify(_filteredObjects, null, 2));
});

// ── Shared pagination renderer ────────────────────────────────────────────
function renderPagination(containerId, total, page, pageSize, onPage) {
  const el = document.getElementById(containerId);
  if (pageSize === 0 || total === 0) { el.innerHTML = ''; return; }
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) { el.innerHTML = ''; return; }
  const btn = (label, p, disabled) =>
    `<button class="btn btn-sm btn-secondary rr-pg-btn" data-page="${p}"${disabled?' disabled':''}>${label}</button>`;
  el.innerHTML =
    btn('«', 1, page <= 1) + btn('‹', page - 1, page <= 1) +
    `<span class="rr-pg-label">${page} / ${pages}</span>` +
    btn('›', page + 1, page >= pages) + btn('»', pages, page >= pages);
  el.querySelectorAll('.rr-pg-btn').forEach(b => {
    b.addEventListener('click', () => onPage(parseInt(b.dataset.page, 10)));
  });
}

// ── Section 3: Interface Lookup ───────────────────────────────────────────
populateDomainSelect('ifDomainSelect');

document.getElementById('ifSearchBtn').addEventListener('click', async () => {
  const domain = document.getElementById('ifDomainSelect').value;
  const ips    = document.getElementById('ifIpsInput').value.trim();
  if (!domain || !ips) {
    document.getElementById('ifStatus').textContent = 'Domain and IPs are required.'; return;
  }
  document.getElementById('ifStatus').textContent = 'Searching…';
  document.getElementById('ifTableSection').style.display = 'none';
  const r = await fetch(`/api/rule-review/interfaces?domain=${encodeURIComponent(domain)}&ips=${encodeURIComponent(ips)}`);
  if (!r.ok) { document.getElementById('ifStatus').textContent = 'Error.'; return; }
  const data = await r.json();
  document.getElementById('ifStatus').textContent = `${(data.results||[]).length} match(es)`;
  document.getElementById('ifTbody').innerHTML = (data.results||[]).map(res => `<tr>
    <td>${esc(res.gateway)}</td><td>${esc(res.interface)}</td><td>${esc(res.ip)}</td>
    <td>${esc(res.subnet)}</td><td>${esc(res.mask)}</td>
  </tr>`).join('') || '<tr><td colspan="5" class="text-muted">No matches.</td></tr>';
  document.getElementById('ifTableSection').style.display = '';
});

// ── Section 4: NAT Lookup ─────────────────────────────────────────────────
populateDomainSelect('natDomainSelect');

document.getElementById('natSearchBtn').addEventListener('click', async () => {
  const domain = document.getElementById('natDomainSelect').value;
  const ip     = document.getElementById('natIpInput').value.trim();
  if (!domain || !ip) {
    document.getElementById('natStatus').textContent = 'Domain and IP are required.'; return;
  }
  document.getElementById('natStatus').textContent = 'Searching…';
  document.getElementById('natTableSection').style.display = 'none';
  const r = await fetch(`/api/rule-review/nat?domain=${encodeURIComponent(domain)}&ip=${encodeURIComponent(ip)}`);
  if (!r.ok) { document.getElementById('natStatus').textContent = 'Error.'; return; }
  const data = await r.json();
  document.getElementById('natStatus').textContent = `${(data.results||[]).length} match(es)`;
  const f = (res, field) => esc(objName(res[field]));
  document.getElementById('natTbody').innerHTML = (data.results||[]).map(res => `<tr>
    <td>${esc(res.package)}</td><td>${esc(res['rule-number'])}</td>
    <td>${f(res,'original-source')}</td><td>${f(res,'original-destination')}</td>
    <td>${f(res,'original-service')}</td>
    <td>${f(res,'translated-source')}</td><td>${f(res,'translated-destination')}</td>
    <td>${f(res,'translated-service')}</td>
  </tr>`).join('') || '<tr><td colspan="8" class="text-muted">No matches.</td></tr>';
  document.getElementById('natTableSection').style.display = '';
});

// ── Where Used modal ──────────────────────────────────────────────────────
async function openWhereUsed(uid, name, domain) {
  const modal = document.getElementById('whereUsedModal');
  const body  = document.getElementById('whereUsedBody');
  const title = document.getElementById('whereUsedTitle');
  title.textContent = `Where Used: ${name}`;
  body.innerHTML = '<p class="text-muted">Loading…</p>';
  modal.style.display = 'flex';

  try {
    const r = await fetch(
      `/api/rule-review/where-used?domain=${encodeURIComponent(domain)}&uid=${encodeURIComponent(uid)}&name=${encodeURIComponent(name)}`
    );
    if (!r.ok) { body.innerHTML = '<p class="text-muted">Error loading results.</p>'; return; }
    const data = await r.json();
    const rules = data.rules || [];

    if (!rules.length) {
      body.innerHTML = `<p class="text-muted">No access-control rules reference this object in the <strong>${esc(domain)}</strong> domain.</p>`;
      return;
    }

    // Group by package
    const byPkg = {};
    rules.forEach(rule => {
      const key = rule.package || '(unknown package)';
      if (!byPkg[key]) byPkg[key] = { domain: rule.package_domain, rules: [] };
      byPkg[key].rules.push(rule);
    });

    let html = `<p style="font-size:.85rem;color:var(--text-muted);margin-bottom:1rem">
      Found in <strong>${rules.length}</strong> rule(s) across <strong>${Object.keys(byPkg).length}</strong> package(s) — searched in domain <strong>${esc(domain)}</strong>
    </p>`;

    for (const [pkg, info] of Object.entries(byPkg)) {
      const pkgDomainLabel = info.domain && info.domain !== domain
        ? ` <span style="font-size:.72rem;background:#fff3cd;color:#664d03;padding:1px 5px;border-radius:3px;margin-left:.35rem">${esc(info.domain)}</span>`
        : '';
      html += `<div style="margin-bottom:1.25rem">
        <div style="font-weight:600;font-size:.88rem;margin-bottom:.4rem;padding-bottom:.3rem;border-bottom:1px solid var(--border)">
          📦 ${esc(pkg)}${pkgDomainLabel}
        </div>
        <table class="data-table" style="font-size:.82rem">
          <thead><tr>
            <th style="width:3rem">#</th>
            <th>Rule Name</th>
            <th style="width:8rem">Used In</th>
            <th>Layer</th>
            <th style="width:5rem">Global</th>
          </tr></thead>
          <tbody>
            ${info.rules.map(rule => {
              const cols = (rule.columns || []).map(c => `<span style="background:#e2d9f3;color:#3d1a78;padding:1px 5px;border-radius:3px;font-size:.75rem;white-space:nowrap">${esc(c)}</span>`).join(' ');
              const globalBadge = rule.is_global
                ? '<span style="background:#cfe2ff;color:#084298;padding:1px 5px;border-radius:3px;font-size:.75rem">Global</span>'
                : '';
              return `<tr>
                <td style="color:var(--text-muted)">${esc(rule.rule_number)}</td>
                <td>${esc(rule.rule_name)}</td>
                <td>${cols || '—'}</td>
                <td style="color:var(--text-muted);font-size:.78rem">${esc(rule.layer)}</td>
                <td>${globalBadge}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>`;
    }

    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<p class="text-muted">Error loading results.</p>';
  }
}

document.getElementById('whereUsedClose').addEventListener('click', () => {
  document.getElementById('whereUsedModal').style.display = 'none';
});
document.getElementById('whereUsedModal').addEventListener('click', e => {
  if (e.target === document.getElementById('whereUsedModal'))
    document.getElementById('whereUsedModal').style.display = 'none';
});
