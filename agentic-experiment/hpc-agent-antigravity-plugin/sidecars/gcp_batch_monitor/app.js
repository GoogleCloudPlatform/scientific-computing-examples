/**
 * Frontend logic for Google Cloud Batch Monitor Sidecar (`gcp_batch_monitor`)
 */

let currentTelemetry = null;
let selectedWindowDays = 30;
let selectedUserFilter = null;
let liveTickCounter = 0;

function apiFetch(url, options = {}) {
  if (window.sidecar && typeof window.sidecar.fetch === 'function') {
    return window.sidecar.fetch(url, options);
  }
  return fetch(url, options);
}

function showToast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => el.classList.add('hidden'), 3200);
}

async function sendToAgent(promptText) {
  try {
    if (window.sidecar?.agent?.sendMessage) {
      await window.sidecar.agent.sendMessage(promptText);
      showToast('Sent request to HPC Agent in chat');
    } else {
      showToast('Agent bridge ready (open inside Antigravity AuxPane to message chat)');
    }
  } catch (err) {
    showToast(`Failed to send to agent: ${err.message}`);
  }
}

function fmtNum(n) {
  return Number(n || 0).toLocaleString('en-US');
}

function fmtDurationSec(totalSeconds) {
  const sec = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (v) => String(v).padStart(2, '0');
  return `${pad(h)}h ${pad(m)}m ${pad(s)}s`;
}

async function loadTelemetry(forceRefresh = false) {
  try {
    const res = await apiFetch(
      `/api/telemetry?days=${selectedWindowDays}&refresh=${forceRefresh ? '1' : '0'}`
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    currentTelemetry = await res.json();
    liveTickCounter = 0;
    renderAll();
    if (forceRefresh) showToast('Google Cloud Batch telemetry synchronized');
  } catch (err) {
    console.error('[gcp_batch_monitor] loadTelemetry failed:', err);
    showToast(`Error loading Batch telemetry: ${err.message}`);
  }
}

function renderAll() {
  if (!currentTelemetry) return;
  const { config, sourceBadge, summary30d, windowStats, windowDays } = currentTelemetry;

  document.getElementById('badge-source').textContent = sourceBadge;
  document.getElementById('badge-project').textContent = `Project: ${config.projectId}`;
  document.getElementById('badge-region').textContent = `Region: ${config.region}`;

  document.getElementById('cfg-project').value = config.projectId || '';
  document.getElementById('cfg-region').value = config.region || '';
  document.getElementById('cfg-mode').value = config.dataMode || 'auto';

  // KPIs
  document.getElementById('kpi-nodes-now').textContent = `${summary30d.nodesInUseNow} Nodes`;
  document.getElementById('kpi-nodes-spot-sub').textContent =
    `${summary30d.spotNodesNow} Spot (${summary30d.spotRatioPct}%) · ${summary30d.standardNodesNow} Std`;

  document.getElementById('kpi-window-nodes-label').textContent = `${windowDays}-Day Node Usage`;
  document.getElementById('kpi-peak-avg-nodes').textContent =
    `${windowStats.peakNodes} peak / ${windowStats.avgNodes} avg`;
  document.getElementById('kpi-node-hours-30d').textContent =
    `${fmtNum(windowStats.nodeHours)} node-hrs (${windowDays}d)`;

  document.getElementById('kpi-active-jobs').textContent = `${summary30d.runningJobsNow} Running`;
  document.getElementById('kpi-queued-jobs').textContent =
    `${summary30d.queuedJobsNow} queued · ${fmtNum(summary30d.vcpusInUseNow)} vCPUs`;

  document.getElementById('kpi-avg-duration').textContent = `Avg ${summary30d.avgJobDurationFormatted}`;
  document.getElementById('kpi-max-duration').textContent =
    `P95: ${summary30d.p95JobDurationFormatted} · Max: ${summary30d.maxJobDurationFormatted}`;

  document.getElementById('kpi-users-now').textContent =
    `${summary30d.activeUsersNow} Active / ${summary30d.totalUsers30d}`;
  document.getElementById('kpi-runtime-hours-30d').textContent =
    `${fmtNum(windowStats.runtimeHours)} cumulative job-hrs (${windowDays}d)`;

  document.getElementById('kpi-jobs-30d').textContent = `${fmtNum(windowStats.totalJobs)} Jobs`;
  document.getElementById('kpi-success-rate').textContent =
    `${summary30d.jobSuccessRate30dPct}% ok · ${summary30d.totalSpotPreemptions30d} Spot retries`;

  document.getElementById('chart-days-title').textContent = `Last ${windowDays} Days`;

  renderBatchUsersTable();
  renderBatchJobsTable();
  renderBatchNodesChart();
  renderNodePoolsTable();
  renderDurationBuckets();
  renderDurationTrendChart();
}

// ---------------------------------------------------------------------------
// People Running Batch & Duration Leaderboard
// ---------------------------------------------------------------------------

function renderBatchUsersTable() {
  const tbody = document.getElementById('batch-users-tbody');
  const clearBtn = document.getElementById('btn-clear-user-filter');
  if (!tbody || !currentTelemetry) return;

  if (clearBtn) {
    clearBtn.classList.toggle('hidden', !selectedUserFilter);
  }

  tbody.innerHTML = (currentTelemetry.batchUsers || [])
    .map((u) => {
      const isSelected = selectedUserFilter === u.user;
      const liveUserSec = u.activeJobsNow > 0 ? u.activeDurationSeconds + liveTickCounter : 0;
      const liveDurStr = u.activeJobsNow > 0 ? fmtDurationSec(liveUserSec) : 'Idle (00h 00m)';

      return `
        <tr class="clickable-row" data-user="${u.user}" style="${isSelected ? 'outline: 1px solid #3b82f6;' : ''}">
          <td>
            <strong>${u.user}</strong>
            <div class="card-subtitle">${u.displayName}</div>
          </td>
          <td>
            <div>${u.team}</div>
            <div class="card-subtitle"><code>${u.primaryPipeline}</code></div>
          </td>
          <td>
            ${
              u.activeJobsNow > 0
                ? `<span class="state-badge state-RUNNING">${u.activeJobsNow} running</span>`
                : `<span class="card-subtitle">0 active</span>`
            }
          </td>
          <td><strong>${u.nodesInUseNow} nodes</strong></td>
          <td>
            <span class="duration-mono live-user-dur" data-base="${u.activeDurationSeconds}" data-active="${u.activeJobsNow}">
              ${liveDurStr}
            </span>
          </td>
          <td><strong>${u.avgJobDuration}</strong></td>
          <td>
            <strong>${u.longestJobDuration}</strong>
            <div class="card-subtitle"><code>${u.longestJobName}</code></div>
          </td>
          <td><strong>${fmtNum(u.totalJobDurationHours30d)} hrs</strong> (${fmtNum(u.jobs30d)} jobs)</td>
          <td>${fmtNum(u.totalNodeHours30d)} node-hrs</td>
          <td><span class="prov-SPOT">${u.spotSharePct}% Spot</span></td>
        </tr>
      `;
    })
    .join('');

  tbody.querySelectorAll('tr.clickable-row').forEach((row) => {
    row.addEventListener('click', () => {
      const usr = row.getAttribute('data-user');
      selectedUserFilter = selectedUserFilter === usr ? null : usr;
      renderBatchUsersTable();
      renderBatchJobsTable();
    });
  });
}

// ---------------------------------------------------------------------------
// Active & 30-Day Batch Jobs + Live Duration Table
// ---------------------------------------------------------------------------

function renderBatchJobsTable() {
  const tbody = document.getElementById('batch-jobs-tbody');
  if (!tbody || !currentTelemetry) return;

  const query = (document.getElementById('job-search-input')?.value || '').toLowerCase().trim();
  const stateFilter = document.getElementById('job-state-filter')?.value || 'ALL';
  const provFilter = document.getElementById('job-prov-filter')?.value || 'ALL';

  const filtered = (currentTelemetry.jobs || []).filter((j) => {
    if (selectedUserFilter && j.user !== selectedUserFilter) return false;
    if (stateFilter !== 'ALL' && j.state !== stateFilter) return false;
    if (provFilter !== 'ALL' && j.provisioning !== provFilter) return false;
    if (query) {
      const hay = `${j.jobId} ${j.pipeline} ${j.processName} ${j.user} ${j.machineType}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });

  tbody.innerHTML = filtered
    .map((j) => {
      const isRunning = j.state === 'RUNNING';
      const curSec = isRunning ? j.durationSeconds + liveTickCounter : j.durationSeconds;
      const curDurText = isRunning ? fmtDurationSec(curSec) : j.durationFormatted;
      const pct = Math.min(100, Number(((curSec / Math.max(1, j.maxDurationSeconds)) * 100).toFixed(1)));
      const barColor =
        j.state === 'FAILED'
          ? '#ef4444'
          : pct > 78
          ? '#f59e0b'
          : j.state === 'SUCCEEDED'
          ? '#3b82f6'
          : '#22c55e';

      return `
        <tr>
          <td>
            <strong><code>${j.jobId}</code></strong>
            <div class="card-subtitle">${j.processName}</div>
          </td>
          <td>${j.pipeline}</td>
          <td><strong>${j.user}</strong><div class="card-subtitle">${j.submittedAgo}</div></td>
          <td><span class="state-badge state-${j.state}">${j.state}</span></td>
          <td>
            <strong>${j.nodesInUse > 0 ? `${j.nodesInUse}× ` : ''}${j.machineType}</strong>
            <span class="prov-${j.provisioning}">${j.provisioning}</span>
          </td>
          <td>${j.tasksCompleted}/${j.tasksTotal}</td>
          <td>
            <div class="duration-mono live-job-dur" data-base="${j.durationSeconds}" data-running="${isRunning ? '1' : '0'}">
              ${curDurText}
            </div>
            <div class="card-subtitle">Limit: ${j.maxDurationFormatted}</div>
          </td>
          <td>
            <div style="display:flex;align-items:center;gap:6px;">
              <div class="progress-track">
                <div class="progress-fill" style="width:${pct}%; background:${barColor}"></div>
              </div>
              <span>${pct}%</span>
            </div>
          </td>
          <td><span class="card-subtitle">30d avg:</span><br/><strong>${j.avg30dDurationFormatted}</strong></td>
          <td>
            <button class="btn btn-secondary btn-xs job-action-btn"
              data-job="${j.jobId}"
              data-proc="${j.processName}"
              data-user="${j.user}"
              data-dur="${curDurText}"
              data-mt="${j.machineType}">
              Optimize
            </button>
          </td>
        </tr>
      `;
    })
    .join('');

  tbody.querySelectorAll('.job-action-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const job = btn.getAttribute('data-job');
      const proc = btn.getAttribute('data-proc');
      const user = btn.getAttribute('data-user');
      const dur = btn.getAttribute('data-dur');
      const mt = btn.getAttribute('data-mt');
      sendToAgent(
        `Analyze Google Cloud Batch job "${job}" (process: ${proc}, user: ${user}, machine: ${mt}, current duration: ${dur}) and suggest Nextflow/Batch hardware tier and Spot/disk optimizations.`
      );
    });
  });
}

// ---------------------------------------------------------------------------
// 30-Day Batch Nodes in Use SVG Chart & Node Pools
// ---------------------------------------------------------------------------

function renderBatchNodesChart() {
  const svg = document.getElementById('batch-nodes-svg');
  const tooltip = document.getElementById('batch-nodes-tooltip');
  if (!svg || !currentTelemetry) return;

  const series = currentTelemetry.dailySeries || [];
  const mode = document.getElementById('nodes-chart-mode')?.value || 'spot_std';
  const W = 780;
  const H = 210;
  const padL = 40;
  const padR = 14;
  const padT = 14;
  const padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxVal =
    mode === 'runtime'
      ? Math.max(50, ...series.map((d) => d.totalJobRuntimeHours))
      : mode === 'jobs'
      ? Math.max(20, ...series.map((d) => d.jobsSucceeded + d.jobsFailed))
      : Math.max(20, ...series.map((d) => d.peakNodes));

  const barStep = plotW / Math.max(1, series.length);
  const barW = Math.max(6, barStep * 0.66);

  let html = '';

  for (let i = 0; i <= 4; i++) {
    const val = Math.round((maxVal * i) / 4);
    const y = padT + plotH - (plotH * i) / 4;
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="rgba(148,163,184,0.16)" stroke-dasharray="3,3" />`;
    html += `<text x="${padL - 6}" y="${y + 4}" text-anchor="end" fill="#94a3b8" font-size="10">${val}</text>`;
  }

  series.forEach((d, idx) => {
    const x = padL + idx * barStep + (barStep - barW) / 2;

    if (mode === 'spot_std') {
      const hPeak = (d.peakNodes / maxVal) * plotH;
      const yPeak = padT + plotH - hPeak;
      const hSpot = (d.spotNodesAvg / maxVal) * plotH;
      const hStd = (d.standardNodesAvg / maxVal) * plotH;
      const yStd = padT + plotH - hStd;
      const ySpot = yStd - hSpot;

      html += `<rect class="batch-day-bar" data-idx="${idx}" x="${x}" y="${yPeak}" width="${barW}" height="${hPeak}" rx="2" fill="rgba(147,197,253,0.28)" />`;
      html += `<rect class="batch-day-bar" data-idx="${idx}" x="${x}" y="${yStd}" width="${barW}" height="${hStd}" fill="#6366f1" />`;
      html += `<rect class="batch-day-bar" data-idx="${idx}" x="${x}" y="${ySpot}" width="${barW}" height="${hSpot}" rx="2" fill="#14b8a6" />`;
    } else if (mode === 'runtime') {
      const hRun = (d.totalJobRuntimeHours / maxVal) * plotH;
      const yRun = padT + plotH - hRun;
      html += `<rect class="batch-day-bar" data-idx="${idx}" x="${x}" y="${yRun}" width="${barW}" height="${hRun}" rx="2" fill="#3b82f6" />`;
    } else {
      const hJobs = ((d.jobsSucceeded + d.jobsFailed) / maxVal) * plotH;
      const yJobs = padT + plotH - hJobs;
      html += `<rect class="batch-day-bar" data-idx="${idx}" x="${x}" y="${yJobs}" width="${barW}" height="${hJobs}" rx="2" fill="#22c55e" />`;
    }

    if (idx % Math.max(1, Math.floor(series.length / 7)) === 0 || idx === series.length - 1) {
      html += `<text x="${x + barW / 2}" y="${H - 8}" text-anchor="middle" fill="#94a3b8" font-size="10">${d.label}</text>`;
    }
  });

  svg.innerHTML = html;

  svg.querySelectorAll('.batch-day-bar').forEach((el) => {
    el.addEventListener('mouseenter', () => {
      const d = series[Number(el.getAttribute('data-idx'))];
      if (!d || !tooltip) return;
      tooltip.innerHTML = `
        <span><strong>${d.label} (${d.date})</strong></span>
        <span>Avg Batch Nodes: <strong>${d.avgNodes}</strong> (${d.spotNodesAvg} Spot / ${d.standardNodesAvg} Std) · Peak: <strong>${d.peakNodes} nodes</strong></span>
        <span>Jobs: <strong>${d.jobsSucceeded} succeeded</strong> (${d.jobsFailed} failed)</span>
        <span>Avg Duration: <strong>${Math.floor(d.avgJobDurationMin / 60)}h ${d.avgJobDurationMin % 60}m</strong> · Total Runtime: <strong>${fmtNum(d.totalJobRuntimeHours)} hrs</strong></span>
      `;
    });
  });
}

function renderNodePoolsTable() {
  const tbody = document.getElementById('node-pools-tbody');
  if (!tbody || !currentTelemetry) return;

  tbody.innerHTML = (currentTelemetry.nodePools || [])
    .map(
      (p) => `
      <tr>
        <td><strong><code>${p.machineType}</code></strong></td>
        <td>${p.tier}</td>
        <td><span class="prov-${p.provisioning}">${p.provisioning}</span></td>
        <td><strong>${p.nodesInUseNow} nodes</strong></td>
        <td>${fmtNum(p.vcpusInUse)} vCPUs · ${fmtNum(p.memoryGiBInUse)} GiB</td>
        <td><code>${p.diskType}</code></td>
        <td><span class="duration-mono">${p.avgNodeDuration}</span></td>
        <td><strong>${fmtNum(p.nodeHours30d)} node-hrs</strong></td>
        <td>${fmtNum(p.jobsServed30d)} jobs</td>
        <td>${p.primaryWorkloads}</td>
      </tr>
    `
    )
    .join('');
}

// ---------------------------------------------------------------------------
// 30-Day Duration Distribution & Trend
// ---------------------------------------------------------------------------

function renderDurationBuckets() {
  const grid = document.getElementById('duration-buckets-grid');
  if (!grid || !currentTelemetry) return;

  grid.innerHTML = (currentTelemetry.durationBuckets30d || [])
    .map(
      (b) => `
      <div class="bucket-card">
        <div style="display:flex; justify-content:space-between; align-items:baseline;">
          <strong style="font-size:13.5px;">${b.label}</strong>
          <span class="pill-badge">${b.pct}%</span>
        </div>
        <div style="font-size:18px; font-weight:700; margin:4px 0;">
          ${fmtNum(b.count)} <span style="font-size:11.5px; font-weight:400; color:var(--muted-foreground,#94a3b8);">jobs (30d)</span>
        </div>
        <div class="progress-track" style="margin:6px 0;">
          <div class="progress-fill" style="width:${Math.min(100, b.pct * 2.5)}%"></div>
        </div>
        <div class="card-subtitle">${b.tierHint}</div>
      </div>
    `
    )
    .join('');
}

function renderDurationTrendChart() {
  const svg = document.getElementById('duration-trend-svg');
  if (!svg || !currentTelemetry) return;

  const series = currentTelemetry.dailySeries || [];
  const W = 780;
  const H = 190;
  const padL = 40;
  const padR = 14;
  const padT = 14;
  const padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxMin = Math.max(300, ...series.map((d) => d.maxJobDurationMin));
  const stepX = plotW / Math.max(1, series.length - 1);

  const buildPath = (getter) =>
    series
      .map((d, i) => {
        const x = padL + i * stepX;
        const y = padT + plotH - (getter(d) / maxMin) * plotH;
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');

  let html = '';
  for (let i = 0; i <= 3; i++) {
    const val = Math.round((maxMin * i) / 3);
    const y = padT + plotH - (plotH * i) / 3;
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="rgba(148,163,184,0.15)" stroke-dasharray="3,3" />`;
    html += `<text x="${padL - 6}" y="${y + 4}" text-anchor="end" fill="#94a3b8" font-size="10">${val}m</text>`;
  }

  html += `<path d="${buildPath((d) => d.avgJobDurationMin)}" fill="none" stroke="#3b82f6" stroke-width="2.4" />`;
  html += `<path d="${buildPath((d) => d.maxJobDurationMin)}" fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="4,3" />`;

  series.forEach((d, idx) => {
    if (idx % Math.max(1, Math.floor(series.length / 7)) === 0 || idx === series.length - 1) {
      const x = padL + idx * stepX;
      html += `<text x="${x}" y="${H - 7}" text-anchor="middle" fill="#94a3b8" font-size="10">${d.label}</text>`;
    }
  });

  svg.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Live 1-Second Duration Ticker + Event Wiring
// ---------------------------------------------------------------------------

setInterval(() => {
  liveTickCounter += 1;
  document.querySelectorAll('.live-job-dur[data-running="1"]').forEach((el) => {
    const base = Number(el.getAttribute('data-base')) || 0;
    el.textContent = fmtDurationSec(base + liveTickCounter);
  });
  document.querySelectorAll('.live-user-dur').forEach((el) => {
    const active = Number(el.getAttribute('data-active')) || 0;
    if (active > 0) {
      const base = Number(el.getAttribute('data-base')) || 0;
      el.textContent = fmtDurationSec(base + liveTickCounter);
    }
  });
}, 1000);

document.addEventListener('DOMContentLoaded', () => {
  // Tabs
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      const pane = document.getElementById(btn.getAttribute('data-tab'));
      if (pane) pane.classList.add('active');
    });
  });

  // Window buttons (7d / 14d / 30d)
  document.querySelectorAll('.window-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.window-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      selectedWindowDays = Number(btn.getAttribute('data-days')) || 30;
      loadTelemetry(false);
    });
  });

  document.getElementById('nodes-chart-mode')?.addEventListener('change', renderBatchNodesChart);
  document.getElementById('job-search-input')?.addEventListener('input', renderBatchJobsTable);
  document.getElementById('job-state-filter')?.addEventListener('change', renderBatchJobsTable);
  document.getElementById('job-prov-filter')?.addEventListener('change', renderBatchJobsTable);
  document.getElementById('btn-clear-user-filter')?.addEventListener('click', () => {
    selectedUserFilter = null;
    renderBatchUsersTable();
    renderBatchJobsTable();
  });

  // Config drawer
  const drawer = document.getElementById('config-drawer');
  document.getElementById('btn-toggle-config')?.addEventListener('click', () => {
    drawer?.classList.toggle('hidden');
  });
  document.getElementById('btn-cancel-config')?.addEventListener('click', () => {
    drawer?.classList.add('hidden');
  });
  document.getElementById('btn-save-config')?.addEventListener('click', async () => {
    const payload = {
      projectId: document.getElementById('cfg-project').value,
      region: document.getElementById('cfg-region').value,
      dataMode: document.getElementById('cfg-mode').value,
      days: selectedWindowDays,
    };
    const res = await apiFetch('/api/config', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      currentTelemetry = await res.json();
      liveTickCounter = 0;
      renderAll();
      drawer?.classList.add('hidden');
      showToast('Batch configuration saved');
    }
  });

  document.getElementById('btn-sync')?.addEventListener('click', () => loadTelemetry(true));

  document.getElementById('btn-optimize-batch')?.addEventListener('click', () => {
    if (!currentTelemetry) return;
    const s = currentTelemetry.summary30d;
    sendToAgent(
      `Review our 30-day Google Cloud Batch telemetry in project ${currentTelemetry.config.projectId} (${currentTelemetry.config.region}): ` +
        `${s.nodesInUseNow} Batch nodes currently in use (${s.spotNodesNow} Spot / ${s.standardNodesNow} Standard, 30d total: ${s.totalNodeHours30d} node-hrs across ${s.totalJobs30d} jobs), ` +
        `mean job duration ${s.avgJobDurationFormatted} (P95: ${s.p95JobDurationFormatted}, Max: ${s.maxJobDurationFormatted} by ${s.longestJobUser}). ` +
        `Use the nextflow-batch-optimizer skill to recommend process tiering and Spot preemption mitigation.`
    );
  });

  loadTelemetry(false);
});

