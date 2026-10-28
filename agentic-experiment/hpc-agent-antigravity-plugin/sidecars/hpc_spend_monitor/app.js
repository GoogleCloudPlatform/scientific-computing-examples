(function () {
  'use strict';

  const FOUR_HOURS_MS = 4 * 60 * 60 * 1000;
  let currentReport = null;
  let nextPollTargetMs = Date.now() + FOUR_HOURS_MS;
  let lastFrontendAlertKey = '';

  const els = {
    statusDot: document.getElementById('statusDot'),
    monthBadge: document.getElementById('monthBadge'),
    projectSubtitle: document.getElementById('projectSubtitle'),
    nextPollCountdown: document.getElementById('nextPollCountdown'),
    pollNowBtn: document.getElementById('pollNowBtn'),

    budgetPromptCard: document.getElementById('budgetPromptCard'),
    budgetPromptTitle: document.getElementById('budgetPromptTitle'),
    budgetStatusPill: document.getElementById('budgetStatusPill'),
    nextResetDateLabel: document.getElementById('nextResetDateLabel'),
    budgetForm: document.getElementById('budgetForm'),
    maxBudgetInput: document.getElementById('maxBudgetInput'),
    projectIdInput: document.getElementById('projectIdInput'),
    bqTableInput: document.getElementById('bqTableInput'),
    saveBudgetBtn: document.getElementById('saveBudgetBtn'),

    exceededAlertBanner: document.getElementById('exceededAlertBanner'),
    agentNotifiedBadge: document.getElementById('agentNotifiedBadge'),
    exceededAlertText: document.getElementById('exceededAlertText'),
    sendAlertToAgentBtn: document.getElementById('sendAlertToAgentBtn'),
    askAgentMitigateBtn: document.getElementById('askAgentMitigateBtn'),

    kpiMonthTag: document.getElementById('kpiMonthTag'),
    kpiHpcSpend: document.getElementById('kpiHpcSpend'),
    kpiBudgetComparison: document.getElementById('kpiBudgetComparison'),
    budgetProgressBar: document.getElementById('budgetProgressBar'),

    kpiHpcPortionPct: document.getElementById('kpiHpcPortionPct'),
    kpiTotalGcpBillSub: document.getElementById('kpiTotalGcpBillSub'),
    splitHpcBar: document.getElementById('splitHpcBar'),
    splitNonHpcBar: document.getElementById('splitNonHpcBar'),

    kpiLast4hBurn: document.getElementById('kpiLast4hBurn'),
    kpiAvg4hBurn: document.getElementById('kpiAvg4hBurn'),

    kpiResetTag: document.getElementById('kpiResetTag'),
    kpiRemainingBudget: document.getElementById('kpiRemainingBudget'),
    kpiElapsedBlocks: document.getElementById('kpiElapsedBlocks'),

    cumulativeSpendSvg: document.getElementById('cumulativeSpendSvg'),
    skuBreakdownBody: document.getElementById('skuBreakdownBody'),
    fourHourLogBody: document.getElementById('fourHourLogBody'),
    sendSummaryToAgentBtn: document.getElementById('sendSummaryToAgentBtn'),

    lastPollFooter: document.getElementById('lastPollFooter'),
    resetNoticeFooter: document.getElementById('resetNoticeFooter'),
    toastBanner: document.getElementById('toastBanner'),
  };

  function getActiveConversationId() {
    return (window.sidecar && window.sidecar.conversationId) || '';
  }

  async function sidecarFetch(url, options = {}) {
    const fn =
      window.sidecar && typeof window.sidecar.fetch === 'function'
        ? window.sidecar.fetch.bind(window.sidecar)
        : window.fetch.bind(window);
    return await fn(url, options);
  }

  function fmtUsd(val, decimals = 2) {
    const n = Number(val) || 0;
    return (
      '$' +
      n.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
    );
  }

  function showToast(msg, durationMs = 4200) {
    if (!els.toastBanner) return;
    els.toastBanner.textContent = msg;
    els.toastBanner.classList.remove('hidden');
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
      els.toastBanner.classList.add('hidden');
    }, durationMs);
  }

  async function dispatchAgentNotification(message, title = '🚨 HPC Monthly Spend Alert') {
    const convId = getActiveConversationId();
    let sentViaPreload = false;

    // 1. Try preload bridge (`window.sidecar.agent.sendMessage` / `startConversation`) if available
    if (window.sidecar && window.sidecar.agent) {
      try {
        if (convId && typeof window.sidecar.agent.sendMessage === 'function') {
          await window.sidecar.agent.sendMessage(message, convId);
          sentViaPreload = true;
        } else if (typeof window.sidecar.agent.startConversation === 'function') {
          await window.sidecar.agent.startConversation(message, title);
          sentViaPreload = true;
        }
      } catch (err) {
        console.warn('[hpc_spend_monitor] preload agent notify fallback to backend:', err);
      }
    }

    // 2. Also notify backend `/api/notify-agent` so persistent alert ledger stays synchronized
    try {
      const res = await sidecarFetch('/api/notify-agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversationId: convId,
          message: sentViaPreload ? '' : message,
          title,
        }),
      });
      await res.json();
    } catch (err) {
      console.warn('[hpc_spend_monitor] backend notify-agent error:', err);
    }

    showToast('🚨 Alert notification sent to Agent conversation!');
  }

  function renderCumulativeChart(data) {
    const svg = els.cumulativeSpendSvg;
    if (!svg) return;

    const series = Array.isArray(data.fourHourSeries) ? data.fourHourSeries : [];
    if (series.length === 0) {
      svg.innerHTML = '';
      return;
    }

    const W = 760;
    const H = 230;
    const padL = 62;
    const padR = 24;
    const padT = 20;
    const padB = 32;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const maxBudget = Number(data.maxMonthlyBudgetUsd) || 25000;
    const maxTotal = Math.max(...series.map((d) => d.cumulativeTotalUsd || 0), 1);
    const maxHpc = Math.max(...series.map((d) => d.cumulativeHpcUsd || 0), 1);
    const yMax = Math.max(maxBudget * 1.15, maxTotal * 1.08, maxHpc * 1.15, 1000);

    const xForIndex = (i) =>
      padL + (series.length <= 1 ? plotW : (i / (series.length - 1)) * plotW);
    const yForVal = (v) => padT + plotH - Math.min(1, Math.max(0, v / yMax)) * plotH;

    // Horizontal Y grid lines
    const gridTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * yMax);
    const gridLinesHtml = gridTicks
      .map((val) => {
        const y = yForVal(val).toFixed(1);
        const label =
          val >= 1000 ? `$${(val / 1000).toFixed(1)}k` : `$${Math.round(val)}`;
        return `
          <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="rgba(148,163,184,0.12)" stroke-width="1" />
          <text x="${padL - 8}" y="${Number(y) + 4}" text-anchor="end" fill="#95a3b8" font-size="10" font-family="monospace">${label}</text>
        `;
      })
      .join('');

    // Polyline points for Total GCP Bill & Accumulated HPC Spend
    const totalPts = series
      .map((d, i) => `${xForIndex(i).toFixed(1)},${yForVal(d.cumulativeTotalUsd).toFixed(1)}`)
      .join(' ');
    const hpcPts = series
      .map((d, i) => `${xForIndex(i).toFixed(1)},${yForVal(d.cumulativeHpcUsd).toFixed(1)}`)
      .join(' ');

    const firstX = xForIndex(0).toFixed(1);
    const lastX = xForIndex(series.length - 1).toFixed(1);
    const baseLineY = (padT + plotH).toFixed(1);
    const hpcAreaPts = `${firstX},${baseLineY} ${hpcPts} ${lastX},${baseLineY}`;

    // Max Monthly HPC Spend Cap line
    const capY = yForVal(maxBudget).toFixed(1);
    const isExceeded = Boolean(data.isExceeded);
    const hpcStroke = isExceeded ? '#ef4444' : '#38bdf8';
    const hpcFillId = isExceeded ? 'hpcExceededGrad' : 'hpcNormalGrad';

    // X-axis date labels (5 evenly spaced)
    const xTickIndices = [
      0,
      Math.floor((series.length - 1) * 0.25),
      Math.floor((series.length - 1) * 0.5),
      Math.floor((series.length - 1) * 0.75),
      series.length - 1,
    ];
    const uniqueXIndices = Array.from(new Set(xTickIndices));
    const xLabelsHtml = uniqueXIndices
      .map((idx) => {
        const item = series[idx];
        if (!item) return '';
        const x = xForIndex(idx).toFixed(1);
        return `<text x="${x}" y="${H - 10}" text-anchor="middle" fill="#95a3b8" font-size="10" font-family="monospace">${item.label}</text>`;
      })
      .join('');

    // Highlight latest point
    const lastPoint = series[series.length - 1];
    const lastPtX = xForIndex(series.length - 1).toFixed(1);
    const lastPtY = yForVal(lastPoint.cumulativeHpcUsd).toFixed(1);

    svg.innerHTML = `
      <defs>
        <linearGradient id="hpcNormalGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.35" />
          <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.02" />
        </linearGradient>
        <linearGradient id="hpcExceededGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ef4444" stop-opacity="0.42" />
          <stop offset="100%" stop-color="#ef4444" stop-opacity="0.03" />
        </linearGradient>
      </defs>
      ${gridLinesHtml}
      <!-- Total GCP Bill Line -->
      <polyline fill="none" stroke="#64748b" stroke-width="1.6" stroke-dasharray="3,3" points="${totalPts}" />
      <!-- HPC Spend Area & Line -->
      <polygon fill="url(#${hpcFillId})" points="${hpcAreaPts}" />
      <polyline fill="none" stroke="${hpcStroke}" stroke-width="2.6" points="${hpcPts}" />
      <!-- Max Monthly Budget Cap Line -->
      <line x1="${padL}" y1="${capY}" x2="${W - padR}" y2="${capY}" stroke="#ef4444" stroke-width="1.8" stroke-dasharray="6,4" />
      <rect x="${W - padR - 178}" y="${Math.max(4, Number(capY) - 18)}" width="174" height="16" rx="4" fill="rgba(127,29,29,0.88)" />
      <text x="${W - padR - 91}" y="${Math.max(15, Number(capY) - 7)}" text-anchor="middle" fill="#fecaca" font-size="9.5" font-weight="700" font-family="monospace">
        Max Monthly Cap: ${fmtUsd(maxBudget, 0)}
      </text>
      <!-- Latest Point Marker -->
      <circle cx="${lastPtX}" cy="${lastPtY}" r="4.5" fill="${hpcStroke}" stroke="#0b0f17" stroke-width="1.5" />
      ${xLabelsHtml}
    `;
  }

  function renderTables(data) {
    if (els.skuBreakdownBody && Array.isArray(data.skuBreakdown)) {
      els.skuBreakdownBody.innerHTML = data.skuBreakdown
        .map((row) => {
          const badgeClass = row.isHpc ? 'type-hpc' : 'type-nonhpc';
          const badgeText = row.isHpc ? 'HPC' : 'Non-HPC';
          return `
            <tr>
              <td>
                <div><strong>${row.category}</strong></div>
                <div style="color:#95a3b8;font-size:0.72rem;">${row.service} &bull; ${row.usageLabel}</div>
              </td>
              <td><span class="type-badge ${badgeClass}">${badgeText}</span></td>
              <td class="num">${fmtUsd(row.last4hUsd)}</td>
              <td class="num"><strong>${fmtUsd(row.monthToDateUsd)}</strong></td>
              <td class="num">${row.shareOfTotalBillPct.toFixed(1)}%</td>
            </tr>
          `;
        })
        .join('');
    }

    if (els.fourHourLogBody && Array.isArray(data.fourHourSeries)) {
      const recent = data.fourHourSeries.slice(-10).reverse();
      els.fourHourLogBody.innerHTML = recent
        .map((b) => {
          const overCap =
            data.maxMonthlyBudgetUsd > 0 && b.cumulativeHpcUsd > data.maxMonthlyBudgetUsd;
          return `
            <tr>
              <td><code>${b.label}</code></td>
              <td class="num">${fmtUsd(b.hpcBlockUsd)}</td>
              <td class="num">${fmtUsd(b.totalBlockUsd)}</td>
              <td class="num">${b.hpcSharePct.toFixed(1)}%</td>
              <td class="num" style="color:${overCap ? '#fca5a5' : '#e6edf3'};font-weight:700;">
                ${fmtUsd(b.cumulativeHpcUsd)}
              </td>
            </tr>
          `;
        })
        .join('');
    }
  }

  function renderDashboard(data) {
    currentReport = data;
    if (data.nextPollIso) {
      const parsed = Date.parse(data.nextPollIso);
      if (!Number.isNaN(parsed)) {
        nextPollTargetMs = parsed;
      }
    }

    // Header & status dot
    els.statusDot.classList.remove('warning', 'exceeded');
    els.budgetPromptCard.classList.remove('warning', 'exceeded');
    els.budgetStatusPill.classList.remove('healthy', 'warning', 'exceeded');

    if (data.isExceeded) {
      els.statusDot.classList.add('exceeded');
      els.budgetPromptCard.classList.add('exceeded');
      els.budgetStatusPill.classList.add('exceeded');
      els.budgetStatusPill.textContent = 'EXCEEDED MONTHLY LIMIT';
    } else if (data.isWarning) {
      els.statusDot.classList.add('warning');
      els.budgetPromptCard.classList.add('warning');
      els.budgetStatusPill.classList.add('warning');
      els.budgetStatusPill.textContent = `WARNING (${data.budgetUtilizationPct.toFixed(1)}%)`;
    } else {
      els.budgetStatusPill.classList.add('healthy');
      els.budgetStatusPill.textContent = `WITHIN BUDGET (${data.budgetUtilizationPct.toFixed(1)}%)`;
    }

    els.monthBadge.textContent = `${data.billingMonth} (${data.monthLabel})`;
    els.projectSubtitle.innerHTML =
      `GCP Project: <code>${data.projectId}</code> &bull; Billing Account: <code>${data.billingAccountName}</code> &bull; Source: <code>${data.dataSource}</code>`;

    if (els.nextResetDateLabel && data.nextResetIso) {
      els.nextResetDateLabel.textContent = `${data.nextResetIso.slice(0, 10)} 00:00 UTC`;
    }

    // Populate form inputs if not actively focused
    if (document.activeElement !== els.maxBudgetInput) {
      els.maxBudgetInput.value = data.maxMonthlyBudgetUsd || 25000;
    }
    if (document.activeElement !== els.projectIdInput) {
      els.projectIdInput.value = data.projectId || '';
    }
    if (document.activeElement !== els.bqTableInput) {
      els.bqTableInput.value = data.billingExportTable || '';
    }

    // Highlight active preset button
    document.querySelectorAll('.chip-btn[data-preset]').forEach((btn) => {
      const presetVal = Number(btn.getAttribute('data-preset'));
      btn.classList.toggle('active', presetVal === Number(data.maxMonthlyBudgetUsd));
    });

    // Exceeded Alert Banner & Automatic Agent Notification
    if (data.isExceeded) {
      els.exceededAlertBanner.classList.remove('hidden');
      const overage = data.accumulatedHpcSpendUsd - data.maxMonthlyBudgetUsd;
      els.exceededAlertText.innerHTML =
        `Accumulated HPC spend for <strong>${data.monthLabel}</strong> is <strong>${fmtUsd(data.accumulatedHpcSpendUsd)}</strong> ` +
        `(${data.hpcPortionPct}% of your ${fmtUsd(data.totalGcpBillUsd)} total GCP bill), which exceeds your maximum monthly spend limit of ` +
        `<strong>${fmtUsd(data.maxMonthlyBudgetUsd)}</strong> by <strong>+${fmtUsd(overage)}</strong> (${data.budgetUtilizationPct.toFixed(1)}% used).`;

      const alertKey = `${data.billingMonth}:${data.maxMonthlyBudgetUsd}`;
      if (data.alertState?.justNotifiedAgent && lastFrontendAlertKey !== alertKey) {
        lastFrontendAlertKey = alertKey;
        // Also ensure preload bridge notifies the active agent window if connected
        if (window.sidecar && window.sidecar.agent && data.alertState.alertMessage) {
          const convId = getActiveConversationId();
          if (convId && typeof window.sidecar.agent.sendMessage === 'function') {
            window.sidecar.agent.sendMessage(data.alertState.alertMessage, convId).catch(() => {});
          }
        }
        showToast('🚨 Monthly HPC Budget Exceeded! Alert notification sent to Agent.');
      }
    } else {
      els.exceededAlertBanner.classList.add('hidden');
    }

    // KPI 1: Accumulated HPC Spend
    els.kpiMonthTag.textContent = data.billingMonth;
    els.kpiHpcSpend.textContent = fmtUsd(data.accumulatedHpcSpendUsd);
    els.kpiHpcSpend.style.color = data.isExceeded ? '#fca5a5' : '#e6edf3';
    els.kpiBudgetComparison.textContent =
      `of ${fmtUsd(data.maxMonthlyBudgetUsd)} monthly max (${data.budgetUtilizationPct.toFixed(1)}%)`;

    const pctBar = Math.min(100, Math.max(0, data.budgetUtilizationPct));
    els.budgetProgressBar.style.width = `${pctBar}%`;
    els.budgetProgressBar.classList.remove('warning', 'exceeded');
    if (data.isExceeded) els.budgetProgressBar.classList.add('exceeded');
    else if (data.isWarning) els.budgetProgressBar.classList.add('warning');

    // KPI 2: HPC Portion of Total GCP Bill
    els.kpiHpcPortionPct.textContent = `${data.hpcPortionPct.toFixed(1)}%`;
    els.kpiTotalGcpBillSub.innerHTML =
      `Total GCP Bill (MTD): <strong>${fmtUsd(data.totalGcpBillUsd)}</strong> (Non-HPC: ${fmtUsd(data.nonHpcSpendUsd)})`;
    els.splitHpcBar.style.width = `${data.hpcPortionPct}%`;
    els.splitNonHpcBar.style.width = `${data.nonHpcPortionPct}%`;

    // KPI 3: Latest 4-Hour HPC Burn
    els.kpiLast4hBurn.innerHTML = `${fmtUsd(data.last4hHpcSpendUsd)} <small style="font-size:0.85rem;color:#95a3b8;">/ 4h</small>`;
    els.kpiAvg4hBurn.textContent =
      `Month Avg: ${fmtUsd(data.avgFourHourHpcSpendUsd)} / 4h • Projected EOM: ${fmtUsd(data.projectedMonthEndHpcUsd, 0)}`;

    // KPI 4: Remaining Monthly HPC Budget & Monthly Reset
    const nextResetShort = data.nextResetIso ? data.nextResetIso.slice(0, 10) : '1st of Month';
    els.kpiResetTag.textContent = `Resets ${nextResetShort}`;
    if (data.remainingBudgetUsd >= 0) {
      els.kpiRemainingBudget.textContent = fmtUsd(data.remainingBudgetUsd);
      els.kpiRemainingBudget.style.color = '#10b981';
    } else {
      els.kpiRemainingBudget.textContent = `-${fmtUsd(Math.abs(data.remainingBudgetUsd))}`;
      els.kpiRemainingBudget.style.color = '#ef4444';
    }
    els.kpiElapsedBlocks.textContent =
      `${data.elapsedFourHourBlocks} / ${data.totalFourHourBlocksInMonth} 4-hour billing intervals elapsed`;

    // Chart & Tables
    renderCumulativeChart(data);
    renderTables(data);

    // Footer
    const pollTimeStr = data.lastPollIso
      ? new Date(data.lastPollIso).toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
      : '--';
    els.lastPollFooter.textContent = `Last 4h GCP Billing Poll: ${pollTimeStr}`;
    els.resetNoticeFooter.textContent =
      `Monthly accumulator (${data.billingMonth}) resets automatically on ${nextResetShort} 00:00 UTC.`;
  }

  async function fetchSpendReport(forceRefresh = false) {
    try {
      if (forceRefresh && els.pollNowBtn) {
        els.pollNowBtn.disabled = true;
        els.pollNowBtn.textContent = '↻ Polling GCP Billing...';
      }
      const convId = encodeURIComponent(getActiveConversationId());
      const url = `/api/spend?refresh=${forceRefresh ? '1' : '0'}&conversationId=${convId}`;
      const res = await sidecarFetch(url);
      const data = await res.json();
      renderDashboard(data);
      if (forceRefresh) {
        showToast('✔ 4-hour GCP Billing & HPC portion updated');
      }
    } catch (err) {
      console.error('[hpc_spend_monitor] Failed to fetch spend report:', err);
      showToast('⚠ Error fetching GCP spend report');
    } finally {
      if (els.pollNowBtn) {
        els.pollNowBtn.disabled = false;
        els.pollNowBtn.innerHTML = '&#x21bb; Poll Billing Now';
      }
    }
  }

  async function saveBudgetSettings(e) {
    if (e) e.preventDefault();
    const maxVal = Number(els.maxBudgetInput.value);
    if (Number.isNaN(maxVal) || maxVal <= 0) {
      showToast('Please enter a valid maximum monthly HPC spend amount ($ USD).');
      return;
    }

    try {
      els.saveBudgetBtn.disabled = true;
      els.saveBudgetBtn.textContent = 'Saving...';
      const payload = {
        maxMonthlyBudgetUsd: maxVal,
        projectId: els.projectIdInput.value.trim(),
        billingExportTable: els.bqTableInput.value.trim(),
        conversationId: getActiveConversationId(),
      };
      const res = await sidecarFetch('/api/budget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const updated = await res.json();
      renderDashboard(updated);

      if (updated.isExceeded) {
        showToast(
          `🚨 Max budget set to ${fmtUsd(maxVal, 0)} — Exceeded by ${fmtUsd(updated.accumulatedHpcSpendUsd - maxVal)}! Agent alerted.`
        );
      } else {
        showToast(`✔ Saved Max Monthly HPC Spend: ${fmtUsd(maxVal, 0)}`);
      }
    } catch (err) {
      console.error('[hpc_spend_monitor] Failed to save budget:', err);
      showToast('⚠ Error saving monthly budget');
    } finally {
      els.saveBudgetBtn.disabled = false;
      els.saveBudgetBtn.textContent = 'Save Monthly Max Spend';
    }
  }

  // Wire Event Listeners
  if (els.budgetForm) {
    els.budgetForm.addEventListener('submit', saveBudgetSettings);
  }

  document.querySelectorAll('.chip-btn[data-preset]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const val = Number(btn.getAttribute('data-preset'));
      if (!Number.isNaN(val) && els.maxBudgetInput) {
        els.maxBudgetInput.value = val;
        saveBudgetSettings();
      }
    });
  });

  if (els.pollNowBtn) {
    els.pollNowBtn.addEventListener('click', () => fetchSpendReport(true));
  }

  if (els.sendAlertToAgentBtn) {
    els.sendAlertToAgentBtn.addEventListener('click', () => {
      const msg =
        (currentReport && currentReport.alertState && currentReport.alertState.alertMessage) ||
        `🚨 **[HPC SPEND ALERT]**: Accumulated monthly HPC spend (${fmtUsd(currentReport?.accumulatedHpcSpendUsd)}) has exceeded the user's maximum monthly budget of ${fmtUsd(currentReport?.maxMonthlyBudgetUsd)}.`;
      dispatchAgentNotification(msg, '🚨 HPC Monthly Budget Exceeded Alert');
    });
  }

  if (els.askAgentMitigateBtn) {
    els.askAgentMitigateBtn.addEventListener('click', () => {
      if (!currentReport) return;
      const msg =
        `🚨 **Urgent HPC Cost Containment Request (${currentReport.billingMonth})**\n\n` +
        `Our accumulated HPC spend is **${fmtUsd(currentReport.accumulatedHpcSpendUsd)}** (${currentReport.hpcPortionPct}% of the ${fmtUsd(currentReport.totalGcpBillUsd)} total GCP bill), exceeding our monthly cap of **${fmtUsd(currentReport.maxMonthlyBudgetUsd)}**.\n\n` +
        `Please help me immediately reduce our 4-hour HPC burn rate (**${fmtUsd(currentReport.last4hHpcSpendUsd)} / 4h**) by:\n` +
        `1. Checking idle or low-utilization Slurm compute partitions and scaling down static nodes.\n` +
        `2. Switching eligible Google Cloud Batch / Nextflow queues from Standard to Spot VMs.\n` +
        `3. Auditing Managed Lustre & Filestore scratch capacity that can be archived to Cloud Storage.`;
      dispatchAgentNotification(msg, '⚙ Mitigate HPC Monthly Spend Overage');
    });
  }

  if (els.sendSummaryToAgentBtn) {
    els.sendSummaryToAgentBtn.addEventListener('click', () => {
      if (!currentReport) return;
      const msg =
        `📊 **4-Hour HPC Spend & Monthly Budget Report (${currentReport.billingMonth})**\n` +
        `- **GCP Project**: \`${currentReport.projectId}\` (\`${currentReport.billingAccountName}\`)\n` +
        `- **Accumulated HPC Spend (MTD)**: **${fmtUsd(currentReport.accumulatedHpcSpendUsd)}** / **${fmtUsd(currentReport.maxMonthlyBudgetUsd)}** max (${currentReport.budgetUtilizationPct.toFixed(1)}%)\n` +
        `- **HPC Portion of Total GCP Bill**: **${currentReport.hpcPortionPct}%** (Total Bill: ${fmtUsd(currentReport.totalGcpBillUsd)}, Non-HPC: ${fmtUsd(currentReport.nonHpcSpendUsd)})\n` +
        `- **Last 4-Hour HPC Burn**: **${fmtUsd(currentReport.last4hHpcSpendUsd)} / 4h** (Projected Month-End: ${fmtUsd(currentReport.projectedMonthEndHpcUsd)})\n` +
        `- **Next Monthly Reset**: \`${(currentReport.nextResetIso || '').slice(0, 10)} 00:00 UTC\``;
      dispatchAgentNotification(msg, '📊 4-Hour HPC Spend Summary');
    });
  }

  // 1-second countdown ticker for the 4-hour polling cycle
  setInterval(() => {
    const remainingMs = Math.max(0, nextPollTargetMs - Date.now());
    const totalSec = Math.floor(remainingMs / 1000);
    const hrs = String(Math.floor(totalSec / 3600)).padStart(2, '0');
    const mins = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
    const secs = String(totalSec % 60).padStart(2, '0');
    if (els.nextPollCountdown) {
      els.nextPollCountdown.textContent = `${hrs}h ${mins}m ${secs}s`;
    }
    if (remainingMs <= 0) {
      nextPollTargetMs = Date.now() + FOUR_HOURS_MS;
      fetchSpendReport(true);
    }
  }, 1000);

  // Initial load
  fetchSpendReport(false);
})();

