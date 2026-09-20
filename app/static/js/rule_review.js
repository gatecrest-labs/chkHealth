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
        <td>${esc(objName((rule.track || {}).type))}</td>
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
