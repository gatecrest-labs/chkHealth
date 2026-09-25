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
  else if (tab === 'cdJobs') initCdJobs();
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
        <button class="btn btn-sm btn-secondary" data-action="edit-group" data-group='${esc(JSON.stringify(g))}'>Edit</button>
        <button class="btn btn-sm btn-secondary" data-action="delete-group" data-name="${esc(g.name)}">Delete</button>
      </td>
    </tr>
  `).join('');
}

document.getElementById('addGroupBtn').addEventListener('click', () => openGroupEdit(null));

document.getElementById('groupsTbody').addEventListener('click', e => {
  const editBtn = e.target.closest('[data-action="edit-group"]');
  if (editBtn) { openGroupEdit(JSON.parse(editBtn.dataset.group)); return; }
  const deleteBtn = e.target.closest('[data-action="delete-group"]');
  if (deleteBtn) { deleteGroup(deleteBtn.dataset.name); }
});
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
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ── Init ──────────────────────────────────────────────────────────────────
loadUsers();

// ── Config-Delta Jobs ──────────────────────────────────────────────────────
let _cdJobs = [];
let _cdPage = 0;
const _cdPageSize = 10;

async function initCdJobs() {
  const resp = await fetch('/admin/api/config-delta/jobs');
  if (!resp.ok) return;
  _cdJobs = await resp.json();
  renderCdJobs();
  await populateCdDomainSelect();

  // Wire form buttons once after panel is visible
  const newBtn = document.getElementById('cdJobNewBtn');
  if (newBtn && !newBtn._cdWired) {
    newBtn._cdWired = true;
    newBtn.addEventListener('click', openNewForm);
    document.getElementById('cdJobSaveBtn').addEventListener('click', saveJobForm);
    document.getElementById('cdJobCancelBtn').addEventListener('click', () => {
      document.getElementById('cdJobForm').style.display = 'none';
    });
  }
}

function renderCdJobs() {
  const start = _cdPage * _cdPageSize;
  const slice = _cdJobs.slice(start, start + _cdPageSize);
  const tbody = document.getElementById('cdJobsTbody');
  if (!tbody) return;
  if (!slice.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-muted">No jobs configured.</td></tr>';
  } else {
    tbody.innerHTML = slice.map(j => {
      const runs = j.runs || [];
      const last = runs.length ? runs[runs.length - 1] : null;
      const lastRan = last ? last.ran_at.slice(0, 16).replace('T', ' ') : '—';
      const statusBadge = last
        ? (last.status === 'ok'
            ? '<span class="badge badge-green">ok</span>'
            : `<span class="badge badge-red" title="${esc(last.error || '')}">error</span>`)
        : '<span class="badge badge-gray">—</span>';
      return `<tr>
        <td>${esc(j.domain)}</td>
        <td>${esc((j.days_of_week || []).join(', '))}</td>
        <td>${esc(j.time)}</td>
        <td>${esc(j.format)}</td>
        <td>${esc(j.email)}</td>
        <td>${esc(lastRan)}</td>
        <td>${statusBadge}</td>
        <td>
          <button class="btn btn-xs btn-secondary cd-job-edit" data-id="${esc(j.id)}">Edit</button>
          <button class="btn btn-xs btn-danger cd-job-delete" data-id="${esc(j.id)}">Delete</button>
          <button class="btn btn-xs btn-secondary cd-job-run" data-id="${esc(j.id)}">Run Now</button>
        </td>
      </tr>`;
    }).join('');
  }
  tbody.querySelectorAll('.cd-job-edit').forEach(btn => {
    btn.addEventListener('click', () => openEditForm(btn.dataset.id));
  });
  tbody.querySelectorAll('.cd-job-delete').forEach(btn => {
    btn.addEventListener('click', () => deleteJob(btn.dataset.id));
  });
  tbody.querySelectorAll('.cd-job-run').forEach(btn => {
    btn.addEventListener('click', () => runJob(btn.dataset.id));
  });
  const totalPages = Math.ceil(_cdJobs.length / _cdPageSize);
  const pager = document.getElementById('cdJobsPager');
  if (pager) pager.innerHTML = buildCdPager(_cdPage, totalPages);
  document.querySelectorAll('.cd-pager-btn').forEach(btn => {
    btn.addEventListener('click', () => { _cdPage = parseInt(btn.dataset.page, 10); renderCdJobs(); });
  });
}

function buildCdPager(current, total) {
  if (total <= 1) return '';
  const btn = (label, p, disabled) =>
    `<button class="btn btn-sm btn-secondary cd-pager-btn" data-page="${p}"${disabled?' disabled':''}>${label}</button>`;
  return btn('‹', current - 1, current <= 0) +
    `<span class="cd-pg-label">${current + 1} / ${total}</span>` +
    btn('›', current + 1, current >= total - 1);
}

async function populateCdDomainSelect() {
  const sel = document.getElementById('cdJobDomain');
  if (!sel) return;
  const resp = await fetch('/admin/api/domains');
  if (!resp.ok) return;
  const domains = await resp.json();
  sel.innerHTML = (domains || []).map(d => {
    const name = typeof d === 'string' ? d : d.name;
    return `<option value="${esc(name)}">${esc(name)}</option>`;
  }).join('');
}

function openNewForm() {
  document.getElementById('cdJobFormTitle').textContent = 'New Job';
  document.getElementById('cdJobEditId').value = '';
  document.getElementById('cdJobDomain').value = '';
  document.querySelectorAll('.cd-day-checks input').forEach(cb => { cb.checked = false; });
  document.getElementById('cdJobTime').value = '06:00';
  document.getElementById('cdJobFormat').value = 'html';
  document.getElementById('cdJobEmail').value = '';
  document.getElementById('cdJobEnabled').checked = true;
  document.getElementById('cdJobForm').style.display = '';
}

function openEditForm(jobId) {
  const job = _cdJobs.find(j => j.id === jobId);
  if (!job) return;
  document.getElementById('cdJobFormTitle').textContent = 'Edit Job';
  document.getElementById('cdJobEditId').value = job.id;
  document.getElementById('cdJobDomain').value = job.domain || '';
  const days = job.days_of_week || [];
  document.querySelectorAll('.cd-day-checks input').forEach(cb => {
    cb.checked = days.includes(cb.value);
  });
  document.getElementById('cdJobTime').value = job.time || '06:00';
  document.getElementById('cdJobFormat').value = job.format || 'html';
  document.getElementById('cdJobEmail').value = job.email || '';
  document.getElementById('cdJobEnabled').checked = !!job.enabled;
  document.getElementById('cdJobForm').style.display = '';
}

async function saveJobForm() {
  const jobId = document.getElementById('cdJobEditId').value;
  const days = [...document.querySelectorAll('.cd-day-checks input:checked')].map(c => c.value);
  const payload = {
    domain: document.getElementById('cdJobDomain').value,
    days_of_week: days,
    time: document.getElementById('cdJobTime').value,
    format: document.getElementById('cdJobFormat').value,
    email: document.getElementById('cdJobEmail').value,
    enabled: document.getElementById('cdJobEnabled').checked,
  };
  const url = jobId
    ? `/admin/api/config-delta/jobs/${encodeURIComponent(jobId)}`
    : '/admin/api/config-delta/jobs';
  const method = jobId ? 'PUT' : 'POST';
  const resp = await fetch(url, {
    method, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) { alert('Save failed'); return; }
  document.getElementById('cdJobForm').style.display = 'none';
  await initCdJobs();
}

async function deleteJob(jobId) {
  if (!confirm('Delete this job?')) return;
  await fetch(`/admin/api/config-delta/jobs/${encodeURIComponent(jobId)}`, {
    method: 'DELETE', headers: { 'X-CSRF-Token': CSRF },
  });
  await initCdJobs();
}

async function runJob(jobId) {
  const resp = await fetch(`/admin/api/config-delta/jobs/${encodeURIComponent(jobId)}/run`, {
    method: 'POST', headers: { 'X-CSRF-Token': CSRF },
  });
  if (resp.ok) {
    alert('Job triggered. Check Last Run status in a moment.');
  } else if (resp.status === 409) {
    alert('Job is already running.');
  } else {
    alert('Failed to trigger job.');
  }
}
