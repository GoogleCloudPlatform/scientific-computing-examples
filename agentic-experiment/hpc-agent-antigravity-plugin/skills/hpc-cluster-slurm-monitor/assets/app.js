/**
 * Frontend logic for HPC Cluster & Slurm Monitor Sidecar (`hpc_cluster_monitor`)
 */

let currentTelemetry = null;
let selectedWindowDays = 30;
let selectedUserFilter = null;

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

async function loadTelemetry(forceRefresh = false) {
  try {
    const res = await apiFetch(
      `/api/telemetry?days=${selectedWindowDays}&refresh=${forceRefresh ? '1' : '0'}`
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    currentTelemetry = await res.json();
    renderAll();
    if (forceRefresh) showToast('Telemetry synchronized');
  } catch (err) {
    console.error('[hpc_cluster_monitor] loadTelemetry failed:', err);
    showToast(`Error loading telemetry: ${err.message}`);
  }
}

function renderAll() {
  if (!currentTelemetry) return;
  const { config, sourceBadge, summary30d, windowStats, windowDays } = currentTelemetry;

  // Header badges
  document.getElementById('badge-source').textContent = sourceBadge;
  document.getElementById('badge-project').textContent = `Project: ${config.projectId}`;
  document.getElementById('badge-region').textContent = `Region: ${config.region}`;
  document.getElementById('badge-cluster').textContent = `Slurm: ${config.loginNode}`;

  // Config inputs
  document.getElementById('cfg-project').value = config.projectId || '';
  document.getElementById('cfg-region').value = config.region || '';
  document.getElementById('cfg-login').value = config.loginNode || '';
  const zoneEl = document.getElementById('cfg-zone');
  if (zoneEl) zoneEl.value = config.zone || '';

  // KPIs
  document.getElementById('kpi-running-instances').textContent =
    `${summary30d.currentRunningInstances} / ${summary30d.totalClusterNodes}`;
  document.getElementById('kpi-running-sub').textContent =
    `${summary30d.allocatedNodes} allocated · ${summary30d.idleNodes} idle · ${summary30d.downNodes} down`;

  document.getElementById('kpi-window-label').textContent = `${windowDays}-Day Instance Stats`;
  document.getElementById('kpi-peak-avg').textContent =
    `${windowStats.peakInstances} peak / ${windowStats.avgInstances} avg`;
  document.getElementById('kpi-instance-hours').textContent =
    `${fmtNum(windowStats.instanceHours)} instance-hrs (${windowDays}d)`;

  document.getElementById('kpi-active-jobs').textContent =
    `${summary30d.runningJobsNow} Running`;
  document.getElementById('kpi-active-users').textContent =
    `${summary30d.pendingJobsNow} pending · ${summary30d.activeUsersNow} active users`;

  document.getElementById('kpi-jobs-30d').textContent =
    `${fmtNum(windowStats.jobsCompleted)} Jobs`;
  document.getElementById('kpi-core-hours-30d').textContent =
    `${fmtNum(Math.round(windowStats.coreHours / 1000))}k core-hrs · ${summary30d.jobSuccessRate30dPct}% ok`;

  document.getElementById('kpi-storage-used').textContent =
    `${summary30d.totalStorageUsedTiB} / ${summary30d.totalStorageCapacityTiB} TiB`;
  document.getElementById('kpi-storage-throughput').textContent =
    `${summary30d.storageUsedPct}% used · ${summary30d.aggregateThroughputGBps} GB/s live I/O`;

  document.getElementById('kpi-utilization-30d').textContent =
    `${summary30d.avgClusterUtilization30dPct}%`;

  document.getElementById('chart-days-title').textContent = `Last ${windowDays} Days`;

  renderInstancesChart();
  renderPartitionsTable();
  renderUsersTable();
  renderJobsTable();
  renderStorageSection();
  renderStorageChart();
}

// ---------------------------------------------------------------------------
// 30-Day Running Instances SVG Chart
// ---------------------------------------------------------------------------

function renderInstancesChart() {
  const svg = document.getElementById('instances-chart-svg');
  const tooltip = document.getElementById('instances-chart-tooltip');
  if (!svg || !currentTelemetry) return;

  const series = currentTelemetry.dailySeries || [];
  const metricMode = document.getElementById('chart-metric-select')?.value || 'instances';
  const W = 780;
  const H = 210;
  const padL = 38;
  const padR = 14;
  const padT = 14;
  const padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxVal =
    metricMode === 'jobs'
      ? Math.max(10, ...series.map((d) => d.jobsCompleted + d.jobsFailed))
      : Math.max(10, ...series.map((d) => d.peakInstances));

  const barStep = plotW / Math.max(1, series.length);
  const barW = Math.max(6, barStep * 0.66);

  let html = '';

  // Horizontal grid lines
  for (let i = 0; i <= 4; i++) {
    const val = Math.round((maxVal * i) / 4);
    const y = padT + plotH - (plotH * i) / 4;
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="rgba(148,163,184,0.16)" stroke-dasharray="3,3" />`;
    html += `<text x="${padL - 6}" y="${y + 4}" text-anchor="end" fill="#94a3b8" font-size="10">${val}</text>`;
  }

  // Bars
  series.forEach((d, idx) => {
    const x = padL + idx * barStep + (barStep - barW) / 2;

    if (metricMode === 'instances') {
      const hPeak = (d.peakInstances / maxVal) * plotH;
      const yPeak = padT + plotH - hPeak;
      const hAvg = (d.avgInstances / maxVal) * plotH;
      const yAvg = padT + plotH - hAvg;

      // Peak bar (light blue translucent)
      html += `<rect class="day-bar" data-idx="${idx}" x="${x}" y="${yPeak}" width="${barW}" height="${hPeak}" rx="2" fill="rgba(147, 197, 253, 0.32)" />`;
      // Avg bar (solid primary blue)
      html += `<rect class="day-bar" data-idx="${idx}" x="${x}" y="${yAvg}" width="${barW}" height="${hAvg}" rx="2" fill="#3b82f6" />`;
    } else if (metricMode === 'families') {
      const f = d.families || {};
      const segments = [
        { val: f.H4D || 0, color: '#8b5cf6' },
        { val: (f.C4 || 0) + (f.C3 || 0), color: '#14b8a6' },
        { val: f.A3_GPU || 0, color: '#f59e0b' },
        { val: f.N4 || 0, color: '#64748b' },
      ];
      let curBottom = padT + plotH;
      segments.forEach((seg) => {
        const segH = (seg.val / maxVal) * plotH;
        curBottom -= segH;
        html += `<rect class="day-bar" data-idx="${idx}" x="${x}" y="${curBottom}" width="${barW}" height="${Math.max(0, segH)}" fill="${seg.color}" />`;
      });
    } else {
      const hOk = (d.jobsCompleted / maxVal) * plotH;
      const yOk = padT + plotH - hOk;
      html += `<rect class="day-bar" data-idx="${idx}" x="${x}" y="${yOk}" width="${barW}" height="${hOk}" rx="2" fill="#22c55e" />`;
    }

    // X-axis date labels every ~4 days
    if (idx % Math.max(1, Math.floor(series.length / 7)) === 0 || idx === series.length - 1) {
      html += `<text x="${x + barW / 2}" y="${H - 8}" text-anchor="middle" fill="#94a3b8" font-size="10">${d.label}</text>`;
    }
  });

  svg.innerHTML = html;

  svg.querySelectorAll('.day-bar').forEach((el) => {
    el.addEventListener('mouseenter', () => {
      const d = series[Number(el.getAttribute('data-idx'))];
      if (!d || !tooltip) return;
      tooltip.innerHTML = `
        <span><strong>${d.label} (${d.date})</strong></span>
        <span>Avg Running: <strong>${d.avgInstances} VMs</strong> · Peak: <strong>${d.peakInstances} VMs</strong> (${fmtNum(d.instanceHours)} VM-hrs)</span>
        <span>Families: H4D=${d.families.H4D}, C4=${d.families.C4}, C3=${d.families.C3}, A3-GPU=${d.families.A3_GPU}</span>
        <span>Slurm Jobs: <strong>${d.jobsCompleted} completed</strong> (${d.jobsFailed} failed)</span>
      `;
    });
  });
}

// ---------------------------------------------------------------------------
// Slurm Partitions Table
// ---------------------------------------------------------------------------

function renderPartitionsTable() {
  const tbody = document.getElementById('partitions-tbody');
  if (!tbody || !currentTelemetry) return;

  const list = currentTelemetry.partitions || [];
  if (list.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" style="text-align:center; padding:18px; color:#94a3b8;">
          Live GCP &amp; Slurm query completed for project <code>${currentTelemetry.config.projectId}</code> at <code>${currentTelemetry.generatedAt}</code>: <strong>0 active Slurm partitions or GCE instances found</strong>.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = list
    .map((p) => {
      const running = p.allocatedNodes + p.mixedNodes;
      return `
        <tr>
          <td><strong>${p.name}</strong></td>
          <td><code>${p.machineType}</code></td>
          <td>${p.provisioning}</td>
          <td><span class="state-badge state-ALLOCATED">${running} Running</span> (${p.allocatedNodes}a/${p.mixedNodes}m)</td>
          <td><span class="state-badge state-IDLE">${p.idleNodes} Idle</span></td>
          <td>${p.downNodes > 0 ? `<span class="state-badge state-DOWN">${p.downNodes} Down</span>` : '0'}</td>
          <td>${p.totalNodes} (${p.totalNodes * p.cpusPerNode} vCPUs${p.gpusPerNode ? `, ${p.totalNodes * p.gpusPerNode} GPUs` : ''})</td>
          <td>${p.interconnect}</td>
          <td>
            <div style="display:flex;align-items:center;gap:6px;">
              <div class="progress-track"><div class="progress-fill" style="width:${p.utilization30dPct}%"></div></div>
              <span>${p.utilization30dPct}%</span>
            </div>
          </td>
          <td>
            <button class="btn btn-secondary btn-xs partition-check-btn" data-machine="${p.machineType}" data-part="${p.name}">
              Check Capacity
            </button>
          </td>
        </tr>
      `;
    })
    .join('');

  tbody.querySelectorAll('.partition-check-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const machine = btn.getAttribute('data-machine');
      const part = btn.getAttribute('data-part');
      sendToAgent(
        `Please check VM availability and compute quota for Slurm partition "${part}" (${machine}) in ${currentTelemetry.config.region}.`
      );
    });
  });
}

// ---------------------------------------------------------------------------
// Slurm Users & Active Jobs Queue
// ---------------------------------------------------------------------------

function renderUsersTable() {
  const tbody = document.getElementById('users-tbody');
  const clearBtn = document.getElementById('btn-clear-user-filter');
  if (!tbody || !currentTelemetry) return;

  if (clearBtn) {
    clearBtn.classList.toggle('hidden', !selectedUserFilter);
  }

  const users = currentTelemetry.slurmUsers || [];
  if (users.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align:center; padding:18px; color:#94a3b8;">
          Live Slurm query (<code>squeue</code> / <code>sacct</code>) completed for <code>${currentTelemetry.config.projectId}</code>: <strong>0 active or 30-day Slurm user jobs found</strong>.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = users
    .map((u) => {
      const isSelected = selectedUserFilter === u.user;
      return `
        <tr class="clickable-row" data-user="${u.user}" style="${isSelected ? 'outline: 1px solid #3b82f6;' : ''}">
          <td><strong>${u.user}</strong><div class="card-subtitle">${u.fullName}</div></td>
          <td>${u.team}</td>
          <td><span class="state-badge state-RUNNING">${u.runningJobs} running</span></td>
          <td>${u.pendingJobs > 0 ? `<span class="state-badge state-PENDING">${u.pendingJobs} queued</span>` : '0'}</td>
          <td><strong>${u.nodesInUse} nodes</strong> (${fmtNum(u.cpusInUse)} cores)</td>
          <td>${u.gpusInUse > 0 ? `<strong>${u.gpusInUse} H100</strong>` : '-'}</td>
          <td>${fmtNum(u.jobs30d)}</td>
          <td>${fmtNum(u.coreHours30d)} hrs</td>
          <td>${u.avgJobDuration}</td>
          <td><code>${u.primaryStorage}</code></td>
          <td>
            <div style="display:flex;align-items:center;gap:6px;">
              <div class="progress-track"><div class="progress-fill" style="width:${u.share30dPct}%"></div></div>
              <span>${u.share30dPct}%</span>
            </div>
          </td>
        </tr>
      `;
    })
    .join('');

  tbody.querySelectorAll('tr.clickable-row').forEach((row) => {
    row.addEventListener('click', () => {
      const usr = row.getAttribute('data-user');
      selectedUserFilter = selectedUserFilter === usr ? null : usr;
      renderUsersTable();
      renderJobsTable();
    });
  });
}

function renderJobsTable() {
  const tbody = document.getElementById('jobs-tbody');
  if (!tbody || !currentTelemetry) return;

  const query = (document.getElementById('job-search-input')?.value || '').toLowerCase().trim();
  const stateFilter = document.getElementById('job-state-filter')?.value || 'ALL';
  const partFilter = document.getElementById('job-partition-filter')?.value || 'ALL';

  const filtered = (currentTelemetry.activeJobs || []).filter((j) => {
    if (selectedUserFilter && j.user !== selectedUserFilter) return false;
    if (stateFilter !== 'ALL' && j.state !== stateFilter) return false;
    if (partFilter !== 'ALL' && j.partition !== partFilter) return false;
    if (query) {
      const hay = `${j.jobId} ${j.name} ${j.user} ${j.partition} ${j.storageMount}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align:center; padding:18px; color:#94a3b8;">
          Live Slurm <code>squeue</code> query completed: <strong>0 active or queued Slurm jobs right now</strong>.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered
    .map(
      (j) => `
      <tr>
        <td><code>#${j.jobId}</code></td>
        <td><strong>${j.name}</strong></td>
        <td><strong>${j.user}</strong></td>
        <td><code>${j.partition}</code></td>
        <td><span class="state-badge state-${j.state}">${j.state}</span></td>
        <td>${j.nodes}N / ${j.cpus}C${j.gpus ? ` / ${j.gpus}G` : ''}</td>
        <td><strong>${j.elapsed}</strong> <span class="card-subtitle">/ ${j.timeLimit}</span></td>
        <td><span class="mount-tag">${j.storageMount}</span></td>
        <td>${j.ioRateMBps > 0 ? `${fmtNum(j.ioRateMBps)} MB/s` : '-'}</td>
        <td><code>${j.nodelist}</code></td>
        <td>
          <button class="btn btn-secondary btn-xs inspect-job-btn" data-jobid="${j.jobId}" data-jobname="${j.name}" data-user="${j.user}">
            Inspect
          </button>
        </td>
      </tr>
    `
    )
    .join('');

  tbody.querySelectorAll('.inspect-job-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const jobId = btn.getAttribute('data-jobid');
      const jobName = btn.getAttribute('data-jobname');
      const user = btn.getAttribute('data-user');
      sendToAgent(
        `Inspect Slurm job #${jobId} (${jobName}) submitted by user ${user} on login node ${currentTelemetry.config.loginNode}.`
      );
    });
  });
}

// ---------------------------------------------------------------------------
// Storage Systems Section & 30d Storage Chart
// ---------------------------------------------------------------------------

function renderStorageSection() {
  const grid = document.getElementById('storage-cards-grid');
  if (!grid || !currentTelemetry) return;

  const systems = currentTelemetry.storageSystems || [];
  if (systems.length === 0) {
    grid.innerHTML = `
      <div class="storage-card" style="grid-column: 1 / -1; text-align:center; padding:20px; color:#94a3b8;">
        Live GCP Storage query (<code>gcloud lustre</code>, <code>gcloud filestore</code>, <code>gcloud compute disks</code>, <code>gcloud storage buckets</code>) completed for <code>${currentTelemetry.config.projectId}</code>: <strong>0 provisioned storage volumes found</strong>.
      </div>
    `;
    return;
  }

  grid.innerHTML = systems
    .map(
      (s) => `
      <div class="storage-card">
        <div class="storage-header">
          <div>
            <div class="mount-tag">${s.mountPoint}</div>
            <div style="font-weight:600; margin-top:2px;">${s.type}</div>
            <div class="card-subtitle">${s.name} · ${s.tier}</div>
          </div>
          <span class="state-badge state-${s.status}">${s.status}</span>
        </div>

        <div style="margin: 8px 0;">
          <div style="display:flex; justify-content:space-between; font-size:11.5px; margin-bottom:4px;">
            <span>Capacity Used: <strong>${s.usedTiB} TiB</strong> / ${s.capacityTiB} TiB</span>
            <strong>${s.usedPct}%</strong>
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width:${Math.min(100, s.usedPct)}%; background:${
        s.usedPct > 80 ? '#f59e0b' : '#3b82f6'
      }"></div>
          </div>
        </div>

        <div class="storage-metrics">
          <div><span class="card-subtitle">Live Throughput:</span><br/><strong>${fmtNum(s.throughputCurrentMBps)} MB/s</strong></div>
          <div><span class="card-subtitle">30d Peak / Avg:</span><br/><strong>${fmtNum(s.throughputPeak30dMBps)} / ${fmtNum(s.throughputAvg30dMBps)} MB/s</strong></div>
          <div><span class="card-subtitle">Live IOPS:</span><br/><strong>${fmtNum(s.iopsCurrent)} IOPS</strong></div>
          <div><span class="card-subtitle">Mounted Nodes:</span><br/><strong>${s.connectedClients} clients</strong></div>
        </div>

        <div style="margin-top:8px; font-size:11px; color:var(--muted-foreground,#94a3b8);">
          <strong>Top Consumers:</strong> ${(s.topUsers || []).join(', ')}
        </div>
        <div style="margin-top:4px; font-size:11px; color:var(--muted-foreground,#94a3b8);">
          ${s.notes}
        </div>
      </div>
    `
    )
    .join('');
}

function renderStorageChart() {
  const svg = document.getElementById('storage-chart-svg');
  if (!svg || !currentTelemetry) return;

  const series = currentTelemetry.dailySeries || [];
  const W = 780;
  const H = 190;
  const padL = 38;
  const padR = 14;
  const padT = 14;
  const padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxVal = Math.max(
    100,
    ...series.map((d) => Math.max(d.lustreUsedTiB + d.filestoreUsedTiB, d.peakThroughputGBps))
  );

  const stepX = plotW / Math.max(1, series.length - 1);

  const buildPath = (getter) =>
    series
      .map((d, i) => {
        const x = padL + i * stepX;
        const y = padT + plotH - (getter(d) / maxVal) * plotH;
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');

  let html = '';
  for (let i = 0; i <= 3; i++) {
    const val = Math.round((maxVal * i) / 3);
    const y = padT + plotH - (plotH * i) / 3;
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="rgba(148,163,184,0.15)" stroke-dasharray="3,3" />`;
    html += `<text x="${padL - 6}" y="${y + 4}" text-anchor="end" fill="#94a3b8" font-size="10">${val}</text>`;
  }

  html += `<path d="${buildPath((d) => d.lustreUsedTiB)}" fill="none" stroke="#3b82f6" stroke-width="2.2" />`;
  html += `<path d="${buildPath((d) => d.filestoreUsedTiB)}" fill="none" stroke="#14b8a6" stroke-width="2.2" />`;
  html += `<path d="${buildPath((d) => d.peakThroughputGBps)}" fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="4,3" />`;

  series.forEach((d, idx) => {
    if (idx % Math.max(1, Math.floor(series.length / 7)) === 0 || idx === series.length - 1) {
      const x = padL + idx * stepX;
      html += `<text x="${x}" y="${H - 7}" text-anchor="middle" fill="#94a3b8" font-size="10">${d.label}</text>`;
    }
  });

  svg.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Event Wiring
// ---------------------------------------------------------------------------

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

  // Chart metric switcher
  document.getElementById('chart-metric-select')?.addEventListener('change', () => {
    renderInstancesChart();
  });

  // Filters
  document.getElementById('job-search-input')?.addEventListener('input', renderJobsTable);
  document.getElementById('job-state-filter')?.addEventListener('change', renderJobsTable);
  document.getElementById('job-partition-filter')?.addEventListener('change', renderJobsTable);
  document.getElementById('btn-clear-user-filter')?.addEventListener('click', () => {
    selectedUserFilter = null;
    renderUsersTable();
    renderJobsTable();
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
      loginNode: document.getElementById('cfg-login').value,
      zone: document.getElementById('cfg-zone')?.value || '',
      days: selectedWindowDays,
    };
    const res = await apiFetch('/api/config', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      currentTelemetry = await res.json();
      renderAll();
      drawer?.classList.add('hidden');
      showToast('Configuration saved');
    }
  });

  // Sync button
  document.getElementById('btn-sync')?.addEventListener('click', () => loadTelemetry(true));

  // Agent interaction buttons
  document.getElementById('btn-ask-agent')?.addEventListener('click', () => {
    if (!currentTelemetry) return;
    const s = currentTelemetry.summary30d;
    sendToAgent(
      `Analyze our 30-day HPC & Slurm telemetry in project ${currentTelemetry.config.projectId} (${currentTelemetry.config.region}): ` +
        `Currently ${s.currentRunningInstances} running instances (30d peak: ${s.peakInstances30d}, 30d avg: ${s.avgInstances30d}, ${s.totalInstanceHours30d} VM-hrs), ` +
        `${s.runningJobsNow} active Slurm jobs across ${s.activeUsersNow} users, and ${s.totalStorageUsedTiB}/${s.totalStorageCapacityTiB} TiB used across Managed Lustre, Filestore, and GCS. ` +
        `Provide optimization recommendations for partition sizing and storage tiering.`
    );
  });

  document.getElementById('btn-scale-cluster')?.addEventListener('click', () => {
    if (!currentTelemetry) return;
    sendToAgent(
      `Help me review and adjust the Slurm cluster partition scaling in ${currentTelemetry.config.projectId} (${currentTelemetry.config.region}) based on our 30-day instance utilization.`
    );
  });

  document.getElementById('btn-check-storage-quota')?.addEventListener('click', () => {
    if (!currentTelemetry) return;
    sendToAgent(
      `Run the storage-quota-checker skill for project ${currentTelemetry.config.projectId} in region ${currentTelemetry.config.region} to verify our Managed Lustre and Filestore quota headroom.`
    );
  });

  loadTelemetry(false);
});

