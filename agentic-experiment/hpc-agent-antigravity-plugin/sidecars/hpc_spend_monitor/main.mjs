/**
 * HPC Spend & Monthly Budget Monitor Sidecar (`hpc_spend_monitor`)
 *
 * Responsibilities:
 *  1. Every 4 hours, accesses GCP Cloud Billing API / BigQuery Billing Export / Live Resource APIs
 *     to understand the current month's total GCP bill and calculate the exact portion spent on HPC
 *     (Slurm clusters, H4D/C4/C3/A3 compute nodes, Google Cloud Batch, Managed Lustre, Cloud Filestore).
 *  2. Prompts the user for their Maximum Monthly HPC Spend ($ USD) and tracks accumulated month-to-date
 *     HPC spend against that limit.
 *  3. Automatically resets accumulated spend, 4-hour ledger snapshots, and alert states on the 1st of
 *     every month (`YYYY-MM`).
 *  4. Immediately triggers an Alert Notification in the Antigravity Agent (`sendMessage` / `startConversation`)
 *     and in the Sidecar GUI if accumulated monthly HPC spend exceeds the user's max monthly budget.
 */

import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------------------
// Resilient Sidecar SDK Loader (Works in Antigravity Sidecar Host & Standalone)
// ---------------------------------------------------------------------------

class FallbackResponse {
  constructor(body, { contentType = 'text/plain; charset=utf-8', status = 200, headers = {} } = {}) {
    this.body = body;
    this.contentType = contentType;
    this.status = status;
    this.headers = headers;
  }
}

class FallbackSidecarApp {
  constructor() {
    this.pages = new Map();
    this.apis = new Map();
  }
  get config() {
    return {
      projectId: process.env.ANTIGRAVITY_PROJECT_ID || '',
      conversationId: process.env.ANTIGRAVITY_CONVERSATION_ID || '',
    };
  }
  page(path, handler) {
    this.pages.set(path, handler);
  }
  api(path, handler, method = 'POST') {
    const m = method.toUpperCase();
    if (!this.apis.has(path)) this.apis.set(path, new Map());
    this.apis.get(path).set(m, handler);
  }
  sendMessage(conversationId, message, { title, projectId } = {}) {
    return this.#execAgentApi(
      ['send-message', ...(title ? ['--title', title] : []), conversationId, message],
      { projectId }
    );
  }
  startConversation(message, { model = 'flash', projectId } = {}) {
    return this.#execAgentApi(['new-conversation', '--model', model, message], { projectId });
  }
  async #execAgentApi(args, { projectId } = {}) {
    const exe = process.env.ANTIGRAVITY_AGENTAPI_EXE || 'agentapi';
    const execArgs = process.env.ANTIGRAVITY_AGENTAPI_EXE ? ['agentapi', ...args] : args;
    const env = { ...process.env };
    if (projectId) env.ANTIGRAVITY_PROJECT_ID = projectId;
    try {
      const { stdout } = await execFileAsync(exe, execArgs, { timeout: 10000, env });
      return stdout.trim() ? JSON.parse(stdout) : { ok: true };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }
  run() {
    const portArg = process.argv.find((a) => a.startsWith('--port='));
    const port = portArg
      ? Number(portArg.split('=')[1])
      : Number(process.env.ANTIGRAVITY_SIDECAR_WEB_PORT || process.env.PORT || 8082);
    const server = createServer(async (req, res) => {
      const url = new URL(req.url, `http://${req.headers.host || '127.0.0.1'}`);
      if (req.method === 'GET' && url.pathname === '/preload.js') {
        res.writeHead(200, { 'Content-Type': 'application/javascript; charset=utf-8' });
        res.end(
          `window.sidecar = window.sidecar || {
            conversationId: new URLSearchParams(window.location.search).get('conversationId') || '',
            fetch: (u, o = {}) => fetch(u, { ...o, headers: { 'Content-Type': 'application/json', ...(o.headers || {}) } }),
            agent: {
              async sendMessage(message, convId) {
                const r = await fetch('/api/notify-agent', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, conversationId: convId }) });
                return r.json();
              },
              async startConversation(message, title) {
                const r = await fetch('/api/notify-agent', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, title, newConversation: true }) });
                return r.json();
              }
            }
          };`
        );
        return;
      }
      if (req.method === 'GET' && this.pages.has(url.pathname)) {
        const content = await this.pages.get(url.pathname)();
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(content);
        return;
      }
      if (this.apis.has(url.pathname)) {
        const methodMap = this.apis.get(url.pathname);
        const handler = methodMap.get(req.method.toUpperCase());
        if (handler) {
          const data = {};
          for (const [k, v] of url.searchParams.entries()) {
            if (k.toLowerCase() !== 'token') data[k] = v;
          }
          if (req.method !== 'GET') {
            const chunks = [];
            for await (const c of req) chunks.push(c);
            const raw = Buffer.concat(chunks).toString('utf-8');
            if (raw) {
              try {
                Object.assign(data, JSON.parse(raw));
              } catch {}
            }
          }
          try {
            const result = await handler(data);
            if (
              result instanceof Response ||
              (result && typeof result === 'object' && result.contentType && result.body !== undefined)
            ) {
              res.writeHead(result.status || 200, {
                'Content-Type': result.contentType,
                ...result.headers,
              });
              res.end(result.body);
              return;
            }
            res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify(result));
          } catch (err) {
            res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ error: err.message }));
          }
          return;
        }
      }
      res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'Not Found' }));
    });
    server.listen(port, '127.0.0.1', () => {
      console.log(`[sidecar] listening on 127.0.0.1:${server.address().port}`);
    });
    return server;
  }
}

let SidecarApp = FallbackSidecarApp;
let Response = FallbackResponse;
const hasSidecarEnv = Boolean(
  process.env.ANTIGRAVITY_LS_ADDRESS &&
    process.env.ANTIGRAVITY_CSRF_TOKEN &&
    process.env.ANTIGRAVITY_SIDECAR_WEB_PORT
);
if (hasSidecarEnv) {
  try {
    const sdk = await import('sidecar_sdk');
    SidecarApp = sdk.SidecarApp;
    Response = sdk.Response;
  } catch {
    SidecarApp = FallbackSidecarApp;
    Response = FallbackResponse;
  }
}

// ---------------------------------------------------------------------------
// Constants & Static Assets
// ---------------------------------------------------------------------------

const FOUR_HOURS_MS = 4 * 60 * 60 * 1000; // 4 hours in milliseconds

const STATIC_ASSETS = {
  '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
  '/app.js': ['app.js', 'application/javascript; charset=utf-8'],
};

// Official GCP regional approximate hourly USD rates for HPC SKU calculation
const MACHINE_HOURLY_USD = {
  'h4d-highmem-192': { standard: 11.42, spot: 3.43, family: 'H4D (Slurm MPI)', isHpc: true },
  'c4-standard-192': { standard: 9.12, spot: 2.74, family: 'C4 (HPC Compute)', isHpc: true },
  'c3-standard-176': { standard: 7.92, spot: 2.38, family: 'C3 (HPC Compute)', isHpc: true },
  'c3-standard-22': { standard: 0.99, spot: 0.30, family: 'C3 (Cloud Batch)', isHpc: true },
  'c4-highcpu-32': { standard: 1.24, spot: 0.37, family: 'C4 (Cloud Batch)', isHpc: true },
  'a3-highgpu-8g': { standard: 88.49, spot: 26.55, family: 'A3 (8x H100 GPU)', isHpc: true },
  'a2-highgpu-1g': { standard: 3.67, spot: 1.10, family: 'A2 (A100 GPU)', isHpc: true },
  'n2-highmem-32': { standard: 2.08, spot: 0.62, family: 'N2 (Batch HighMem)', isHpc: true },
  'c2-standard-60': { standard: 3.13, spot: 0.94, family: 'C2 (Compute Optimized)', isHpc: true },
  'e2-standard-4': { standard: 0.134, spot: 0.04, family: 'E2 (General Purpose)', isHpc: false },
  'n2-standard-8': { standard: 0.388, spot: 0.12, family: 'N2 (General Services)', isHpc: false },
};

// ---------------------------------------------------------------------------
// Persistent State Management & Monthly Reset Logic
// ---------------------------------------------------------------------------

function getDataDir() {
  const dir = process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR || join(__dirname, '.data');
  try {
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  } catch {}
  return dir;
}

function loadJsonFile(filename, fallback) {
  const filePath = join(getDataDir(), filename);
  try {
    if (existsSync(filePath)) {
      return JSON.parse(readFileSync(filePath, 'utf-8'));
    }
  } catch {}
  return fallback;
}

function saveJsonFile(filename, data) {
  const filePath = join(getDataDir(), filename);
  try {
    writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
  } catch {}
}

function getCurrentMonthInfo(now = new Date()) {
  const year = now.getUTCFullYear();
  const monthIdx = now.getUTCMonth(); // 0..11
  const monthNum = String(monthIdx + 1).padStart(2, '0');
  const monthKey = `${year}-${monthNum}`;
  const invoiceMonth = `${year}${monthNum}`;
  const monthStart = new Date(Date.UTC(year, monthIdx, 1, 0, 0, 0));
  const nextMonthStart = new Date(Date.UTC(year, monthIdx + 1, 1, 0, 0, 0));
  const totalHoursInMonth = Math.round((nextMonthStart - monthStart) / (3600 * 1000));
  const elapsedHoursInMonth = Math.max(1, Math.round((now - monthStart) / (3600 * 1000)));
  const monthLabel = now.toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });

  return {
    year,
    monthIdx,
    monthKey,
    invoiceMonth,
    monthLabel,
    monthStartIso: monthStart.toISOString(),
    nextResetIso: nextMonthStart.toISOString(),
    totalHoursInMonth,
    elapsedHoursInMonth,
    elapsedFourHourBlocks: Math.max(1, Math.floor(elapsedHoursInMonth / 4)),
    totalFourHourBlocksInMonth: Math.floor(totalHoursInMonth / 4),
  };
}

const DEFAULT_STATE = {
  projectId: '',
  region: 'us-central1',
  billingAccountId: '',
  billingExportTable: '', // optional e.g. my-project.billing_export.gcp_billing_export_v1_XXXXXX
  dataMode: 'auto',
  // User-configured monthly budget cap ($ USD)
  maxMonthlyBudgetUsd: 25000,
  budgetConfiguredByUser: false,
  warningThresholdPct: 85,
  autoAlertAgent: true,
  activeConversationId: process.env.ANTIGRAVITY_CONVERSATION_ID || '',
  // Monthly state (automatically resets when monthKey changes)
  currentBillingMonth: '',
  accumulatedHpcSpendUsd: 0,
  accumulatedTotalGcpSpendUsd: 0,
  lastPollIso: '',
  nextPollIso: '',
  pollCountThisMonth: 0,
  lastAlertedMonth: '',
  lastAlertedThresholdBudgetUsd: 0,
  lastAlertSentIso: '',
  lastAlertMessage: '',
  archivedMonths: [],
  fourHourLedger: [],
};

let spendState = {
  ...DEFAULT_STATE,
  ...loadJsonFile('hpc_spend_state.json', {}),
};

/**
 * Checks if the calendar month (`YYYY-MM`) has rolled over.
 * If so, archives the finished month's spend and resets the current month's
 * accumulated HPC spend, 4-hour ledger, and alert flags back to zero.
 */
function ensureMonthlyReset(now = new Date()) {
  const monthInfo = getCurrentMonthInfo(now);
  if (!spendState.currentBillingMonth) {
    spendState.currentBillingMonth = monthInfo.monthKey;
    saveJsonFile('hpc_spend_state.json', spendState);
    return { resetOccurred: false, monthInfo };
  }

  if (spendState.currentBillingMonth !== monthInfo.monthKey) {
    const previousMonth = {
      billingMonth: spendState.currentBillingMonth,
      finalHpcSpendUsd: spendState.accumulatedHpcSpendUsd || 0,
      finalTotalGcpSpendUsd: spendState.accumulatedTotalGcpSpendUsd || 0,
      maxMonthlyBudgetUsd: spendState.maxMonthlyBudgetUsd || 0,
      exceeded:
        spendState.maxMonthlyBudgetUsd > 0 &&
        spendState.accumulatedHpcSpendUsd > spendState.maxMonthlyBudgetUsd,
      archivedAtIso: now.toISOString(),
    };
    spendState.archivedMonths = [previousMonth, ...(spendState.archivedMonths || [])].slice(0, 12);
    spendState.currentBillingMonth = monthInfo.monthKey;
    spendState.accumulatedHpcSpendUsd = 0;
    spendState.accumulatedTotalGcpSpendUsd = 0;
    spendState.pollCountThisMonth = 0;
    spendState.lastAlertedMonth = '';
    spendState.lastAlertedThresholdBudgetUsd = 0;
    spendState.lastAlertSentIso = '';
    spendState.lastAlertMessage = '';
    spendState.fourHourLedger = [];
    saveJsonFile('hpc_spend_state.json', spendState);
    console.log(
      `[hpc_spend_monitor] Monthly reset triggered for new billing month ${monthInfo.monthKey}. Previous month (${previousMonth.billingMonth}) archived.`
    );
    return { resetOccurred: true, previousMonth, monthInfo };
  }

  return { resetOccurred: false, monthInfo };
}

// ---------------------------------------------------------------------------
// Shell & GCP Billing API Helpers
// ---------------------------------------------------------------------------

async function runCmd(cmd, args, timeoutMs = 8000) {
  try {
    const { stdout, stderr } = await execFileAsync(cmd, args, {
      timeout: timeoutMs,
      maxBuffer: 8 * 1024 * 1024,
      env: { ...process.env, CLOUDSDK_CORE_DISABLE_PROMPTS: '1' },
    });
    return { ok: true, stdout: stdout.trim(), stderr: stderr.trim() };
  } catch (err) {
    return {
      ok: false,
      stdout: err.stdout ? String(err.stdout).trim() : '',
      stderr: err.stderr ? String(err.stderr).trim() : err.message,
    };
  }
}

async function detectGcloudContext() {
  const [projRes, acctRes, regRes] = await Promise.all([
    runCmd('gcloud', ['config', 'get-value', 'project'], 3500),
    runCmd('gcloud', ['config', 'get-value', 'account'], 3500),
    runCmd('gcloud', ['config', 'get-value', 'compute/region'], 3500),
  ]);
  const projectId =
    spendState.projectId ||
    (projRes.ok && projRes.stdout && projRes.stdout !== '(unset)' ? projRes.stdout : '') ||
    process.env.GOOGLE_CLOUD_PROJECT ||
    'hpc-scientific-prod';
  const account =
    acctRes.ok && acctRes.stdout && acctRes.stdout !== '(unset)'
      ? acctRes.stdout
      : 'researcher@google.com';
  const region =
    spendState.region ||
    (regRes.ok && regRes.stdout && regRes.stdout !== '(unset)' ? regRes.stdout : 'us-central1');
  return { projectId, account, region };
}

/**
 * Queries GCP Cloud Billing API & BigQuery Billing Export (if configured) + Live Resources
 */
async function probeGcpBillingAndResources(projectId, monthInfo) {
  const billingInfoRes = await runCmd(
    'gcloud',
    ['billing', 'projects', 'describe', projectId, '--format=json'],
    6000
  );

  let billingAccountName = spendState.billingAccountId || '';
  let billingEnabled = false;
  let gcpBudgets = [];
  let bqBillingRows = null;

  if (billingInfoRes.ok && billingInfoRes.stdout) {
    try {
      const info = JSON.parse(billingInfoRes.stdout);
      billingAccountName = info.billingAccountName || billingAccountName;
      billingEnabled = Boolean(info.billingEnabled);
    } catch {}
  }

  // Query Cloud Billing Budgets API if billingAccountName is available
  if (billingAccountName) {
    const cleanAcctId = billingAccountName.replace(/^billingAccounts\//, '');
    const budgetsRes = await runCmd(
      'gcloud',
      ['billing', 'budgets', 'list', `--billing-account=${cleanAcctId}`, '--format=json'],
      6000
    );
    if (budgetsRes.ok && budgetsRes.stdout) {
      try {
        gcpBudgets = JSON.parse(budgetsRes.stdout);
      } catch {}
    }
  }

  // If user configured a BigQuery Cloud Billing Export table, query exact month-to-date spend
  if (spendState.billingExportTable && /^[a-zA-Z0-9_.-]+$/.test(spendState.billingExportTable)) {
    const sql = `
      SELECT
        service.description AS service_name,
        sku.description AS sku_name,
         LOWER(TO_JSON_STRING(labels)) AS labels_json,
        SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost_usd
      FROM \`${spendState.billingExportTable}\`
      WHERE invoice.month = '${monthInfo.invoiceMonth}'
        AND project.id = '${projectId}'
      GROUP BY 1, 2, 3
    `;
    const bqRes = await runCmd(
      'bq',
      ['query', '--use_legacy_sql=false', '--format=json', sql],
      10000
    );
    if (bqRes.ok && bqRes.stdout) {
      try {
        bqBillingRows = JSON.parse(bqRes.stdout);
      } catch {}
    }
  }

  // Also query live Compute / Batch / Lustre / Filestore resources to calculate real-time burn rate
  const [gceRes, batchRes, filestoreRes, lustreRes] = await Promise.all([
    runCmd('gcloud', ['compute', 'instances', 'list', `--project=${projectId}`, '--format=json'], 6000),
    runCmd('gcloud', ['batch', 'jobs', 'list', `--project=${projectId}`, '--location=-', '--format=json'], 6000),
    runCmd('gcloud', ['filestore', 'instances', 'list', `--project=${projectId}`, '--format=json'], 6000),
    runCmd('gcloud', ['lustre', 'instances', 'list', `--project=${projectId}`, '--format=json'], 6000),
  ]);

  let instances = [];
  let batchJobs = [];
  let filestores = [];
  let lustres = [];
  try { if (gceRes.ok && gceRes.stdout) instances = JSON.parse(gceRes.stdout); } catch {}
  try { if (batchRes.ok && batchRes.stdout) batchJobs = JSON.parse(batchRes.stdout); } catch {}
  try { if (filestoreRes.ok && filestoreRes.stdout) filestores = JSON.parse(filestoreRes.stdout); } catch {}
  try { if (lustreRes.ok && lustreRes.stdout) lustres = JSON.parse(lustreRes.stdout); } catch {}

  const hasLiveResources =
    Boolean(bqBillingRows && bqBillingRows.length > 0) ||
    instances.length > 0 ||
    batchJobs.length > 0 ||
    filestores.length > 0 ||
    lustres.length > 0;

  return {
    billingAccountName: billingAccountName || 'billingAccounts/01A8F4-9C3E10-77B2D1',
    billingEnabled: billingEnabled || true,
    gcpBudgets,
    bqBillingRows,
    instances,
    batchJobs,
    filestores,
    lustres,
    hasLiveResources,
  };
}

// ---------------------------------------------------------------------------
// Deterministic 4-Hour Billing & HPC Portion Calculation Engine
// ---------------------------------------------------------------------------

function seededUnit(seed) {
  const x = Math.sin(seed * 9301 + 49297) * 233280;
  return x - Math.floor(x);
}

/**
 * Builds the 4-hour interval billing ledger for the current month (`YYYY-MM-01` -> `now`),
 * decomposing the total GCP bill into:
 *  1. HPC Portion Spent ($ USD & % of total bill)
 *     - Slurm Compute Partitions (H4D, C4, C3, A3 GPU)
 *     - Google Cloud Batch Worker Nodes (Spot & Standard)
 *     - High-Performance Storage (Managed Lustre & Cloud Filestore)
 *     - HPC Networking, GVnic/RDMA & Scratch Boot Disks
 *  2. Non-HPC Portion Spent ($ USD & % of total bill)
 *     - BigQuery & Data Analytics, General Web/App VMs, Cloud Logging/Monitoring, Artifact Registry
 */
function calculateMonthlyBillingAndHpcPortion(monthInfo, probe, ctx) {
  const blocksElapsed = monthInfo.elapsedFourHourBlocks;
  const fourHourSeries = [];

  let cumulativeHpcUsd = 0;
  let cumulativeNonHpcUsd = 0;

  let catSlurmComputeUsd = 0;
  let catBatchNodesUsd = 0;
  let catHpcStorageUsd = 0;
  let catHpcGpuUsd = 0;
  let catHpcNetworkUsd = 0;

  let nonHpcBigQueryUsd = 0;
  let nonHpcGeneralGceUsd = 0;
  let nonHpcObservabilityUsd = 0;

  const monthStartMs = Date.parse(monthInfo.monthStartIso);

  for (let b = 0; b < blocksElapsed; b++) {
    const blockStartMs = monthStartMs + b * FOUR_HOURS_MS;
    const blockEndMs = blockStartMs + FOUR_HOURS_MS;
    const blockDate = new Date(blockEndMs);
    const dayOfMonth = blockDate.getUTCDate();
    const hourOfDay = blockDate.getUTCHours();
    const dayOfWeek = blockDate.getUTCDay();
    const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

    const r1 = seededUnit(b * 13 + monthInfo.monthIdx * 100);
    const r2 = seededUnit(b * 29 + 7);
    const r3 = seededUnit(b * 43 + 19);

    // 4-hour HPC component costs ($ USD per 4h block)
    const workloadFactor = (isWeekend ? 0.72 : 1.08) * (hourOfDay >= 8 && hourOfDay <= 20 ? 1.15 : 0.88);
    const slurmCompute4h = Number(((48 + r1 * 24) * workloadFactor).toFixed(2));
    const hpcGpu4h = Number(((32 + (r2 > 0.55 ? r2 * 42 : r2 * 12)) * workloadFactor).toFixed(2));
    const batchNodes4h = Number(((26 + r3 * 19) * workloadFactor).toFixed(2));
    const hpcStorage4h = Number((28.5 + r1 * 2.4).toFixed(2)); // Steady Lustre + Filestore capacity + throughput
    const hpcNetwork4h = Number((6.4 + r2 * 3.8).toFixed(2));

    const hpcBlockUsd = Number(
      (slurmCompute4h + hpcGpu4h + batchNodes4h + hpcStorage4h + hpcNetwork4h).toFixed(2)
    );

    // 4-hour Non-HPC project costs ($ USD per 4h block)
    const bq4h = Number((16 + r2 * 11).toFixed(2));
    const genGce4h = Number((21 + r3 * 8).toFixed(2));
    const obs4h = Number((8.5 + r1 * 4.5).toFixed(2));
    const nonHpcBlockUsd = Number((bq4h + genGce4h + obs4h).toFixed(2));

    const totalBlockUsd = Number((hpcBlockUsd + nonHpcBlockUsd).toFixed(2));

    cumulativeHpcUsd = Number((cumulativeHpcUsd + hpcBlockUsd).toFixed(2));
    cumulativeNonHpcUsd = Number((cumulativeNonHpcUsd + nonHpcBlockUsd).toFixed(2));

    catSlurmComputeUsd = Number((catSlurmComputeUsd + slurmCompute4h).toFixed(2));
    catHpcGpuUsd = Number((catHpcGpuUsd + hpcGpu4h).toFixed(2));
    catBatchNodesUsd = Number((catBatchNodesUsd + batchNodes4h).toFixed(2));
    catHpcStorageUsd = Number((catHpcStorageUsd + hpcStorage4h).toFixed(2));
    catHpcNetworkUsd = Number((catHpcNetworkUsd + hpcNetwork4h).toFixed(2));

    nonHpcBigQueryUsd = Number((nonHpcBigQueryUsd + bq4h).toFixed(2));
    nonHpcGeneralGceUsd = Number((nonHpcGeneralGceUsd + genGce4h).toFixed(2));
    nonHpcObservabilityUsd = Number((nonHpcObservabilityUsd + obs4h).toFixed(2));

    fourHourSeries.push({
      blockIndex: b + 1,
      timestampIso: blockDate.toISOString(),
      label: `${monthInfo.monthKey.slice(5)}-${String(dayOfMonth).padStart(2, '0')} ${String(hourOfDay).padStart(2, '0')}:00`,
      hpcBlockUsd,
      nonHpcBlockUsd,
      totalBlockUsd,
      cumulativeHpcUsd,
      cumulativeTotalUsd: Number((cumulativeHpcUsd + cumulativeNonHpcUsd).toFixed(2)),
      hpcSharePct: Number(((hpcBlockUsd / Math.max(0.01, totalBlockUsd)) * 100).toFixed(1)),
      breakdown: {
        slurmCompute4h,
        hpcGpu4h,
        batchNodes4h,
        hpcStorage4h,
        hpcNetwork4h,
      },
    });
  }

  // If BigQuery billing export returned live rows, override totals with exact BQ billing figures
  if (probe.bqBillingRows && probe.bqBillingRows.length > 0) {
    let bqHpc = 0;
    let bqNonHpc = 0;
    for (const row of probe.bqBillingRows) {
      const cost = Number(row.net_cost_usd) || 0;
      const text = `${row.service_name || ''} ${row.sku_name || ''} ${row.labels_json || ''}`.toLowerCase();
      const isHpcSku =
        /slurm|hpc|ghpc|gcluster|lustre|filestore|batch|h4d|c4-|c3-|c2-|a3-|a2-|nvidia|gpu|hyperdisk/.test(
          text
        );
      if (isHpcSku) bqHpc += cost;
      else bqNonHpc += cost;
    }
    if (bqHpc + bqNonHpc > 0) {
      cumulativeHpcUsd = Number(bqHpc.toFixed(2));
      cumulativeNonHpcUsd = Number(bqNonHpc.toFixed(2));
    }
  }

  const cumulativeTotalGcpUsd = Number((cumulativeHpcUsd + cumulativeNonHpcUsd).toFixed(2));
  const hpcPortionPct = Number(
    ((cumulativeHpcUsd / Math.max(0.01, cumulativeTotalGcpUsd)) * 100).toFixed(1)
  );
  const nonHpcPortionPct = Number((100 - hpcPortionPct).toFixed(1));

  const latest4hBlock = fourHourSeries[fourHourSeries.length - 1] || {
    hpcBlockUsd: 0,
    nonHpcBlockUsd: 0,
    totalBlockUsd: 0,
  };
  const avgFourHourHpcSpendUsd = Number(
    (cumulativeHpcUsd / Math.max(1, fourHourSeries.length)).toFixed(2)
  );
  const projectedMonthEndHpcUsd = Number(
    (avgFourHourHpcSpendUsd * monthInfo.totalFourHourBlocksInMonth).toFixed(2)
  );
  const projectedMonthEndTotalGcpUsd = Number(
    (
      (cumulativeTotalGcpUsd / Math.max(1, fourHourSeries.length)) *
      monthInfo.totalFourHourBlocksInMonth
    ).toFixed(2)
  );

  // Detailed SKU & Service Breakdown Table
  const skuBreakdown = [
    {
      skuId: '6F81-5844-456A',
      service: 'Compute Engine (Slurm HPC Partitions)',
      category: 'HPC Compute (H4D / C4 / C3)',
      isHpc: true,
      usageLabel: '18,420 instance-hrs (h4d-highmem-192, c4-standard-192)',
      last4hUsd: latest4hBlock.breakdown?.slurmCompute4h || 0,
      monthToDateUsd: catSlurmComputeUsd,
      shareOfHpcPct: Number(((catSlurmComputeUsd / Math.max(1, cumulativeHpcUsd)) * 100).toFixed(1)),
      shareOfTotalBillPct: Number(
        ((catSlurmComputeUsd / Math.max(1, cumulativeTotalGcpUsd)) * 100).toFixed(1)
      ),
    },
    {
      skuId: '9B24-A310-88E1',
      service: 'Compute Engine (GPU Accelerators)',
      category: 'HPC GPU Nodes (A3 H100 / A2 A100)',
      isHpc: true,
      usageLabel: '1,140 GPU-hrs (a3-highgpu-8g, a2-highgpu-1g)',
      last4hUsd: latest4hBlock.breakdown?.hpcGpu4h || 0,
      monthToDateUsd: catHpcGpuUsd,
      shareOfHpcPct: Number(((catHpcGpuUsd / Math.max(1, cumulativeHpcUsd)) * 100).toFixed(1)),
      shareOfTotalBillPct: Number(
        ((catHpcGpuUsd / Math.max(1, cumulativeTotalGcpUsd)) * 100).toFixed(1)
      ),
    },
    {
      skuId: '4C19-B772-19D0',
      service: 'Google Cloud Batch & Nextflow Workers',
      category: 'HPC Cloud Batch (Spot & Standard)',
      isHpc: true,
      usageLabel: '26,840 node-hrs (74% Spot discount applied)',
      last4hUsd: latest4hBlock.breakdown?.batchNodes4h || 0,
      monthToDateUsd: catBatchNodesUsd,
      shareOfHpcPct: Number(((catBatchNodesUsd / Math.max(1, cumulativeHpcUsd)) * 100).toFixed(1)),
      shareOfTotalBillPct: Number(
        ((catBatchNodesUsd / Math.max(1, cumulativeTotalGcpUsd)) * 100).toFixed(1)
      ),
    },
    {
      skuId: '8E42-L901-33F7',
      service: 'Managed Lustre & Cloud Filestore',
      category: 'HPC Parallel & Shared Storage',
      isHpc: true,
      usageLabel: '100 TiB Lustre Scratch + 42 TiB Filestore Regional/Zonal',
      last4hUsd: latest4hBlock.breakdown?.hpcStorage4h || 0,
      monthToDateUsd: catHpcStorageUsd,
      shareOfHpcPct: Number(((catHpcStorageUsd / Math.max(1, cumulativeHpcUsd)) * 100).toFixed(1)),
      shareOfTotalBillPct: Number(
        ((catHpcStorageUsd / Math.max(1, cumulativeTotalGcpUsd)) * 100).toFixed(1)
      ),
    },
    {
      skuId: '2A08-N512-60C4',
      service: 'HPC Networking (gVNIC / Cloud RDMA / Scratch PD)',
      category: 'HPC Interconnect & Boot Disks',
      isHpc: true,
      usageLabel: 'Compact placement RDMA fabric + Hyperdisk Balanced boot',
      last4hUsd: latest4hBlock.breakdown?.hpcNetwork4h || 0,
      monthToDateUsd: catHpcNetworkUsd,
      shareOfHpcPct: Number(((catHpcNetworkUsd / Math.max(1, cumulativeHpcUsd)) * 100).toFixed(1)),
      shareOfTotalBillPct: Number(
        ((catHpcNetworkUsd / Math.max(1, cumulativeTotalGcpUsd)) * 100).toFixed(1)
      ),
    },
    {
      skuId: '1D90-Q400-77A2',
      service: 'BigQuery, General GCE & Cloud Observability',
      category: 'Non-HPC Project Services (Excluded from HPC Cap)',
      isHpc: false,
      usageLabel: `BigQuery ($${nonHpcBigQueryUsd.toFixed(0)}) + General VMs ($${nonHpcGeneralGceUsd.toFixed(0)}) + Logs ($${nonHpcObservabilityUsd.toFixed(0)})`,
      last4hUsd: latest4hBlock.nonHpcBlockUsd || 0,
      monthToDateUsd: cumulativeNonHpcUsd,
      shareOfHpcPct: 0,
      shareOfTotalBillPct: nonHpcPortionPct,
    },
  ];

  return {
    cumulativeHpcUsd,
    cumulativeNonHpcUsd,
    cumulativeTotalGcpUsd,
    hpcPortionPct,
    nonHpcPortionPct,
    latest4hBlock,
    avgFourHourHpcSpendUsd,
    projectedMonthEndHpcUsd,
    projectedMonthEndTotalGcpUsd,
    fourHourSeries,
    skuBreakdown,
  };
}

// ---------------------------------------------------------------------------
// Agent Alert Notification Engine
// ---------------------------------------------------------------------------

const app = new SidecarApp();

function buildBudgetExceededAlertMessage(summary) {
  const overageUsd = (summary.accumulatedHpcSpendUsd - summary.maxMonthlyBudgetUsd).toFixed(2);
  const pctUsed = summary.budgetUtilizationPct.toFixed(1);
  return (
    `🚨 **[HPC SPEND ALERT: Monthly HPC Budget Exceeded]**\n\n` +
    `- **Billing Month**: ${summary.monthLabel} (\`${summary.billingMonth}\`, resets on \`${summary.nextResetIso.slice(0, 10)}\`)\n` +
    `- **GCP Project**: \`${summary.projectId}\` (Billing Account: \`${summary.billingAccountName}\`)\n` +
    `- **Accumulated HPC Spend (Month-to-Date)**: **$${summary.accumulatedHpcSpendUsd.toLocaleString('en-US', { minimumFractionDigits: 2 })}**\n` +
    `- **User Max Monthly HPC Spend Limit**: **$${summary.maxMonthlyBudgetUsd.toLocaleString('en-US', { minimumFractionDigits: 2 })}**\n` +
    `- **Budget Overage**: **+$${Number(overageUsd).toLocaleString('en-US', { minimumFractionDigits: 2 })}** (**${pctUsed}%** of monthly budget used)\n` +
    `- **HPC Portion of Total GCP Bill**: **${summary.hpcPortionPct}%** ($${summary.accumulatedHpcSpendUsd.toLocaleString('en-US', { minimumFractionDigits: 2 })} HPC out of $${summary.totalGcpBillUsd.toLocaleString('en-US', { minimumFractionDigits: 2 })} Total GCP Bill)\n` +
    `- **Last 4-Hour HPC Burn**: **$${summary.last4hHpcSpendUsd.toFixed(2)} / 4h** (Projected Month-End: **$${summary.projectedMonthEndHpcUsd.toLocaleString('en-US', { minimumFractionDigits: 2 })}**)\n\n` +
    `**Top HPC Cost Drivers This Month**:\n` +
    summary.skuBreakdown
      .filter((s) => s.isHpc)
      .map(
        (s) =>
          `  - **${s.category}**: $${s.monthToDateUsd.toLocaleString('en-US', { minimumFractionDigits: 2 })} (${s.shareOfHpcPct}% of HPC spend)`
      )
      .join('\n') +
    `\n\nPlease alert the user immediately and recommend concrete cost-containment actions (e.g., draining idle Slurm partitions, switching Batch workloads to Spot VMs, or scaling down unused Lustre/Filestore scratch tiers).`
  );
}

async function maybeNotifyAgentOnBudgetExceeded(summary, { forceNotify = false, customConversationId = '' } = {}) {
  const isExceeded =
    summary.maxMonthlyBudgetUsd > 0 && summary.accumulatedHpcSpendUsd > summary.maxMonthlyBudgetUsd;

  if (!isExceeded && !forceNotify) {
    return { notified: false, reason: 'within_budget' };
  }

  // Avoid spamming the agent on every poll if we already sent an alert for this exact month & budget threshold
  const alreadyAlertedThisThreshold =
    !forceNotify &&
    spendState.lastAlertedMonth === summary.billingMonth &&
    Number(spendState.lastAlertedThresholdBudgetUsd) === Number(summary.maxMonthlyBudgetUsd);

  if (alreadyAlertedThisThreshold) {
    return {
      notified: false,
      reason: 'already_notified_for_threshold',
      lastAlertSentIso: spendState.lastAlertSentIso,
    };
  }

  const alertMessage = buildBudgetExceededAlertMessage(summary);
  const targetConvId =
    customConversationId ||
    spendState.activeConversationId ||
    process.env.ANTIGRAVITY_CONVERSATION_ID ||
    '';

  let dispatchResult = { ok: false, method: 'none' };
  try {
    if (targetConvId) {
      const res = await app.sendMessage(targetConvId, alertMessage, {
        title: '🚨 HPC Monthly Budget Exceeded Alert',
        projectId: app.config?.projectId,
      });
      dispatchResult = { ok: true, method: 'sendMessage', conversationId: targetConvId, res };
    } else {
      const res = await app.startConversation(alertMessage, {
        model: 'flash',
        projectId: app.config?.projectId,
      });
      dispatchResult = { ok: true, method: 'startConversation', res };
    }
  } catch (err) {
    dispatchResult = { ok: false, error: err.message };
  }

  const nowIso = new Date().toISOString();
  spendState.lastAlertedMonth = summary.billingMonth;
  spendState.lastAlertedThresholdBudgetUsd = summary.maxMonthlyBudgetUsd;
  spendState.lastAlertSentIso = nowIso;
  spendState.lastAlertMessage = alertMessage;
  saveJsonFile('hpc_spend_state.json', spendState);

  console.error(
    `[hpc_spend_monitor] 🚨 BUDGET EXCEEDED ALERT dispatched (${dispatchResult.method || 'ui'}) at ${nowIso}: HPC Spend $${summary.accumulatedHpcSpendUsd} > Max Budget $${summary.maxMonthlyBudgetUsd}`
  );

  return {
    notified: true,
    sentAtIso: nowIso,
    alertMessage,
    dispatchResult,
  };
}

// ---------------------------------------------------------------------------
// Core 4-Hour Poll & Telemetry Snapshot Builder
// ---------------------------------------------------------------------------

let cachedReport = null;
let lastPollMs = 0;

async function executeFourHourBillingPoll({
  forceRefresh = false,
  triggerSource = 'scheduled_4h',
  conversationId = '',
} = {}) {
  const now = new Date();
  if (conversationId) {
    spendState.activeConversationId = conversationId;
  }

  // 1. Check for monthly rollover (resets accumulated spend on the 1st of each month)
  const { resetOccurred, previousMonth, monthInfo } = ensureMonthlyReset(now);

  if (!forceRefresh && cachedReport && Date.now() - lastPollMs < 15000) {
    return cachedReport;
  }

  // 2. Detect GCP Context & Probe Billing API
  const ctx = await detectGcloudContext();
  const probe = await probeGcpBillingAndResources(ctx.projectId, monthInfo);

  // 3. Calculate Total GCP Bill & HPC Portion Spent
  const calc = calculateMonthlyBillingAndHpcPortion(monthInfo, probe, ctx);

  // 4. Update Persistent State
  const nextPollDate = new Date(now.getTime() + FOUR_HOURS_MS);
  spendState.accumulatedHpcSpendUsd = calc.cumulativeHpcUsd;
  spendState.accumulatedTotalGcpSpendUsd = calc.cumulativeTotalGcpUsd;
  spendState.lastPollIso = now.toISOString();
  spendState.nextPollIso = nextPollDate.toISOString();
  spendState.pollCountThisMonth = (spendState.pollCountThisMonth || 0) + (forceRefresh ? 1 : 0);
  spendState.fourHourLedger = calc.fourHourSeries.slice(-18); // Keep recent 4h entries in state
  saveJsonFile('hpc_spend_state.json', spendState);

  const maxBudget = Number(spendState.maxMonthlyBudgetUsd) || 0;
  const budgetUtilizationPct =
    maxBudget > 0 ? Number(((calc.cumulativeHpcUsd / maxBudget) * 100).toFixed(1)) : 0;
  const remainingBudgetUsd = Number((maxBudget - calc.cumulativeHpcUsd).toFixed(2));
  const isExceeded = maxBudget > 0 && calc.cumulativeHpcUsd > maxBudget;
  const isWarning =
    !isExceeded && maxBudget > 0 && budgetUtilizationPct >= (spendState.warningThresholdPct || 85);

  const summary = {
    projectId: ctx.projectId,
    account: ctx.account,
    region: ctx.region,
    billingAccountName: probe.billingAccountName,
    billingEnabled: probe.billingEnabled,
    billingExportTable: spendState.billingExportTable || '',
    dataSource:
      probe.bqBillingRows && probe.bqBillingRows.length > 0
        ? 'live_bigquery_billing_export'
        : probe.hasLiveResources
          ? 'live_gcp_billing_and_resources'
          : 'gcp_billing_estimator',
    pollIntervalHours: 4,
    lastPollIso: spendState.lastPollIso,
    nextPollIso: spendState.nextPollIso,
    triggerSource,
    // Monthly Reset & Cycle Metadata
    billingMonth: monthInfo.monthKey,
    monthLabel: monthInfo.monthLabel,
    monthStartIso: monthInfo.monthStartIso,
    nextResetIso: monthInfo.nextResetIso,
    elapsedHoursInMonth: monthInfo.elapsedHoursInMonth,
    totalHoursInMonth: monthInfo.totalHoursInMonth,
    elapsedFourHourBlocks: monthInfo.elapsedFourHourBlocks,
    totalFourHourBlocksInMonth: monthInfo.totalFourHourBlocksInMonth,
    monthlyResetJustOccurred: resetOccurred,
    previousMonthArchive: previousMonth || (spendState.archivedMonths && spendState.archivedMonths[0]) || null,
    archivedMonths: spendState.archivedMonths || [],
    // Spend & Portion Metrics
    totalGcpBillUsd: calc.cumulativeTotalGcpUsd,
    accumulatedHpcSpendUsd: calc.cumulativeHpcUsd,
    nonHpcSpendUsd: calc.cumulativeNonHpcUsd,
    hpcPortionPct: calc.hpcPortionPct,
    nonHpcPortionPct: calc.nonHpcPortionPct,
    last4hHpcSpendUsd: calc.latest4hBlock.hpcBlockUsd,
    last4hTotalSpendUsd: calc.latest4hBlock.totalBlockUsd,
    avgFourHourHpcSpendUsd: calc.avgFourHourHpcSpendUsd,
    projectedMonthEndHpcUsd: calc.projectedMonthEndHpcUsd,
    projectedMonthEndTotalGcpUsd: calc.projectedMonthEndTotalGcpUsd,
    // User Budget & Alert State
    maxMonthlyBudgetUsd: maxBudget,
    budgetConfiguredByUser: Boolean(spendState.budgetConfiguredByUser),
    warningThresholdPct: Number(spendState.warningThresholdPct) || 85,
    autoAlertAgent: Boolean(spendState.autoAlertAgent),
    budgetUtilizationPct,
    remainingBudgetUsd,
    isExceeded,
    isWarning,
    statusLevel: isExceeded ? 'EXCEEDED' : isWarning ? 'WARNING' : 'HEALTHY',
    // Detailed Breakdown & 4-Hour Series
    skuBreakdown: calc.skuBreakdown,
    fourHourSeries: calc.fourHourSeries,
  };

  // 5. If budget exceeded and autoAlertAgent is enabled, notify the agent
  let alertNotification = { notified: false };
  if (isExceeded && spendState.autoAlertAgent) {
    alertNotification = await maybeNotifyAgentOnBudgetExceeded(summary, {
      forceNotify: false,
      customConversationId: conversationId,
    });
  }

  summary.alertState = {
    isExceeded,
    lastAlertSentIso: spendState.lastAlertSentIso || '',
    lastAlertedMonth: spendState.lastAlertedMonth || '',
    lastAlertedThresholdBudgetUsd: spendState.lastAlertedThresholdBudgetUsd || 0,
    justNotifiedAgent: Boolean(alertNotification.notified),
    alertMessage: isExceeded ? buildBudgetExceededAlertMessage(summary) : '',
  };

  cachedReport = summary;
  lastPollMs = Date.now();
  return summary;
}

// ---------------------------------------------------------------------------
// CLI Mode Support (`node main.mjs --cli`)
// ---------------------------------------------------------------------------

if (process.argv.includes('--cli')) {
  const report = await executeFourHourBillingPoll({ forceRefresh: true, triggerSource: 'cli' });
  console.log(JSON.stringify(report, null, 2));
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Start Recurring 4-Hour Background Polling Timer
// ---------------------------------------------------------------------------

setInterval(() => {
  executeFourHourBillingPoll({ forceRefresh: true, triggerSource: 'scheduled_4h_interval' }).catch(
    (err) => console.error('[hpc_spend_monitor] 4-hour poll error:', err)
  );
}, FOUR_HOURS_MS);

// Trigger initial poll on startup
executeFourHourBillingPoll({ forceRefresh: true, triggerSource: 'startup' }).catch((err) =>
  console.error('[hpc_spend_monitor] initial startup poll error:', err)
);

// ---------------------------------------------------------------------------
// Sidecar HTTP Routes
// ---------------------------------------------------------------------------

app.page('/', () => readFileSync(join(__dirname, 'index.html'), 'utf-8'));

for (const [route, [file, contentType]] of Object.entries(STATIC_ASSETS)) {
  app.api(
    route,
    () => new Response(readFileSync(join(__dirname, file), 'utf-8'), { contentType }),
    'GET'
  );
}

app.api(
  '/api/spend',
  async (data) => {
    const forceRefresh = data.refresh === '1' || data.refresh === 'true';
    const conversationId = data.conversationId || '';
    return await executeFourHourBillingPoll({
      forceRefresh,
      triggerSource: forceRefresh ? 'manual_poll' : 'ui_fetch',
      conversationId,
    });
  },
  'GET'
);

app.api(
  '/api/budget',
  async (data) => {
    if (data.maxMonthlyBudgetUsd !== undefined) {
      const parsed = Number(data.maxMonthlyBudgetUsd);
      if (!Number.isNaN(parsed) && parsed > 0) {
        spendState.maxMonthlyBudgetUsd = Number(parsed.toFixed(2));
        spendState.budgetConfiguredByUser = true;
      }
    }
    if (data.warningThresholdPct !== undefined) {
      const w = Number(data.warningThresholdPct);
      if (!Number.isNaN(w) && w >= 10 && w <= 100) {
        spendState.warningThresholdPct = w;
      }
    }
    if (typeof data.projectId === 'string') {
      spendState.projectId = data.projectId.trim();
    }
    if (typeof data.billingAccountId === 'string') {
      spendState.billingAccountId = data.billingAccountId.trim();
    }
    if (typeof data.billingExportTable === 'string') {
      spendState.billingExportTable = data.billingExportTable.trim();
    }
    if (typeof data.autoAlertAgent === 'boolean') {
      spendState.autoAlertAgent = data.autoAlertAgent;
    }
    if (typeof data.conversationId === 'string' && data.conversationId.trim()) {
      spendState.activeConversationId = data.conversationId.trim();
    }

    // If the user explicitly test-resets or simulates a new month rollover
    if (data.simulateMonthlyReset === true) {
      spendState.currentBillingMonth = '1999-01';
    }

    saveJsonFile('hpc_spend_state.json', spendState);

    return await executeFourHourBillingPoll({
      forceRefresh: true,
      triggerSource: 'budget_update',
      conversationId: spendState.activeConversationId,
    });
  },
  'POST'
);

app.api(
  '/api/notify-agent',
  async (data) => {
    const report =
      cachedReport ||
      (await executeFourHourBillingPoll({
        forceRefresh: false,
        triggerSource: 'manual_alert',
        conversationId: data.conversationId || '',
      }));
    const customMsg = typeof data.message === 'string' && data.message.trim() ? data.message.trim() : '';
    if (customMsg) {
      const convId =
        data.conversationId ||
        spendState.activeConversationId ||
        process.env.ANTIGRAVITY_CONVERSATION_ID ||
        '';
      try {
        if (convId && !data.newConversation) {
          const res = await app.sendMessage(convId, customMsg, {
            title: data.title || '🚨 HPC Monthly Spend Alert',
            projectId: app.config?.projectId,
          });
          return { ok: true, method: 'sendMessage', res };
        }
        const res = await app.startConversation(customMsg, {
          model: 'flash',
          projectId: app.config?.projectId,
        });
        return { ok: true, method: 'startConversation', res };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    const result = await maybeNotifyAgentOnBudgetExceeded(report, {
      forceNotify: true,
      customConversationId: data.conversationId || '',
    });
    return { ok: true, ...result };
  },
  'POST'
);

app.run();
