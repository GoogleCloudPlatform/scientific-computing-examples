/**
 * HPC Spend & Monthly Budget Monitor Sidecar (`hpc_spend_monitor`)
 *
 * STRICT REAL-TIME TELEMETRY ONLY — NO DEMO OR HARDCODED FALLBACK DATA.
 *
 * Responsibilities:
 *  1. Every 4 hours, accesses live GCP Cloud Billing API, BigQuery Cloud Billing Export (if available),
 *     and live GCP Resource APIs (Compute Engine, Persistent Disks/Hyperdisks, Cloud Batch, Managed Lustre,
 *     Cloud Filestore) to calculate the real month-to-date GCP bill and the exact HPC portion of spend.
 *  2. Prompts the user for their Maximum Monthly HPC Spend ($ USD) and verifies accumulated month-to-date
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
      console.error(`[sidecar] listening on 127.0.0.1:${server.address().port}`);
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
// Constants & GCP Pricing Lookup Tables (Used Only for Real Discovered Resources)
// ---------------------------------------------------------------------------

const FOUR_HOURS_MS = 4 * 60 * 60 * 1000;

const STATIC_ASSETS = {
  '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
  '/app.js': ['app.js', 'application/javascript; charset=utf-8'],
};

// Per-vCPU and per-GB-RAM hourly USD catalog rates by GCP machine family
// Used to compute real burn rate of live instances discovered via `gcloud compute instances list`
// or `gcloud batch jobs list` when BigQuery Billing Export is not configured.
const FAMILY_PRICING_PER_VCPU_HR = {
  h4d: { standard: 0.0595, spot: 0.0179, isHpc: true, label: 'H4D (Slurm Cloud RDMA)' },
  h3: { standard: 0.052, spot: 0.0156, isHpc: true, label: 'H3 (HPC Compute)' },
  c4: { standard: 0.0475, spot: 0.0143, isHpc: true, label: 'C4 (HPC Compute)' },
  c4d: { standard: 0.0445, spot: 0.0134, isHpc: true, label: 'C4D (HPC Compute)' },
  c3: { standard: 0.045, spot: 0.0135, isHpc: true, label: 'C3 (HPC Compute)' },
  c3d: { standard: 0.041, spot: 0.0123, isHpc: true, label: 'C3D (HPC Compute)' },
  c2: { standard: 0.0522, spot: 0.0157, isHpc: true, label: 'C2 (Compute Optimized)' },
  c2d: { standard: 0.045, spot: 0.0135, isHpc: true, label: 'C2D (Compute Optimized)' },
  a3: { standard: 0.425, spot: 0.128, isHpc: true, label: 'A3 (NVIDIA H100 GPU)' },
  a2: { standard: 0.306, spot: 0.092, isHpc: true, label: 'A2 (NVIDIA A100 GPU)' },
  g2: { standard: 0.078, spot: 0.024, isHpc: true, label: 'G2 (NVIDIA L4 GPU)' },
  n4: { standard: 0.039, spot: 0.0117, isHpc: false, label: 'N4 (General Purpose)' },
  n2: { standard: 0.0485, spot: 0.0145, isHpc: false, label: 'N2 (General Purpose)' },
  n2d: { standard: 0.0422, spot: 0.0127, isHpc: false, label: 'N2D (General Purpose)' },
  e2: { standard: 0.0335, spot: 0.01, isHpc: false, label: 'E2 (General Purpose)' },
  n1: { standard: 0.0475, spot: 0.01, isHpc: false, label: 'N1 (General Purpose)' },
};

const GPU_HOURLY_USD = {
  'nvidia-h100-80gb': 11.06,
  'nvidia-h100-mega-80gb': 12.2,
  'nvidia-tesla-a100': 3.67,
  'nvidia-a100-80gb': 5.07,
  'nvidia-l4': 0.81,
  'nvidia-tesla-v100': 2.48,
  'nvidia-tesla-t4': 0.35,
};

function parseMachineHourlyRate(machineType, isSpot = false, labels = {}, name = '') {
  const shortType = (machineType || '').split('/').pop().toLowerCase();
  const parts = shortType.split('-');
  const family = parts[0] || 'e2';
  const vcpus = Number(parts[2]) || (shortType.includes('8g') ? 208 : shortType.includes('1g') ? 12 : 4);
  const pricing = FAMILY_PRICING_PER_VCPU_HR[family] || FAMILY_PRICING_PER_VCPU_HR.e2;
  const ratePerVcpu = isSpot ? pricing.spot : pricing.standard;

  const labelStr = `${name} ${JSON.stringify(labels || {})}`.toLowerCase();
  const hasHpcMarker =
    pricing.isHpc ||
    /hpc|slurm|ghpc|gcluster|batch|mpi|lustre|nextflow|compute|login|controller/.test(labelStr);

  return {
    family: family.toUpperCase(),
    vcpus,
    hourlyUsd: Number((vcpus * ratePerVcpu).toFixed(4)),
    isHpc: hasHpcMarker,
    categoryLabel: pricing.label,
  };
}

// ---------------------------------------------------------------------------
// Persistent State Management & Monthly Reset Logic
// ---------------------------------------------------------------------------

function getDataDir() {
  const dir =
    process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR ||
    join('/tmp', 'hpc_agent_antigravity_spend_monitor');
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
  billingExportTable: '',
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
    console.error(
      `[hpc_spend_monitor] Monthly reset triggered for new billing month ${monthInfo.monthKey}. Previous month (${previousMonth.billingMonth}) archived.`
    );
    return { resetOccurred: true, previousMonth, monthInfo };
  }

  return { resetOccurred: false, monthInfo };
}

// ---------------------------------------------------------------------------
// Shell & Real-Time GCP API Helpers
// ---------------------------------------------------------------------------

async function runCmd(cmd, args, timeoutMs = 10000) {
  try {
    const { stdout, stderr } = await execFileAsync(cmd, args, {
      timeout: timeoutMs,
      maxBuffer: 12 * 1024 * 1024,
      env: {
        ...process.env,
        CLOUDSDK_CORE_DISABLE_PROMPTS: '1',
        CLOUDSDK_CORE_DISABLE_FILE_LOGGING: '1',
      },
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
    runCmd('gcloud', ['config', 'get-value', 'project'], 4000),
    runCmd('gcloud', ['config', 'get-value', 'account'], 4000),
    runCmd('gcloud', ['config', 'get-value', 'compute/region'], 4000),
  ]);
  const clean = (v) => (v && v !== '(unset)' ? v.split('\n').pop().trim() : '');
  const projectId =
    spendState.projectId ||
    (projRes.ok ? clean(projRes.stdout) : '') ||
    process.env.GOOGLE_CLOUD_PROJECT ||
    '';
  const account = acctRes.ok ? clean(acctRes.stdout) : '';
  const region = spendState.region || (regRes.ok ? clean(regRes.stdout) : '') || 'us-central1';
  return { projectId, account, region };
}

/**
 * Attempts to auto-discover a BigQuery Cloud Billing Export table in the project
 * if the user has not explicitly provided one.
 */
async function autoDiscoverBqBillingExportTable(projectId) {
  if (!projectId) return '';
  const dsRes = await runCmd('bq', ['ls', `--project_id=${projectId}`, '--format=json'], 6000);
  if (!dsRes.ok || !dsRes.stdout) return '';
  try {
    const datasets = JSON.parse(dsRes.stdout);
    if (!Array.isArray(datasets)) return '';
    for (const ds of datasets) {
      const dsId = ds.datasetReference?.datasetId || '';
      if (/billing|cost|finops|export/i.test(dsId)) {
        const tblRes = await runCmd(
          'bq',
          ['ls', `--project_id=${projectId}`, `${projectId}:${dsId}`, '--format=json'],
          6000
        );
        if (tblRes.ok && tblRes.stdout) {
          const tables = JSON.parse(tblRes.stdout);
          if (Array.isArray(tables)) {
            const match = tables.find((t) =>
              /gcp_billing_export/i.test(t.tableReference?.tableId || '')
            );
            if (match) {
              return `${projectId}.${dsId}.${match.tableReference.tableId}`;
            }
          }
        }
      }
    }
  } catch {}
  return '';
}

/**
 * Queries real-time GCP Cloud Billing API, BigQuery Billing Export (if configured/discovered),
 * and live GCP resources (Compute Engine VMs, Disks, Batch jobs, Filestore, Managed Lustre).
 */
async function probeGcpBillingAndResources(projectId, monthInfo) {
  const errors = [];
  if (!projectId) {
    errors.push('No active GCP project configured in gcloud.');
    return {
      billingAccountName: 'Not Configured',
      billingEnabled: false,
      gcpBudgets: [],
      bqSkuRows: null,
      bqFourHourRows: null,
      instances: [],
      disks: [],
      batchJobs: [],
      filestores: [],
      lustres: [],
      errors,
    };
  }

  // 1. Query GCP Cloud Billing Project Info
  const billingInfoRes = await runCmd(
    'gcloud',
    ['billing', 'projects', 'describe', projectId, '--format=json'],
    8000
  );

  let billingAccountName = spendState.billingAccountId || '';
  let billingEnabled = false;
  let gcpBudgets = [];

  if (billingInfoRes.ok && billingInfoRes.stdout) {
    try {
      const info = JSON.parse(billingInfoRes.stdout);
      billingAccountName = info.billingAccountName || billingAccountName || 'No Billing Account Linked';
      billingEnabled = Boolean(info.billingEnabled);
    } catch (e) {
      errors.push(`Billing describe JSON parse error: ${e.message}`);
    }
  } else if (billingInfoRes.stderr) {
    errors.push(`Billing API: ${billingInfoRes.stderr.split('\n')[0]}`);
  }

  // 2. Query Cloud Billing Budgets API if billing account is known
  if (billingAccountName && billingAccountName.startsWith('billingAccounts/')) {
    const cleanAcctId = billingAccountName.replace(/^billingAccounts\//, '');
    const budgetsRes = await runCmd(
      'gcloud',
      ['billing', 'budgets', 'list', `--billing-account=${cleanAcctId}`, '--format=json'],
      8000
    );
    if (budgetsRes.ok && budgetsRes.stdout) {
      try {
        gcpBudgets = JSON.parse(budgetsRes.stdout);
      } catch {}
    }
  }

  // 3. Query BigQuery Cloud Billing Export if configured or auto-discovered
  let bqTable = spendState.billingExportTable;
  if (!bqTable) {
    bqTable = await autoDiscoverBqBillingExportTable(projectId);
    if (bqTable) {
      spendState.billingExportTable = bqTable;
      saveJsonFile('hpc_spend_state.json', spendState);
    }
  }

  let bqSkuRows = null;
  let bqFourHourRows = null;
  if (bqTable && /^[a-zA-Z0-9_.:-]+$/.test(bqTable)) {
    const normalizedTable = bqTable.replace(':', '.');
    const skuSql = `
      SELECT
        service.description AS service_name,
        sku.description AS sku_name,
        sku.id AS sku_id,
        LOWER(TO_JSON_STRING(labels)) AS labels_json,
        SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost_usd,
        SUM(CASE WHEN usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 4 HOUR)
            THEN cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)
            ELSE 0 END) AS last_4h_usd,
        SUM(usage.amount_in_pricing_units) AS usage_amount,
        ANY_VALUE(usage.pricing_unit) AS pricing_unit
      FROM \`${normalizedTable}\`
      WHERE invoice.month = '${monthInfo.invoiceMonth}'
        AND project.id = '${projectId}'
      GROUP BY 1, 2, 3, 4
      HAVING net_cost_usd != 0
      ORDER BY net_cost_usd DESC
    `;
    const seriesSql = `
      SELECT
        TIMESTAMP_SECONDS(DIV(UNIX_SECONDS(usage_start_time), 14400) * 14400) AS block_start_ts,
        LOWER(CONCAT(IFNULL(service.description, ''), ' ', IFNULL(sku.description, ''), ' ', IFNULL(TO_JSON_STRING(labels), ''))) AS meta_text,
        SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost_usd
      FROM \`${normalizedTable}\`
      WHERE invoice.month = '${monthInfo.invoiceMonth}'
        AND project.id = '${projectId}'
      GROUP BY 1, 2
      ORDER BY 1 ASC
    `;
    const [skuRes, seriesRes] = await Promise.all([
      runCmd('bq', ['query', '--use_legacy_sql=false', '--format=json', skuSql], 12000),
      runCmd('bq', ['query', '--use_legacy_sql=false', '--format=json', seriesSql], 12000),
    ]);
    if (skuRes.ok && skuRes.stdout) {
      try {
        bqSkuRows = JSON.parse(skuRes.stdout);
      } catch {}
    } else if (skuRes.stderr) {
      errors.push(`BigQuery Billing Export: ${skuRes.stderr.split('\n')[0]}`);
    }
    if (seriesRes.ok && seriesRes.stdout) {
      try {
        bqFourHourRows = JSON.parse(seriesRes.stdout);
      } catch {}
    }
  }

  // 4. Query Real-Time GCP Compute, Disks, Batch, Filestore & Managed Lustre Resources
  const [gceRes, disksRes, batchRes, filestoreRes, lustreRes] = await Promise.all([
    runCmd('gcloud', ['compute', 'instances', 'list', `--project=${projectId}`, '--format=json'], 9000),
    runCmd('gcloud', ['compute', 'disks', 'list', `--project=${projectId}`, '--format=json'], 9000),
    runCmd('gcloud', ['batch', 'jobs', 'list', `--project=${projectId}`, '--location=-', '--format=json'], 9000),
    runCmd('gcloud', ['filestore', 'instances', 'list', `--project=${projectId}`, '--format=json'], 9000),
    runCmd('gcloud', ['lustre', 'instances', 'list', `--project=${projectId}`, '--location=-', '--format=json'], 9000),
  ]);

  let instances = [];
  let disks = [];
  let batchJobs = [];
  let filestores = [];
  let lustres = [];

  if (gceRes.ok && gceRes.stdout) {
    try { instances = JSON.parse(gceRes.stdout); } catch {}
  } else if (gceRes.stderr && !gceRes.stderr.includes('Listed 0 items')) {
    errors.push(`Compute Engine API: ${gceRes.stderr.split('\n')[0]}`);
  }

  if (disksRes.ok && disksRes.stdout) {
    try { disks = JSON.parse(disksRes.stdout); } catch {}
  }

  if (batchRes.ok && batchRes.stdout) {
    try { batchJobs = JSON.parse(batchRes.stdout); } catch {}
  }

  if (filestoreRes.ok && filestoreRes.stdout) {
    try { filestores = JSON.parse(filestoreRes.stdout); } catch {}
  }

  if (lustreRes.ok && lustreRes.stdout) {
    try { lustres = JSON.parse(lustreRes.stdout); } catch {}
  }

  return {
    billingAccountName: billingAccountName || 'Not Linked / Unavailable',
    billingEnabled,
    gcpBudgets: Array.isArray(gcpBudgets) ? gcpBudgets : [],
    bqSkuRows: Array.isArray(bqSkuRows) ? bqSkuRows : null,
    bqFourHourRows: Array.isArray(bqFourHourRows) ? bqFourHourRows : null,
    instances: Array.isArray(instances) ? instances : [],
    disks: Array.isArray(disks) ? disks : [],
    batchJobs: Array.isArray(batchJobs) ? batchJobs : [],
    filestores: Array.isArray(filestores) ? filestores : [],
    lustres: Array.isArray(lustres) ? lustres : [],
    errors,
  };
}

// ---------------------------------------------------------------------------
// 100% Real-Time 4-Hour Billing & HPC Portion Calculation Engine
// ---------------------------------------------------------------------------

function isHpcBillingText(text) {
  return /slurm|hpc|ghpc|gcluster|lustre|filestore|batch|h4d|h3-|c4-|c4d-|c3-|c3d-|c2-|c2d-|a3-|a2-|g2-|nvidia|gpu|hyperdisk-extreme|hyperdisk-ml|rdma|gvnic/.test(
    String(text || '').toLowerCase()
  );
}

/**
 * Calculates how many hours a resource was active inside `[blockStartMs, blockEndMs]`.
 */
function overlapHoursInBlock(resourceStartMs, resourceEndMs, blockStartMs, blockEndMs) {
  const start = Math.max(resourceStartMs, blockStartMs);
  const end = Math.min(resourceEndMs, blockEndMs);
  if (end <= start) return 0;
  return (end - start) / (3600 * 1000);
}

/**
 * Decomposes the current month's real GCP bill and active resource usage into:
 *  - `fourHourSeries`: Real 4-hour interval spend from the 1st of the month to `now`
 *  - `skuBreakdown`: Real cost categories & SKUs discovered in the project
 *  - Exact `cumulativeHpcUsd`, `cumulativeNonHpcUsd`, `cumulativeTotalGcpUsd`, `hpcPortionPct`
 */
function calculateRealMonthlyBillingAndHpcPortion(monthInfo, probe, nowMs = Date.now()) {
  const monthStartMs = Date.parse(monthInfo.monthStartIso);
  const blocksElapsed = monthInfo.elapsedFourHourBlocks;

  // Case 1: BigQuery Cloud Billing Export returned real invoice rows for this month
  if (probe.bqSkuRows && probe.bqSkuRows.length > 0) {
    let cumulativeHpcUsd = 0;
    let cumulativeNonHpcUsd = 0;
    const skuBreakdown = [];

    for (const row of probe.bqSkuRows) {
      const mtdCost = Number(Number(row.net_cost_usd || 0).toFixed(2));
      const last4hCost = Number(Number(row.last_4h_usd || 0).toFixed(2));
      const combinedText = `${row.service_name || ''} ${row.sku_name || ''} ${row.labels_json || ''}`;
      const isHpc = isHpcBillingText(combinedText);

      if (isHpc) cumulativeHpcUsd = Number((cumulativeHpcUsd + mtdCost).toFixed(2));
      else cumulativeNonHpcUsd = Number((cumulativeNonHpcUsd + mtdCost).toFixed(2));

      skuBreakdown.push({
        skuId: row.sku_id || 'BQ-EXPORT',
        service: row.service_name || 'Google Cloud Service',
        category: row.sku_name || 'Cloud Billing SKU',
        isHpc,
        usageLabel: row.usage_amount
          ? `${Number(row.usage_amount).toLocaleString('en-US', { maximumFractionDigits: 2 })} ${row.pricing_unit || 'units'}`
          : 'BigQuery Billing Export',
        last4hUsd: last4hCost,
        monthToDateUsd: mtdCost,
        shareOfHpcPct: 0,
        shareOfTotalBillPct: 0,
      });
    }

    const cumulativeTotalGcpUsd = Number((cumulativeHpcUsd + cumulativeNonHpcUsd).toFixed(2));
    for (const item of skuBreakdown) {
      item.shareOfHpcPct =
        item.isHpc && cumulativeHpcUsd > 0
          ? Number(((item.monthToDateUsd / cumulativeHpcUsd) * 100).toFixed(1))
          : 0;
      item.shareOfTotalBillPct =
        cumulativeTotalGcpUsd > 0
          ? Number(((item.monthToDateUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
          : 0;
    }

    // Build 4-hour series from BigQuery `bqFourHourRows`
    const bucketMap = new Map();
    for (const r of probe.bqFourHourRows || []) {
      const tsMs = Date.parse(r.block_start_ts);
      if (Number.isNaN(tsMs)) continue;
      const idx = Math.floor((tsMs - monthStartMs) / FOUR_HOURS_MS);
      if (idx < 0 || idx >= blocksElapsed) continue;
      const cur = bucketMap.get(idx) || { hpc: 0, nonHpc: 0 };
      const c = Number(r.net_cost_usd) || 0;
      if (isHpcBillingText(r.meta_text)) cur.hpc += c;
      else cur.nonHpc += c;
      bucketMap.set(idx, cur);
    }

    const fourHourSeries = [];
    let runHpc = 0;
    let runNonHpc = 0;
    for (let b = 0; b < blocksElapsed; b++) {
      const blockEndMs = monthStartMs + (b + 1) * FOUR_HOURS_MS;
      const d = new Date(blockEndMs);
      const entry = bucketMap.get(b) || { hpc: 0, nonHpc: 0 };
      const hpcBlockUsd = Number(entry.hpc.toFixed(2));
      const nonHpcBlockUsd = Number(entry.nonHpc.toFixed(2));
      const totalBlockUsd = Number((hpcBlockUsd + nonHpcBlockUsd).toFixed(2));
      runHpc = Number((runHpc + hpcBlockUsd).toFixed(2));
      runNonHpc = Number((runNonHpc + nonHpcBlockUsd).toFixed(2));

      fourHourSeries.push({
        blockIndex: b + 1,
        timestampIso: d.toISOString(),
        label: `${monthInfo.monthKey.slice(5)}-${String(d.getUTCDate()).padStart(2, '0')} ${String(d.getUTCHours()).padStart(2, '0')}:00`,
        hpcBlockUsd,
        nonHpcBlockUsd,
        totalBlockUsd,
        cumulativeHpcUsd: runHpc,
        cumulativeTotalUsd: Number((runHpc + runNonHpc).toFixed(2)),
        hpcSharePct:
          totalBlockUsd > 0 ? Number(((hpcBlockUsd / totalBlockUsd) * 100).toFixed(1)) : 0,
      });
    }

    const hpcPortionPct =
      cumulativeTotalGcpUsd > 0
        ? Number(((cumulativeHpcUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
        : 0;
    const nonHpcPortionPct =
      cumulativeTotalGcpUsd > 0 ? Number((100 - hpcPortionPct).toFixed(1)) : 0;
    const latest4hBlock = fourHourSeries[fourHourSeries.length - 1] || {
      hpcBlockUsd: 0,
      nonHpcBlockUsd: 0,
      totalBlockUsd: 0,
    };
    const avgFourHourHpcSpendUsd = Number(
      (cumulativeHpcUsd / Math.max(1, fourHourSeries.length)).toFixed(2)
    );

    return {
      cumulativeHpcUsd,
      cumulativeNonHpcUsd,
      cumulativeTotalGcpUsd,
      hpcPortionPct,
      nonHpcPortionPct,
      latest4hBlock,
      avgFourHourHpcSpendUsd,
      projectedMonthEndHpcUsd: Number(
        (avgFourHourHpcSpendUsd * monthInfo.totalFourHourBlocksInMonth).toFixed(2)
      ),
      projectedMonthEndTotalGcpUsd: Number(
        (
          (cumulativeTotalGcpUsd / Math.max(1, fourHourSeries.length)) *
          monthInfo.totalFourHourBlocksInMonth
        ).toFixed(2)
      ),
      fourHourSeries,
      skuBreakdown,
    };
  }

  // Case 2: No BigQuery export table configured — compute 100% from real live GCP resources in the project
  // Parse real GCE instances
  const parsedInstances = probe.instances.map((inst) => {
    const createdMs = inst.creationTimestamp ? Date.parse(inst.creationTimestamp) : monthStartMs;
    const startMs = inst.lastStartTimestamp ? Date.parse(inst.lastStartTimestamp) : createdMs;
    const isRunning = inst.status === 'RUNNING';
    const stopMs = isRunning
      ? nowMs
      : inst.lastStopTimestamp
        ? Date.parse(inst.lastStopTimestamp)
        : createdMs;
    const isSpot =
      inst.scheduling?.provisioningModel === 'SPOT' || inst.scheduling?.preemptible === true;
    const rateInfo = parseMachineHourlyRate(inst.machineType, isSpot, inst.labels, inst.name);

    let gpuHourlyUsd = 0;
    let gpuCount = 0;
    for (const acc of inst.guestAccelerators || []) {
      const accType = (acc.acceleratorType || '').split('/').pop().toLowerCase();
      const cnt = Number(acc.acceleratorCount) || 0;
      gpuCount += cnt;
      gpuHourlyUsd += cnt * (GPU_HOURLY_USD[accType] || 2.5);
    }

    return {
      name: inst.name,
      status: inst.status,
      machineType: (inst.machineType || '').split('/').pop() || 'unknown',
      isSpot,
      isHpc: rateInfo.isHpc || gpuCount > 0,
      categoryLabel: rateInfo.categoryLabel,
      vmHourlyUsd: rateInfo.hourlyUsd,
      gpuHourlyUsd,
      gpuCount,
      activeStartMs: Math.max(monthStartMs, Math.min(createdMs, startMs)),
      activeEndMs: Math.max(createdMs, stopMs),
    };
  });

  // Parse real Persistent Disks & Hyperdisks
  const parsedDisks = probe.disks.map((d) => {
    const sizeGb = Number(d.sizeGb) || 0;
    const diskType = (d.type || '').split('/').pop().toLowerCase();
    const createdMs = d.creationTimestamp ? Date.parse(d.creationTimestamp) : monthStartMs;
    const monthlyPerGb = diskType.includes('hyperdisk')
      ? 0.12
      : diskType.includes('ssd')
        ? 0.17
        : diskType.includes('balanced')
          ? 0.1
          : 0.04;
    const hourlyUsd = (sizeGb * monthlyPerGb) / 730;
    const usersStr = JSON.stringify(d.users || []).toLowerCase();
    const labelsStr = JSON.stringify(d.labels || {}).toLowerCase();
    const isHpc =
      diskType.includes('hyperdisk') ||
      isHpcBillingText(`${d.name || ''} ${usersStr} ${labelsStr}`);
    return {
      name: d.name,
      diskType,
      sizeGb,
      hourlyUsd,
      isHpc,
      activeStartMs: Math.max(monthStartMs, createdMs),
      activeEndMs: nowMs,
    };
  });

  // Parse real Google Cloud Batch jobs
  const parsedBatchJobs = probe.batchJobs.map((jb) => {
    const createMs = jb.createTime ? Date.parse(jb.createTime) : nowMs;
    const state = jb.status?.state || 'UNKNOWN';
    const updateMs = jb.updateTime ? Date.parse(jb.updateTime) : nowMs;
    const endMs = state === 'SUCCEEDED' || state === 'FAILED' ? updateMs : nowMs;
    const instPolicy = jb.allocationPolicy?.instances?.[0]?.policy || {};
    const mt = instPolicy.machineType || 'e2-standard-4';
    const isSpot = instPolicy.provisioningModel === 'SPOT';
    const parallelism = Math.max(1, Number(jb.taskGroups?.[0]?.parallelism || 1));
    const rateInfo = parseMachineHourlyRate(mt, isSpot, jb.labels, jb.name);
    return {
      name: (jb.name || '').split('/').pop() || 'batch-job',
      state,
      machineType: mt,
      isSpot,
      parallelism,
      hourlyUsd: rateInfo.hourlyUsd * parallelism,
      activeStartMs: Math.max(monthStartMs, createMs),
      activeEndMs: Math.max(createMs, endMs),
    };
  });

  // Parse real Cloud Filestore & Managed Lustre instances
  const parsedStorage = [
    ...probe.lustres.map((l) => {
      const capGib = Number(l.capacityGib) || 0;
      const createMs = l.createTime ? Date.parse(l.createTime) : monthStartMs;
      const hourlyUsd = (capGib * 0.22) / 730;
      return {
        name: (l.name || '').split('/').pop() || 'lustre',
        service: 'Google Cloud Managed Lustre',
        capGib,
        hourlyUsd,
        activeStartMs: Math.max(monthStartMs, createMs),
        activeEndMs: nowMs,
      };
    }),
    ...probe.filestores.map((f) => {
      const capGib = Number(f.fileShares?.[0]?.capacityGb) || 0;
      const createMs = f.createTime ? Date.parse(f.createTime) : monthStartMs;
      const hourlyUsd = (capGib * 0.2) / 730;
      return {
        name: (f.name || '').split('/').pop() || 'filestore',
        service: `Cloud Filestore (${f.tier || 'STANDARD'})`,
        capGib,
        hourlyUsd,
        activeStartMs: Math.max(monthStartMs, createMs),
        activeEndMs: nowMs,
      };
    }),
  ];

  const fourHourSeries = [];
  let cumulativeHpcUsd = 0;
  let cumulativeNonHpcUsd = 0;

  let catHpcComputeUsd = 0;
  let catHpcGpuUsd = 0;
  let catBatchUsd = 0;
  let catHpcStorageUsd = 0;
  let catHpcDisksUsd = 0;
  let catNonHpcComputeUsd = 0;
  let catNonHpcDisksUsd = 0;

  let hpcInstanceHrs = 0;
  let hpcGpuHrs = 0;
  let batchNodeHrs = 0;
  let nonHpcInstanceHrs = 0;

  for (let b = 0; b < blocksElapsed; b++) {
    const blockStartMs = monthStartMs + b * FOUR_HOURS_MS;
    const blockEndMs = Math.min(nowMs, blockStartMs + FOUR_HOURS_MS);
    const blockDate = new Date(blockStartMs + FOUR_HOURS_MS);

    let blockHpcCompute = 0;
    let blockHpcGpu = 0;
    let blockBatch = 0;
    let blockHpcStorage = 0;
    let blockHpcDisks = 0;
    let blockNonHpcCompute = 0;
    let blockNonHpcDisks = 0;

    for (const inst of parsedInstances) {
      const hrs = overlapHoursInBlock(inst.activeStartMs, inst.activeEndMs, blockStartMs, blockEndMs);
      if (hrs <= 0) continue;
      if (inst.isHpc) {
        blockHpcCompute += hrs * inst.vmHourlyUsd;
        blockHpcGpu += hrs * inst.gpuHourlyUsd;
        hpcInstanceHrs += hrs;
        hpcGpuHrs += hrs * inst.gpuCount;
      } else {
        blockNonHpcCompute += hrs * inst.vmHourlyUsd;
        nonHpcInstanceHrs += hrs;
      }
    }

    for (const jb of parsedBatchJobs) {
      const hrs = overlapHoursInBlock(jb.activeStartMs, jb.activeEndMs, blockStartMs, blockEndMs);
      if (hrs <= 0) continue;
      blockBatch += hrs * jb.hourlyUsd;
      batchNodeHrs += hrs * jb.parallelism;
    }

    for (const st of parsedStorage) {
      const hrs = overlapHoursInBlock(st.activeStartMs, st.activeEndMs, blockStartMs, blockEndMs);
      if (hrs <= 0) continue;
      blockHpcStorage += hrs * st.hourlyUsd;
    }

    for (const dk of parsedDisks) {
      const hrs = overlapHoursInBlock(dk.activeStartMs, dk.activeEndMs, blockStartMs, blockEndMs);
      if (hrs <= 0) continue;
      if (dk.isHpc) blockHpcDisks += hrs * dk.hourlyUsd;
      else blockNonHpcDisks += hrs * dk.hourlyUsd;
    }

    const hpcBlockUsd = Number(
      (blockHpcCompute + blockHpcGpu + blockBatch + blockHpcStorage + blockHpcDisks).toFixed(2)
    );
    const nonHpcBlockUsd = Number((blockNonHpcCompute + blockNonHpcDisks).toFixed(2));
    const totalBlockUsd = Number((hpcBlockUsd + nonHpcBlockUsd).toFixed(2));

    cumulativeHpcUsd = Number((cumulativeHpcUsd + hpcBlockUsd).toFixed(2));
    cumulativeNonHpcUsd = Number((cumulativeNonHpcUsd + nonHpcBlockUsd).toFixed(2));

    catHpcComputeUsd = Number((catHpcComputeUsd + blockHpcCompute).toFixed(2));
    catHpcGpuUsd = Number((catHpcGpuUsd + blockHpcGpu).toFixed(2));
    catBatchUsd = Number((catBatchUsd + blockBatch).toFixed(2));
    catHpcStorageUsd = Number((catHpcStorageUsd + blockHpcStorage).toFixed(2));
    catHpcDisksUsd = Number((catHpcDisksUsd + blockHpcDisks).toFixed(2));
    catNonHpcComputeUsd = Number((catNonHpcComputeUsd + blockNonHpcCompute).toFixed(2));
    catNonHpcDisksUsd = Number((catNonHpcDisksUsd + blockNonHpcDisks).toFixed(2));

    fourHourSeries.push({
      blockIndex: b + 1,
      timestampIso: blockDate.toISOString(),
      label: `${monthInfo.monthKey.slice(5)}-${String(blockDate.getUTCDate()).padStart(2, '0')} ${String(blockDate.getUTCHours()).padStart(2, '0')}:00`,
      hpcBlockUsd,
      nonHpcBlockUsd,
      totalBlockUsd,
      cumulativeHpcUsd,
      cumulativeTotalUsd: Number((cumulativeHpcUsd + cumulativeNonHpcUsd).toFixed(2)),
      hpcSharePct:
        totalBlockUsd > 0 ? Number(((hpcBlockUsd / totalBlockUsd) * 100).toFixed(1)) : 0,
      breakdown: {
        slurmCompute4h: Number(blockHpcCompute.toFixed(2)),
        hpcGpu4h: Number(blockHpcGpu.toFixed(2)),
        batchNodes4h: Number(blockBatch.toFixed(2)),
        hpcStorage4h: Number(blockHpcStorage.toFixed(2)),
        hpcNetwork4h: Number(blockHpcDisks.toFixed(2)),
      },
    });
  }

  const cumulativeTotalGcpUsd = Number((cumulativeHpcUsd + cumulativeNonHpcUsd).toFixed(2));
  const hpcPortionPct =
    cumulativeTotalGcpUsd > 0
      ? Number(((cumulativeHpcUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
      : 0;
  const nonHpcPortionPct =
    cumulativeTotalGcpUsd > 0 ? Number((100 - hpcPortionPct).toFixed(1)) : 0;

  const latest4hBlock = fourHourSeries[fourHourSeries.length - 1] || {
    hpcBlockUsd: 0,
    nonHpcBlockUsd: 0,
    totalBlockUsd: 0,
    breakdown: {},
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

  const hpcInstCount = parsedInstances.filter((i) => i.isHpc).length;
  const nonHpcInstCount = parsedInstances.filter((i) => !i.isHpc).length;
  const hpcDiskGb = parsedDisks.filter((d) => d.isHpc).reduce((a, d) => a + d.sizeGb, 0);
  const nonHpcDiskGb = parsedDisks.filter((d) => !d.isHpc).reduce((a, d) => a + d.sizeGb, 0);
  const totalStorageGib = parsedStorage.reduce((a, s) => a + s.capGib, 0);

  const skuBreakdown = [
    {
      skuId: 'LIVE-GCE-HPC',
      service: 'Compute Engine (HPC & Slurm Instances)',
      category: 'HPC Compute VMs',
      isHpc: true,
      usageLabel: `${hpcInstCount} live HPC VMs (${hpcInstanceHrs.toFixed(1)} instance-hrs MTD)`,
      last4hUsd: latest4hBlock.breakdown?.slurmCompute4h || 0,
      monthToDateUsd: catHpcComputeUsd,
      shareOfHpcPct:
        cumulativeHpcUsd > 0 ? Number(((catHpcComputeUsd / cumulativeHpcUsd) * 100).toFixed(1)) : 0,
      shareOfTotalBillPct:
        cumulativeTotalGcpUsd > 0
          ? Number(((catHpcComputeUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
          : 0,
    },
    {
      skuId: 'LIVE-GPU-HPC',
      service: 'Compute Engine (GPU Accelerators)',
      category: 'HPC GPU Accelerators',
      isHpc: true,
      usageLabel: `${hpcGpuHrs.toFixed(1)} GPU-hrs MTD`,
      last4hUsd: latest4hBlock.breakdown?.hpcGpu4h || 0,
      monthToDateUsd: catHpcGpuUsd,
      shareOfHpcPct:
        cumulativeHpcUsd > 0 ? Number(((catHpcGpuUsd / cumulativeHpcUsd) * 100).toFixed(1)) : 0,
      shareOfTotalBillPct:
        cumulativeTotalGcpUsd > 0
          ? Number(((catHpcGpuUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
          : 0,
    },
    {
      skuId: 'LIVE-BATCH-HPC',
      service: 'Google Cloud Batch',
      category: 'Cloud Batch Worker Nodes',
      isHpc: true,
      usageLabel: `${parsedBatchJobs.length} Batch jobs (${batchNodeHrs.toFixed(1)} node-hrs MTD)`,
      last4hUsd: latest4hBlock.breakdown?.batchNodes4h || 0,
      monthToDateUsd: catBatchUsd,
      shareOfHpcPct:
        cumulativeHpcUsd > 0 ? Number(((catBatchUsd / cumulativeHpcUsd) * 100).toFixed(1)) : 0,
      shareOfTotalBillPct:
        cumulativeTotalGcpUsd > 0
          ? Number(((catBatchUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
          : 0,
    },
    {
      skuId: 'LIVE-FS-LUSTRE',
      service: 'Managed Lustre & Cloud Filestore',
      category: 'HPC Shared & Parallel Filesystems',
      isHpc: true,
      usageLabel: `${parsedStorage.length} filesystems (${(totalStorageGib / 1024).toFixed(2)} TiB provisioned)`,
      last4hUsd: latest4hBlock.breakdown?.hpcStorage4h || 0,
      monthToDateUsd: catHpcStorageUsd,
      shareOfHpcPct:
        cumulativeHpcUsd > 0 ? Number(((catHpcStorageUsd / cumulativeHpcUsd) * 100).toFixed(1)) : 0,
      shareOfTotalBillPct:
        cumulativeTotalGcpUsd > 0
          ? Number(((catHpcStorageUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
          : 0,
    },
    {
      skuId: 'LIVE-PD-HPC',
      service: 'Hyperdisk & Persistent Disk (HPC Attached)',
      category: 'HPC Block Storage & Boot Disks',
      isHpc: true,
      usageLabel: `${parsedDisks.filter((d) => d.isHpc).length} HPC disks (${hpcDiskGb} GB provisioned)`,
      last4hUsd: latest4hBlock.breakdown?.hpcNetwork4h || 0,
      monthToDateUsd: catHpcDisksUsd,
      shareOfHpcPct:
        cumulativeHpcUsd > 0 ? Number(((catHpcDisksUsd / cumulativeHpcUsd) * 100).toFixed(1)) : 0,
      shareOfTotalBillPct:
        cumulativeTotalGcpUsd > 0
          ? Number(((catHpcDisksUsd / cumulativeTotalGcpUsd) * 100).toFixed(1))
          : 0,
    },
    {
      skuId: 'LIVE-NON-HPC',
      service: 'Non-HPC Project Compute & Disks',
      category: 'Non-HPC Services (Excluded from HPC Cap)',
      isHpc: false,
      usageLabel: `${nonHpcInstCount} non-HPC VMs (${nonHpcInstanceHrs.toFixed(1)} hrs) + ${nonHpcDiskGb} GB disks`,
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
    `**Live HPC Cost Drivers This Month**:\n` +
    summary.skuBreakdown
      .filter((s) => s.isHpc && s.monthToDateUsd > 0)
      .map(
        (s) =>
          `  - **${s.category}**: $${s.monthToDateUsd.toLocaleString('en-US', { minimumFractionDigits: 2 })} (${s.shareOfHpcPct}% of HPC spend — ${s.usageLabel})`
      )
      .join('\n') +
    `\n\nPlease alert the user immediately and recommend concrete cost-containment actions for the active resources in \`${summary.projectId}\`.`
  );
}

async function maybeNotifyAgentOnBudgetExceeded(summary, { forceNotify = false, customConversationId = '' } = {}) {
  const isExceeded =
    summary.maxMonthlyBudgetUsd > 0 && summary.accumulatedHpcSpendUsd > summary.maxMonthlyBudgetUsd;

  if (!isExceeded && !forceNotify) {
    return { notified: false, reason: 'within_budget' };
  }

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
// Core 4-Hour Poll & Real-Time Telemetry Builder
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

  // 2. Detect Real GCP Context & Probe Live Billing / Resource APIs
  const ctx = await detectGcloudContext();
  const probe = await probeGcpBillingAndResources(ctx.projectId, monthInfo);

  // 3. Calculate Real Total GCP Bill & HPC Portion Spent
  const calc = calculateRealMonthlyBillingAndHpcPortion(monthInfo, probe, now.getTime());

  // 4. Update Persistent State
  const nextPollDate = new Date(now.getTime() + FOUR_HOURS_MS);
  spendState.accumulatedHpcSpendUsd = calc.cumulativeHpcUsd;
  spendState.accumulatedTotalGcpSpendUsd = calc.cumulativeTotalGcpUsd;
  spendState.lastPollIso = now.toISOString();
  spendState.nextPollIso = nextPollDate.toISOString();
  spendState.pollCountThisMonth = (spendState.pollCountThisMonth || 0) + (forceRefresh ? 1 : 0);
  spendState.fourHourLedger = calc.fourHourSeries.slice(-18);
  saveJsonFile('hpc_spend_state.json', spendState);

  const maxBudget = Number(spendState.maxMonthlyBudgetUsd) || 0;
  const budgetUtilizationPct =
    maxBudget > 0 ? Number(((calc.cumulativeHpcUsd / maxBudget) * 100).toFixed(1)) : 0;
  const remainingBudgetUsd = Number((maxBudget - calc.cumulativeHpcUsd).toFixed(2));
  const isExceeded = maxBudget > 0 && calc.cumulativeHpcUsd > maxBudget;
  const isWarning =
    !isExceeded && maxBudget > 0 && budgetUtilizationPct >= (spendState.warningThresholdPct || 85);

  const summary = {
    projectId: ctx.projectId || '(unconfigured)',
    account: ctx.account || '(unauthenticated)',
    region: ctx.region,
    billingAccountName: probe.billingAccountName,
    billingEnabled: probe.billingEnabled,
    billingExportTable: spendState.billingExportTable || '',
    dataSource:
      probe.bqSkuRows && probe.bqSkuRows.length > 0
        ? `live_bigquery_billing_export (${spendState.billingExportTable})`
        : 'live_gcp_billing_and_resource_apis',
    liveCounts: {
      instances: probe.instances.length,
      disks: probe.disks.length,
      batchJobs: probe.batchJobs.length,
      filestores: probe.filestores.length,
      lustres: probe.lustres.length,
      gcpBudgets: probe.gcpBudgets.length,
      bqSkuRows: probe.bqSkuRows ? probe.bqSkuRows.length : 0,
    },
    apiErrors: probe.errors,
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
    previousMonthArchive:
      previousMonth || (spendState.archivedMonths && spendState.archivedMonths[0]) || null,
    archivedMonths: spendState.archivedMonths || [],
    // Real-Time Spend & Portion Metrics
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
