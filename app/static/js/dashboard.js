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
  const history = data.history || [];
  drawSparkline('gwChart',   history.map(h => ({ date: h.date, value: h.gw_count   })), '#0d6efd');
  drawSparkline('ruleChart', history.map(h => ({ date: h.date, value: h.rule_count })), '#198754');
}

document.getElementById('refreshSummaryBtn').addEventListener('click', async () => {
  const btn = document.getElementById('refreshSummaryBtn');
  btn.disabled = true;
  btn.textContent = '↺ Collecting…';
  let prevUpdated = document.getElementById('summaryUpdated').textContent;
  const resp = await fetch('/api/dashboard/refresh', { method: 'POST', headers: { 'X-CSRF-Token': CSRF } });
  if (!resp.ok) { btn.disabled = false; btn.textContent = '↺ Refresh Counts'; return; }
  let polls = 0;
  const timer = setInterval(async () => {
    polls++;
    await loadSummary();
    const nowUpdated = document.getElementById('summaryUpdated').textContent;
    if (polls >= 48 || (nowUpdated && nowUpdated !== prevUpdated)) {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = '↺ Refresh Counts';
    }
  }, 5000);
});

// ── Interactive Sparklines ────────────────────────────────────────────────
// points: [{date: "YYYY-MM-DD", value: N}, ...]
function drawSparkline(canvasId, points, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  canvas._sparkPoints = points;
  canvas._sparkColor  = color;
  _renderSparkline(canvas, null);

  if (!canvas._sparkHoverBound) {
    canvas._sparkHoverBound = true;
    canvas.addEventListener('mousemove', e => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      _renderSparkline(canvas, mx);
      _showSparkTooltip(canvas, e, mx);
    });
    canvas.addEventListener('mouseleave', () => {
      _renderSparkline(canvas, null);
      _hideSparkTooltip();
    });
  }
}

const _LABEL_H = 18;

function _renderSparkline(canvas, hoverX) {
  const points = canvas._sparkPoints;
  const color  = canvas._sparkColor;
  const ctx    = canvas.getContext('2d');
  const dpr    = window.devicePixelRatio || 1;
  const w      = canvas.offsetWidth;
  const h      = (canvas.offsetHeight || 80) - _LABEL_H;
  canvas.width  = w * dpr;
  canvas.height = (h + _LABEL_H) * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h + _LABEL_H);

  if (!points || points.length < 2) {
    ctx.fillStyle = '#ccc';
    ctx.font = '11px system-ui';
    ctx.fillText('No data', 8, h / 2 + 4);
    return;
  }

  const values = points.map(p => p.value);
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const pad = 6;
  const xStep = (w - pad * 2) / (points.length - 1);
  const yScale = (h - pad * 2) / range;
  const pts = points.map((p, i) => ({
    x: pad + i * xStep,
    y: h - pad - (p.value - min) * yScale,
    date: p.date,
    value: p.value,
  }));

  // Nearest dot index for hover
  let hoverIdx = null;
  if (hoverX !== null) {
    let minDist = Infinity;
    pts.forEach((p, i) => {
      const d = Math.abs(p.x - hoverX);
      if (d < minDist) { minDist = d; hoverIdx = i; }
    });
  }

  // Gradient fill
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

  // Line
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Dots
  pts.forEach((p, i) => {
    const active = i === hoverIdx;
    ctx.beginPath();
    ctx.arc(p.x, p.y, active ? 5 : 3, 0, Math.PI * 2);
    ctx.fillStyle = active ? color : (color + 'bb');
    ctx.fill();
    if (active) {
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  });

  // X-axis labels (MM-DD)
  ctx.fillStyle = '#888';
  ctx.font = '10px system-ui';
  ctx.textAlign = 'center';
  const maxLabels = Math.max(2, Math.floor(w / 52));
  const step = Math.max(1, Math.round((points.length - 1) / maxLabels));
  pts.forEach((p, i) => {
    if (i === 0 || i === pts.length - 1 || i % step === 0) {
      const label = p.date ? p.date.slice(5) : '';
      ctx.fillText(label, p.x, h + _LABEL_H - 3);
    }
  });
}

function _showSparkTooltip(canvas, e, hoverX) {
  const points = canvas._sparkPoints;
  if (!points || points.length < 2) return;
  const w = canvas.offsetWidth;
  const pad = 6;
  const xStep = (w - pad * 2) / (points.length - 1);
  const idx = Math.max(0, Math.min(points.length - 1, Math.round((hoverX - pad) / xStep)));
  const p = points[idx];
  const tip = _getTooltip();
  tip.textContent = (p.date || '') + ': ' + (p.value ?? 0).toLocaleString();
  tip.style.display = 'block';
  tip.style.left = (e.clientX + 14) + 'px';
  tip.style.top  = (e.clientY - 32) + 'px';
}

function _hideSparkTooltip() {
  const tip = document.getElementById('_sparkTip');
  if (tip) tip.style.display = 'none';
}

function _getTooltip() {
  let tip = document.getElementById('_sparkTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = '_sparkTip';
    tip.style.cssText = 'position:fixed;background:#1a1a1a;color:#fff;padding:4px 10px;' +
      'border-radius:4px;font-size:12px;pointer-events:none;display:none;z-index:9999;' +
      'white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,.3)';
    document.body.appendChild(tip);
  }
  return tip;
}

// ── Health cards ──────────────────────────────────────────────────────────
const _STATUS_LABEL = {
  healthy:    '&#9679; Healthy',
  reachable:  '&#9679; Reachable',
  unreachable:'&#9679; Unreachable',
  degraded:   '&#9679; Degraded',
  standby:    '&#9679; Standby (HA)',
};

function _renderHealthCard(s) {
  const cls = s.status === 'healthy'   ? 'healthy'
            : s.status === 'reachable' ? 'reachable'
            : s.status === 'degraded'  ? 'degraded'
            : s.status === 'standby'   ? 'standby' : 'unhealthy';
  return `
    <div class="health-card ${cls}">
      <div class="health-card-name">
        <strong>${esc(s.label)}</strong>
        <span class="health-ip">${esc(s.host)}</span>
        <span class="badge badge-secondary" style="font-size:.7rem">${esc(s.type)}</span>
      </div>
      <div class="health-card-meta">
        <div class="health-meta-item"><label>Status</label>
          <span>${_STATUS_LABEL[s.status] || esc(s.status)}</span></div>
        <div class="health-meta-item"><label>Hostname</label>
          <span>${esc(s.hostname || 'N/A')}</span></div>
        <div class="health-meta-item"><label>Version</label>
          <span>${esc(s.version || 'N/A')}</span></div>
        <div class="health-meta-item"><label>HA Role</label>
          <span>${esc(s.ha_role || 'N/A')}</span></div>
        ${s.cpu_pct != null
          ? `<div class="health-meta-item"><label>CPU</label><span>${esc(String(s.cpu_pct))}%</span></div>` : ''}
        ${s.mem_pct != null
          ? `<div class="health-meta-item"><label>MEM</label><span>${esc(String(s.mem_pct))}%</span></div>` : ''}
      </div>
    </div>`;
}

function _renderSection(title, servers) {
  if (!servers.length) return '';
  return `<div class="health-section">
    <h4 class="health-section-title">${esc(title)}</h4>
    ${servers.map(_renderHealthCard).join('')}
  </div>`;
}

async function loadHealth() {
  const r = await fetch('/api/dashboard/health');
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById('healthUpdated').textContent =
    data.last_updated ? 'Updated ' + data.last_updated : '';

  const all = data.servers || [];
  const mds = all.filter(s => s.type === 'MDS');
  const se  = all.filter(s => s.type === 'SmartEvent');
  const mls = all.filter(s => s.type === 'MLS');

  const container = document.getElementById('healthCards');
  container.innerHTML = [
    _renderSection('Provider-1 / MDS', mds),
    _renderSection('SmartEvent', se),
    _renderSection('Log Servers', mls),
  ].join('') ||
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
