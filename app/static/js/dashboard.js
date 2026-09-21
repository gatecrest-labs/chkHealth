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
  const hist = data.history || [];
  drawSparkline('gwChart',   hist.map(h => ({ date: h.date, value: h.gw_count })),   '#0d6efd');
  drawSparkline('ruleChart', hist.map(h => ({ date: h.date, value: h.rule_count })), '#198754');
}

document.getElementById('refreshSummaryBtn').addEventListener('click', async () => {
  const btn = document.getElementById('refreshSummaryBtn');
  btn.disabled = true;
  btn.textContent = '↺ Collecting…';

  // Capture the timestamp before the job runs so we can detect when it finishes
  let prevUpdated = document.getElementById('summaryUpdated').textContent;

  const resp = await fetch('/api/dashboard/refresh', { method: 'POST', headers: { 'X-CSRF-Token': CSRF } });
  if (!resp.ok) {
    btn.disabled = false;
    btn.textContent = '↺ Refresh Counts';
    return;
  }

  // Poll every 5s for up to 4 minutes waiting for the job to complete
  let polls = 0;
  const timer = setInterval(async () => {
    polls++;
    await loadSummary();
    const nowUpdated = document.getElementById('summaryUpdated').textContent;
    const done = polls >= 48 || (nowUpdated && nowUpdated !== prevUpdated);
    if (done) {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = '↺ Refresh Counts';
    }
  }, 5000);
});

// ── Sparkline (vanilla Canvas, interactive) ───────────────────────────────

// Shared tooltip div — created once, reused across all charts.
function _getTooltip() {
  let tip = document.getElementById('_sparkTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = '_sparkTip';
    Object.assign(tip.style, {
      position: 'fixed', pointerEvents: 'none', zIndex: '9999',
      background: '#1a1d23', color: '#e2e6ea',
      padding: '4px 10px', borderRadius: '4px',
      fontSize: '12px', whiteSpace: 'nowrap',
      boxShadow: '0 2px 8px rgba(0,0,0,.25)',
      display: 'none',
    });
    document.body.appendChild(tip);
  }
  return tip;
}

function _renderSparkline(canvas, points, color, hiIdx) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w   = canvas.offsetWidth  || canvas.parentElement.offsetWidth;
  const h   = canvas.offsetHeight || 80;
  canvas.width  = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  const LABEL_H = 18;   // x-axis label row height
  const PAD_X   = 6;
  const PAD_TOP = 6;
  const chartH  = h - LABEL_H;

  if (!points || points.length < 2) {
    ctx.fillStyle = '#ccc';
    ctx.font = '11px system-ui';
    ctx.textBaseline = 'middle';
    ctx.fillText('No data', PAD_X, chartH / 2);
    return;
  }

  const vals  = points.map(p => p.value);
  const min   = Math.min(...vals);
  const max   = Math.max(...vals);
  const range = max - min || 1;
  const xStep = (w - PAD_X * 2) / (points.length - 1);
  const yScale = (chartH - PAD_TOP - 8) / range;

  const pts = vals.map((v, i) => ({
    x: PAD_X + i * xStep,
    y: chartH - 8 - (v - min) * yScale,
  }));

  // Gradient fill
  ctx.beginPath();
  ctx.moveTo(pts[0].x, chartH - 4);
  ctx.lineTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length - 1].x, chartH - 4);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, chartH);
  grad.addColorStop(0, color + '40');
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
    const isHi = i === hiIdx;
    ctx.beginPath();
    ctx.arc(p.x, p.y, isHi ? 5 : 3.5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = isHi ? 2 : 1.5;
    ctx.stroke();
  });

  // X-axis date labels (MM-DD) at start, middle, end
  ctx.fillStyle = '#6c757d';
  ctx.font = '10px system-ui';
  ctx.textBaseline = 'top';
  const labelIdxs = [0, Math.round((points.length - 1) / 2), points.length - 1];
  labelIdxs.forEach((idx, pos) => {
    const raw = points[idx].date || '';            // "YYYY-MM-DD"
    const label = raw.length >= 7 ? raw.slice(5) : raw; // "MM-DD"
    ctx.textAlign = pos === 0 ? 'left' : pos === 2 ? 'right' : 'center';
    ctx.fillText(label, pts[idx].x, chartH + 3);
  });
}

function drawSparkline(canvasId, points, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  // Attach data for re-renders triggered by hover
  canvas._spData  = points;
  canvas._spColor = color;

  _renderSparkline(canvas, points, color, -1);

  canvas.onmousemove = (e) => {
    if (!canvas._spData || canvas._spData.length < 2) return;
    const rect  = canvas.getBoundingClientRect();
    const mx    = e.clientX - rect.left;
    const w     = canvas.offsetWidth || rect.width;
    const PAD_X = 6;
    const xStep = (w - PAD_X * 2) / (canvas._spData.length - 1);
    let hiIdx = 0, minDist = Infinity;
    canvas._spData.forEach((_, i) => {
      const dist = Math.abs(mx - (PAD_X + i * xStep));
      if (dist < minDist) { minDist = dist; hiIdx = i; }
    });

    if (minDist <= xStep / 2 + 6) {
      _renderSparkline(canvas, canvas._spData, canvas._spColor, hiIdx);
      const pt  = canvas._spData[hiIdx];
      const tip = _getTooltip();
      tip.textContent = `${pt.date}: ${pt.value.toLocaleString()}`;
      tip.style.display = 'block';
      tip.style.left = (e.clientX + 12) + 'px';
      tip.style.top  = (e.clientY - 30) + 'px';
    } else {
      _renderSparkline(canvas, canvas._spData, canvas._spColor, -1);
      _getTooltip().style.display = 'none';
    }
  };

  canvas.onmouseleave = () => {
    _renderSparkline(canvas, canvas._spData, canvas._spColor, -1);
    _getTooltip().style.display = 'none';
  };
}

// ── Health cards ──────────────────────────────────────────────────────────
function renderHealthCard(s) {
  const STATUS_LABEL = {
    healthy:     '&#9679; Healthy',
    unreachable: '&#9679; Unreachable',
    degraded:    '&#9679; Degraded',
    standby:     '&#9679; Standby (HA)',
    reachable:   '&#9679; Reachable',
  };
  const cls = s.status === 'healthy'   ? 'healthy'
            : s.status === 'degraded'  ? 'degraded'
            : s.status === 'standby'   ? 'standby'
            : s.status === 'reachable' ? 'reachable' : 'unhealthy';

  // Fields shown per type
  const showHaRole = s.type === 'MDS';
  const showCpu    = s.cpu_pct != null;
  const showMem    = s.mem_pct != null;

  return `
    <div class="health-card ${cls}">
      <div class="health-card-name">
        <strong>${esc(s.label)}</strong>
        <span class="health-ip">${esc(s.host)}</span>
      </div>
      <div class="health-card-meta">
        <div class="health-meta-item">
          <label>Status</label>
          <span>${STATUS_LABEL[s.status] || esc(s.status)}</span>
        </div>
        <div class="health-meta-item">
          <label>Hostname</label><span>${esc(s.hostname || 'N/A')}</span>
        </div>
        <div class="health-meta-item">
          <label>Version</label><span>${esc(s.version || 'N/A')}</span>
        </div>
        ${showHaRole
          ? `<div class="health-meta-item"><label>HA Role</label><span>${esc(s.ha_role || 'N/A')}</span></div>`
          : ''}
        ${showCpu
          ? `<div class="health-meta-item"><label>CPU</label><span>${esc(String(s.cpu_pct))}%</span></div>`
          : ''}
        ${showMem
          ? `<div class="health-meta-item"><label>MEM</label><span>${esc(String(s.mem_pct))}%</span></div>`
          : ''}
      </div>
    </div>`;
}

function renderSection(title, servers) {
  if (!servers.length) return '';
  return `<div class="health-section-title">${esc(title)}</div>`
    + servers.map(renderHealthCard).join('');
}

async function loadHealth() {
  const r = await fetch('/api/dashboard/health');
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById('healthUpdated').textContent =
    data.last_updated ? 'Updated ' + data.last_updated : '';

  const servers = data.servers || [];
  const mds = servers.filter(s => s.type === 'MDS');
  const se  = servers.filter(s => s.type === 'SmartEvent');
  const mls = servers.filter(s => s.type === 'MLS');

  const container = document.getElementById('healthCards');
  const html = renderSection('Provider-1 / MDS', mds)
             + renderSection('SmartEvent', se)
             + renderSection('Log Servers', mls);
  container.innerHTML = html ||
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
