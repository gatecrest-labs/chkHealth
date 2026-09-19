const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

// ── Tab switching ─────────────────────────────────────────────────────────
document.querySelectorAll('.admin-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.admin-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.admin-panel').forEach(p => p.style.display = 'none');
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.tab).style.display = '';
    loadTab(btn.dataset.tab);
  });
});

function loadTab(tab) {
  if (tab === 'users') loadUsers();
  else if (tab === 'groups') loadGroups();
  else if (tab === 'logs') loadLogs();
  else if (tab === 'settings') loadSettings();
  else if (tab === 'tabs') loadTabs();
}

// ── CSS for admin tabs ────────────────────────────────────────────────────
const style = document.createElement('style');
style.textContent = `
  .admin-tabs { display:flex; gap:.25rem; border-bottom:2px solid var(--border); margin-bottom:0; }
  .admin-tab { background:none; border:none; padding:.5rem 1rem; cursor:pointer; font-size:.875rem; color:var(--text-muted); border-bottom:2px solid transparent; margin-bottom:-2px; }
  .admin-tab.active { color:var(--primary); border-bottom-color:var(--primary); font-weight:600; }
`;
document.head.appendChild(style);

// ── Users ─────────────────────────────────────────────────────────────────
async function loadUsers() {
  const r = await fetch('/admin/api/users');
  const users = await r.json();
  const tbody = document.getElementById('usersTbody');
  tbody.innerHTML = users.map(u => `
    <tr>
      <td>${esc(u.username)}</td>
      <td><span class="badge badge-${u.role === 'admin' ? 'danger' : 'secondary'}">${esc(u.role)}</span></td>
      <td></td>
    </tr>
  `).join('');
}

// ── Groups ────────────────────────────────────────────────────────────────
let allTabs = {};
let editingGroup = null;

async function loadGroups() {
  const [gr, tr] = await Promise.all([
    fetch('/admin/api/groups').then(r => r.json()),
    fetch('/admin/api/tabs').then(r => r.json()),
  ]);
  allTabs = tr;
  const tbody = document.getElementById('groupsTbody');
  tbody.innerHTML = gr.map(g => `
    <tr>
      <td>${esc(g.name)}</td>
      <td>${esc((g.members || []).join(', '))}</td>
      <td>${esc((g.allowed_tabs || []).join(', '))}</td>
      <td>${g.domain_restrict ? 'Yes: ' + esc((g.allowed_domains || []).join(', ')) : 'No'}</td>
      <td>
        <button class="btn btn-sm btn-secondary" onclick="openGroupEdit(${JSON.stringify(g)})">Edit</button>
        <button class="btn btn-sm btn-secondary" onclick="deleteGroup('${esc(g.name)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

document.getElementById('addGroupBtn').addEventListener('click', () => openGroupEdit(null));
document.getElementById('groupModalClose').addEventListener('click', () => document.getElementById('groupModal').style.display = 'none');
document.getElementById('groupModalCancel').addEventListener('click', () => document.getElementById('groupModal').style.display = 'none');
document.getElementById('groupDomainRestrict').addEventListener('change', function() {
  document.getElementById('groupDomainsRow').style.display = this.checked ? '' : 'none';
});

function openGroupEdit(g) {
  editingGroup = g ? g.name : null;
  document.getElementById('groupModalTitle').textContent = g ? 'Edit Group' : 'New Group';
  document.getElementById('groupName').value = g ? g.name : '';
  document.getElementById('groupName').disabled = !!g;
  document.getElementById('groupMembers').value = g ? (g.members || []).join('\n') : '';
  document.getElementById('groupDomainRestrict').checked = g ? !!g.domain_restrict : false;
  document.getElementById('groupDomains').value = g ? (g.allowed_domains || []).join('\n') : '';
  document.getElementById('groupDomainsRow').style.display = (g && g.domain_restrict) ? '' : 'none';

  const checks = document.getElementById('groupTabChecks');
  checks.innerHTML = Object.entries(allTabs).map(([key, name]) => `
    <label style="display:inline-flex;align-items:center;gap:.35rem;margin-right:1rem">
      <input type="checkbox" value="${esc(key)}" ${g && (g.allowed_tabs || []).includes(key) ? 'checked' : ''}>
      ${esc(name)}
    </label>
  `).join('');
  document.getElementById('groupModal').style.display = 'flex';
}

document.getElementById('groupModalSave').addEventListener('click', async () => {
  const name = document.getElementById('groupName').value.trim();
  if (!name) { alert('Name is required'); return; }
  const members = document.getElementById('groupMembers').value.split('\n').map(s => s.trim()).filter(Boolean);
  const allowed_tabs = Array.from(document.querySelectorAll('#groupTabChecks input:checked')).map(el => el.value);
  const domain_restrict = document.getElementById('groupDomainRestrict').checked;
  const allowed_domains = document.getElementById('groupDomains').value.split('\n').map(s => s.trim()).filter(Boolean);

  const method = editingGroup ? 'PUT' : 'POST';
  const url = editingGroup ? `/admin/api/groups/${encodeURIComponent(editingGroup)}` : '/admin/api/groups';
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
    body: JSON.stringify({ name, members, allowed_tabs, domain_restrict, allowed_domains }),
  });
  if (r.ok) { document.getElementById('groupModal').style.display = 'none'; loadGroups(); }
  else { const e = await r.json(); alert(e.error || 'Error saving group'); }
});

async function deleteGroup(name) {
  if (!confirm(`Delete group '${name}'?`)) return;
  await fetch(`/admin/api/groups/${encodeURIComponent(name)}`, { method: 'DELETE', headers: { 'X-CSRF-Token': CSRF } });
  loadGroups();
}

// ── Logs ──────────────────────────────────────────────────────────────────
document.getElementById('logRefreshBtn').addEventListener('click', loadLogs);
document.getElementById('logClearBtn').addEventListener('click', async () => {
  await fetch('/admin/api/logs', { method: 'DELETE', headers: { 'X-CSRF-Token': CSRF } });
  loadLogs();
});
document.getElementById('logSetLevelBtn').addEventListener('click', async () => {
  const level = document.getElementById('logLevelFilter').value;
  if (!level) return;
  await fetch('/admin/api/logs/level', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
    body: JSON.stringify({ level }),
  });
  loadLogs();
});

async function loadLogs() {
  const level = document.getElementById('logLevelFilter').value;
  const component = document.getElementById('logComponentFilter').value.trim();
  const params = new URLSearchParams({ limit: 500 });
  if (level) params.set('level', level);
  if (component) params.set('component', component);
  const entries = await fetch(`/admin/api/logs?${params}`).then(r => r.json());
  const LEVEL_CLASS = { ERROR: 'danger', WARN: 'warning', INFO: 'secondary', DEBUG: 'secondary', TRACE: 'secondary' };
  const tbody = document.getElementById('logsTbody');
  tbody.innerHTML = [...entries].reverse().map(e => `
    <tr>
      <td style="white-space:nowrap;font-size:.78rem">${esc(e.ts)}</td>
      <td><span class="badge badge-${LEVEL_CLASS[e.level] || 'secondary'}">${esc(e.level)}</span></td>
      <td style="font-size:.82rem">${esc(e.component)}</td>
      <td style="font-size:.82rem">${esc(e.message)}${e.extra ? ' <span class="text-muted">— ' + esc(JSON.stringify(e.extra)) + '</span>' : ''}</td>
    </tr>
  `).join('');
}

// ── Settings ──────────────────────────────────────────────────────────────
async function loadSettings() {
  const settings = await fetch('/admin/api/settings').then(r => r.json());
  const body = document.getElementById('settingsBody');
  if (Object.keys(settings).length === 0) {
    body.innerHTML = '<p class="text-muted" style="font-size:.875rem">No settings configured.</p>';
    return;
  }
  body.innerHTML = Object.entries(settings).map(([k, v]) => `
    <div style="display:flex;align-items:center;gap:1rem;padding:.5rem 0;border-bottom:1px solid var(--border)">
      <code style="flex:0 0 220px">${esc(k)}</code>
      <span>${esc(String(v))}</span>
    </div>
  `).join('');
}

// ── Tab Registry ──────────────────────────────────────────────────────────
async function loadTabs() {
  const tabs = await fetch('/admin/api/tabs').then(r => r.json());
  const tbody = document.getElementById('tabsTbody');
  tbody.innerHTML = Object.entries(tabs).map(([k, v]) => `
    <tr><td><code>${esc(k)}</code></td><td>${esc(v)}</td></tr>
  `).join('');
}

// ── Helpers ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────
loadUsers();
