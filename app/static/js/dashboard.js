const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

// ── Summary ───────────────────────────────────────────────────────────────
async function loadSummary() {
  const r = await fetch('/api/dashboard/summary');
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById('gwCount').textContent = (data.gw_count ?? 0).toLocaleString();
  document.getElementById('ruleCount').textContent = (data.rule_count ?? 0).toLocaleString();
  document.getElementById('summaryUpdated').textContent =
    data.last_updated ? 'Counts as of ' + data.last_updated : '';
  drawSparkline('gwChart',   (data.history || []).map(h => h.gw_count),   '#0d6efd');
  drawSparkline('ruleChart', (data.history || []).map(h => h.rule_count), '#198754');
}

document.getElementById('refreshSummaryBtn').addEventListener('click', async () => {
  document.getElementById('refreshSummaryBtn').disabled = true;
  await fetch('/api/dashboard/refresh', { method: 'POST', headers: { 'X-CSRF-Token': CSRF } });
  setTimeout(() => {
    loadSummary();
    document.getElementById('refreshSummaryBtn').disabled = false;
  }, 2000);
});

// ── Sparkline (vanilla Canvas) ────────────────────────────────────────────
function drawSparkline(canvasId, values, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.offsetWidth;
  const h = canvas.offsetHeight || 60;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  if (!values || values.length < 2) {
    ctx.fillStyle = '#ccc';
    ctx.font = '11px system-ui';
    ctx.fillText('No data', 8, h / 2 + 4);
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pad = 4;
  const xStep = (w - pad * 2) / (values.length - 1);
  const yScale = (h - pad * 2) / range;
  const pts = values.map((v, i) => ({
    x: pad + i * xStep,
    y: h - pad - (v - min) * yScale,
  }));

  ctx.beginPath();
  ctx.moveTo(pts[0].x, h - pad);
  ctx.lineTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length - 1].x, h - pad);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + '55');
  grad.addColorStop(1, color + '08');
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ── Health cards ──────────────────────────────────────────────────────────
async function loadHealth() {
  const r = await fetch('/api/dashboard/health');
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById('healthUpdated').textContent =
    data.last_updated ? 'Updated ' + data.last_updated : '';
  const LABEL = {
    healthy: '&#9679; Healthy',
    unreachable: '&#9679; Unreachable',
    degraded: '&#9679; Degraded',
    standby: '&#9679; Standby (HA)',
  };
  const container = document.getElementById('healthCards');
  container.innerHTML = (data.servers || []).map(s => {
    const cls = s.status === 'healthy'  ? 'healthy'
              : s.status === 'degraded' ? 'degraded'
              : s.status === 'standby'  ? 'standby' : 'unhealthy';
    return `
      <div class="health-card ${cls}">
        <div class="health-card-name">
          <strong>${esc(s.label)}</strong>
          <span class="health-ip">${esc(s.host)}</span>
          <span class="badge badge-secondary" style="font-size:.7rem">${esc(s.type)}</span>
        </div>
        <div class="health-card-meta">
          <div class="health-meta-item">
            <label>Status</label>
            <span>${LABEL[s.status] || esc(s.status)}</span>
          </div>
          <div class="health-meta-item">
            <label>Hostname</label><span>${esc(s.hostname || 'N/A')}</span>
          </div>
          <div class="health-meta-item">
            <label>Version</label><span>${esc(s.version || 'N/A')}</span>
          </div>
          <div class="health-meta-item">
            <label>HA Role</label><span>${esc(s.ha_role || 'N/A')}</span>
          </div>
          ${s.cpu_pct != null
            ? `<div class="health-meta-item"><label>CPU</label><span>${esc(String(s.cpu_pct))}%</span></div>`
            : ''}
          ${s.mem_pct != null
            ? `<div class="health-meta-item"><label>MEM</label><span>${esc(String(s.mem_pct))}%</span></div>`
            : ''}
        </div>
      </div>`;
  }).join('') ||
    '<p class="text-muted" style="font-size:.875rem">No health data yet — click Refresh Health.</p>';
}

document.getElementById('refreshHealthBtn').addEventListener('click', async () => {
  document.getElementById('refreshHealthBtn').disabled = true;
  await fetch('/api/dashboard/refresh-health',
    { method: 'POST', headers: { 'X-CSRF-Token': CSRF } });
  setTimeout(() => {
    loadHealth();
    document.getElementById('refreshHealthBtn').disabled = false;
  }, 2000);
});

// ── Auto-refresh ──────────────────────────────────────────────────────────
let _autoTimer = null;
function setAutoRefresh(minutes) {
  clearInterval(_autoTimer);
  if (minutes > 0) _autoTimer = setInterval(loadHealth, minutes * 60 * 1000);
}
document.getElementById('autoRefreshSelect').addEventListener('change', function () {
  setAutoRefresh(parseInt(this.value, 10));
});

// ── Helpers ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────
loadSummary();
loadHealth();
setAutoRefresh(15);
