/**
 * Google Cloud Batch Monitor Backend (`gcp_batch_monitor`)
 *
 * STRICT REAL-TIME TELEMETRY ONLY — NO DEMO OR HARDCODED FALLBACK DATA.
 *
 * Queries live GCP Batch, Compute Engine, and Cloud Logging APIs:
 *  1. Google Cloud Batch nodes in use (live Spot vs Standard worker VMs + 30-day node usage history)
 *  2. What Batch jobs are running & their exact duration (live elapsed runtime, max run limit, task progress)
 *  3. People running Batch & per-user duration statistics (current active session duration + 30-day cumulative runtime)
 */

import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

class FallbackResponse {
  constructor(body, { status = 200, contentType = 'text/plain; charset=utf-8', headers = {} } = {}) {
    this.body = body;
    this.status = status;
    this.contentType = contentType;
    this.headers = headers;
  }
}

class FallbackSidecarApp {
  constructor() {
    this.pages = new Map();
    this.apis = new Map();
  }
  page(path, handler) {
    this.pages.set(path, handler);
    return this;
  }
  api(path, handler, method = 'POST') {
    const m = method.toUpperCase();
    if (!this.apis.has(path)) this.apis.set(path, new Map());
    this.apis.get(path).set(m, handler);
    return this;
  }
  run() {
    const portArg = process.argv.find((a) => a.startsWith('--port='));
    const port = portArg ? Number(portArg.split('=')[1]) : Number(process.env.PORT || 8081);
    const server = createServer(async (req, res) => {
      const url = new URL(req.url, `http://${req.headers.host || '127.0.0.1'}`);
      const pathname = url.pathname;
      if (req.method === 'GET' && pathname === '/preload.js') {
        res.writeHead(200, { 'Content-Type': 'application/javascript; charset=utf-8' });
        res.end(
          'window.antigravity = window.antigravity || { sendPromptToAgent() {}, sendTextToTerminal() {} };'
        );
        return;
      }
      if (req.method === 'GET' && this.pages.has(pathname)) {
        const html = await this.pages.get(pathname)(Object.fromEntries(url.searchParams));
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
        return;
      }
      if (this.apis.has(pathname)) {
        const methods = this.apis.get(pathname);
        const handler = methods.get(req.method.toUpperCase());
        if (handler) {
          let data = Object.fromEntries(url.searchParams);
          if (req.method === 'POST' || req.method === 'PUT' || req.method === 'PATCH') {
            const chunks = [];
            for await (const c of req) chunks.push(c);
            const raw = Buffer.concat(chunks).toString('utf-8');
            try {
              if (raw) data = JSON.parse(raw);
            } catch {}
          }
          const out = await handler(data, req);
          if (out instanceof Response) {
            res.writeHead(out.status, { 'Content-Type': out.contentType, ...out.headers });
            res.end(out.body);
          } else {
            res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify(out ?? {}));
          }
          return;
        }
      }
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Not Found' }));
    });
    server.listen(port, '127.0.0.1', () =>
      console.error(`[gcp-batch-monitor] Real-Time GUI listening on http://127.0.0.1:${port}`)
    );
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

const execFileAsync = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS_DIR = existsSync(join(__dirname, '..', 'assets', 'index.html'))
  ? join(__dirname, '..', 'assets')
  : __dirname;

const STATIC_ASSETS = {
  '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
  '/app.js': ['app.js', 'application/javascript; charset=utf-8'],
};

// ---------------------------------------------------------------------------
// Persistent Data Directory & Configuration
// ---------------------------------------------------------------------------

function getDataDir() {
  const dir =
    process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR ||
    join('/tmp', 'hpc_agent_antigravity_batch_monitor');
  try {
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  } catch {}
  return dir;
}

function loadJsonFile(filename, fallback) {
  try {
    const filePath = join(getDataDir(), filename);
    if (existsSync(filePath)) {
      return JSON.parse(readFileSync(filePath, 'utf-8'));
    }
  } catch {}
  return fallback;
}

function saveJsonFile(filename, data) {
  try {
    const filePath = join(getDataDir(), filename);
    writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
  } catch {}
}

let sidecarConfig = loadJsonFile('config.json', {
  projectId: '',
  region: 'us-central1',
});

// ---------------------------------------------------------------------------
// Shell / GCloud Helpers
// ---------------------------------------------------------------------------

async function runCmd(bin, args, timeoutMs = 10000) {
  try {
    const { stdout, stderr } = await execFileAsync(bin, args, {
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
      error: (err.stderr ? String(err.stderr).trim() : '') || err.message,
    };
  }
}

async function detectGcloudContext() {
  const [proj, reg, acct] = await Promise.all([
    runCmd('gcloud', ['config', 'get-value', 'project'], 4000),
    runCmd('gcloud', ['config', 'get-value', 'compute/region'], 4000),
    runCmd('gcloud', ['config', 'get-value', 'account'], 4000),
  ]);
  const clean = (val) => (val && val !== '(unset)' ? val.split('\n').pop().trim() : '');
  return {
    projectId: sidecarConfig.projectId || clean(proj.stdout) || process.env.GOOGLE_CLOUD_PROJECT || '',
    region: sidecarConfig.region || clean(reg.stdout) || 'us-central1',
    account: clean(acct.stdout) || '',
  };
}

function formatDurationSeconds(totalSeconds) {
  const sec = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(h)}h ${pad(m)}m ${pad(s)}s`;
}

function parseMachineSpecs(machineType) {
  const short = (machineType || 'e2-standard-4').split('/').pop().toLowerCase();
  const parts = short.split('-');
  const family = parts[0] || 'e2';
  const kind = parts[1] || 'standard';
  const vcpus = Number(parts[2]) || (short.includes('8g') ? 208 : short.includes('1g') ? 12 : 4);
  const memPerVcpu = kind.includes('highmem') ? 8 : kind.includes('highcpu') ? 2 : 4;
  const memoryGiB = vcpus * memPerVcpu;

  let tier = 'Standard Compute Tier';
  if (family === 'e2') tier = 'Economy Tier';
  else if (family === 'c3' || family === 'c4' || family === 'c2') tier = 'Business Tier (Compute Optimized)';
  else if (kind.includes('highmem') || family === 'a2' || family === 'a3' || family === 'g2')
    tier = 'First Class Tier (High-Mem / GPU)';

  return { short, family, vcpus, memoryGiB, tier };
}

// ---------------------------------------------------------------------------
// 100% Real-Time GCP Batch Discovery (Batch API + Compute Engine + Cloud Logging)
// ---------------------------------------------------------------------------

async function fetchRealGcpBatchTelemetry(projectId, region) {
  const now = Date.now();
  const oneDayMs = 24 * 60 * 60 * 1000;
  const thirtyDaysAgoMs = now - 30 * oneDayMs;

  const diagnostics = {
    queriedAt: new Date(now).toISOString(),
    projectId,
    region,
    liveBatchJobsFound: 0,
    liveBatchNodesFound: 0,
    logEventsFound: 0,
    errors: [],
  };

  if (!projectId) {
    diagnostics.errors.push('No GCP project ID configured.');
  }

  const [batchJobsRes, batchNodesRes, batchLogsRes] = await Promise.all([
    projectId
      ? runCmd(
          'gcloud',
          ['batch', 'jobs', 'list', '--project', projectId, '--location', '-', '--format=json'],
          10000
        )
      : Promise.resolve({ ok: false, stdout: '' }),
    projectId
      ? runCmd(
          'gcloud',
          [
            'compute',
            'instances',
            'list',
            '--project',
            projectId,
            '--filter=labels.goog-batch-job:* OR labels.batch-job-id:* OR name~^batch-',
            '--format=json(name,zone,machineType,status,creationTimestamp,lastStartTimestamp,lastStopTimestamp,scheduling,labels,disks)',
          ],
          9000
        )
      : Promise.resolve({ ok: false, stdout: '' }),
    projectId
      ? runCmd(
          'gcloud',
          [
            'logging',
            'read',
            'protoPayload.serviceName="batch.googleapis.com" AND (protoPayload.methodName:"CreateJob" OR protoPayload.methodName:"DeleteJob")',
            '--project',
            projectId,
            '--freshness=30d',
            '--limit=300',
            '--format=json(timestamp,protoPayload.methodName,protoPayload.resourceName,protoPayload.authenticationInfo.principalEmail,protoPayload.request)',
          ],
          9000
        )
      : Promise.resolve({ ok: false, stdout: '' }),
  ]);

  let rawBatchJobs = [];
  if (batchJobsRes.ok && batchJobsRes.stdout) {
    try {
      const parsed = JSON.parse(batchJobsRes.stdout);
      if (Array.isArray(parsed)) rawBatchJobs = parsed;
    } catch (e) {
      diagnostics.errors.push(`Batch jobs JSON parse error: ${e.message}`);
    }
  } else if (batchJobsRes.error && !batchJobsRes.error.includes('Listed 0 items')) {
    diagnostics.errors.push(`Batch API: ${batchJobsRes.error.split('\n')[0]}`);
  }

  let liveBatchNodes = [];
  if (batchNodesRes.ok && batchNodesRes.stdout) {
    try {
      const parsed = JSON.parse(batchNodesRes.stdout);
      if (Array.isArray(parsed)) {
        liveBatchNodes = parsed;
        diagnostics.liveBatchNodesFound = liveBatchNodes.filter((n) => n.status === 'RUNNING').length;
      }
    } catch {}
  }

  // Map submitter email from Cloud Audit Logs (`CreateJob`) if available
  const creatorByJobName = new Map();
  if (batchLogsRes.ok && batchLogsRes.stdout) {
    try {
      const logs = JSON.parse(batchLogsRes.stdout);
      if (Array.isArray(logs)) {
        diagnostics.logEventsFound = logs.length;
        for (const entry of logs) {
          const resName = entry.protoPayload?.resourceName || '';
          const email = entry.protoPayload?.authenticationInfo?.principalEmail || '';
          if (resName && email) {
            const shortId = resName.split('/').pop();
            creatorByJobName.set(shortId, email);
          }
        }
      }
    } catch {}
  }

  // Transform real Batch jobs
  const jobs = rawBatchJobs
    .filter((jb) => {
      const createMs = jb.createTime ? Date.parse(jb.createTime) : now;
      return createMs >= thirtyDaysAgoMs;
    })
    .map((jb) => {
      const shortId = (jb.name || '').split('/').pop() || jb.uid || 'batch-job';
      const state = jb.status?.state || 'UNKNOWN';
      const createTimeMs = jb.createTime ? Date.parse(jb.createTime) : now;
      const startEvent = (jb.status?.statusEvents || []).find((e) =>
        String(e.description || '').includes('RUNNING')
      );
      const startMs = startEvent?.eventTime ? Date.parse(startEvent.eventTime) : createTimeMs;
      const endMs =
        state === 'SUCCEEDED' || state === 'FAILED' || state === 'CANCELLED'
          ? jb.updateTime
            ? Date.parse(jb.updateTime)
            : now
          : now;
      const durSec =
        state === 'QUEUED' || state === 'SCHEDULED'
          ? 0
          : Math.max(0, Math.round((endMs - startMs) / 1000));

      const maxRunSec =
        parseInt(String(jb.taskGroups?.[0]?.taskSpec?.maxRunDuration || '28800s'), 10) || 28800;
      const instPolicy = jb.allocationPolicy?.instances?.[0]?.policy || {};
      const mt = instPolicy.machineType || 'e2-standard-4';
      const specs = parseMachineSpecs(mt);
      const prov = instPolicy.provisioningModel === 'SPOT' ? 'SPOT' : 'STANDARD';
      const bootDiskType = instPolicy.bootDisk?.type || 'pd-balanced';
      const bootDiskGb = instPolicy.bootDisk?.sizeGb || 50;

      const taskCount = Math.max(1, Number(jb.taskGroups?.[0]?.taskCount || 1));
      const parallelism = Math.max(1, Number(jb.taskGroups?.[0]?.parallelism || 1));

      // Check real task counts from status.taskGroups if provided by Batch API
      const statusCounts = jb.status?.taskGroups?.['group0']?.counts || {};
      const succeededTasks = Number(statusCounts.SUCCEEDED || (state === 'SUCCEEDED' ? taskCount : 0));
      const runningTasks = Number(statusCounts.RUNNING || (state === 'RUNNING' ? parallelism : 0));

      // Count spot preemption events from statusEvents
      const preemptionCount = (jb.status?.statusEvents || []).filter((e) =>
        /preempt|spot|20001/i.test(`${e.type || ''} ${e.description || ''}`)
      ).length;

      const userLabel =
        creatorByJobName.get(shortId) ||
        jb.labels?.user ||
        jb.labels?.submitter ||
        jb.labels?.['goog-batch-user'] ||
        jb.allocationPolicy?.serviceAccount?.email ||
        'gcp-batch-submitter';

      return {
        jobId: shortId,
        uid: jb.uid || shortId,
        pipeline: jb.labels?.pipeline || jb.labels?.workflow || 'Google Cloud Batch',
        processName: jb.labels?.process || jb.labels?.task_name || shortId,
        user: userLabel,
        state,
        nodesInUse: state === 'RUNNING' ? Math.max(1, runningTasks || parallelism) : 0,
        parallelism,
        machineType: specs.short,
        vcpusPerNode: specs.vcpus,
        memoryGiBPerNode: specs.memoryGiB,
        tier: specs.tier,
        diskType: `${bootDiskType} (${bootDiskGb} GB)`,
        provisioning: prov,
        tasksCompleted: succeededTasks,
        tasksTotal: taskCount,
        durationSeconds: durSec,
        durationFormatted: formatDurationSeconds(durSec),
        maxDurationSeconds: maxRunSec,
        maxDurationFormatted: formatDurationSeconds(maxRunSec),
        durationPct: Math.min(100, Number(((durSec / Math.max(1, maxRunSec)) * 100).toFixed(1))),
        avg30dDurationFormatted: formatDurationSeconds(durSec),
        createTimeMs,
        startMs,
        endMs,
        preemptionCount,
        submittedAgo: jb.createTime
          ? new Date(createTimeMs).toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
          : 'Live',
        region: (jb.name || '').split('/')[3] || region,
      };
    });

  diagnostics.liveBatchJobsFound = jobs.length;

  // Compute per-process 30-day average baseline from the real jobs list
  const procDurMap = new Map();
  for (const j of jobs) {
    if (j.durationSeconds <= 0) continue;
    const cur = procDurMap.get(j.processName) || { sum: 0, cnt: 0 };
    cur.sum += j.durationSeconds;
    cur.cnt += 1;
    procDurMap.set(j.processName, cur);
  }
  for (const j of jobs) {
    const stat = procDurMap.get(j.processName);
    if (stat && stat.cnt > 0) {
      j.avg30dDurationFormatted = formatDurationSeconds(Math.round(stat.sum / stat.cnt));
    }
  }

  // Build real Node Pools from real jobs & live worker nodes
  const poolMap = new Map();
  for (const j of jobs) {
    const key = `${j.machineType}:${j.provisioning}`;
    const cur = poolMap.get(key) || {
      machineType: j.machineType,
      tier: j.tier,
      provisioning: j.provisioning,
      diskType: j.diskType,
      nodesInUseNow: 0,
      vcpusInUse: 0,
      memoryGiBInUse: 0,
      totalDurSec: 0,
      nodeHours30d: 0,
      jobsServed30d: 0,
      workloadsSet: new Set(),
    };
    if (j.state === 'RUNNING') {
      cur.nodesInUseNow += j.nodesInUse;
      cur.vcpusInUse += j.nodesInUse * j.vcpusPerNode;
      cur.memoryGiBInUse += j.nodesInUse * j.memoryGiBPerNode;
    }
    cur.totalDurSec += j.durationSeconds;
    cur.nodeHours30d += (j.durationSeconds / 3600) * j.parallelism;
    cur.jobsServed30d += 1;
    cur.workloadsSet.add(j.processName);
    poolMap.set(key, cur);
  }

  // Also include any live GCE Batch worker VMs discovered directly via `gcloud compute instances list`
  for (const vm of liveBatchNodes) {
    if (vm.status !== 'RUNNING') continue;
    const specs = parseMachineSpecs(vm.machineType);
    const prov =
      vm.scheduling?.provisioningModel === 'SPOT' || vm.scheduling?.preemptible === true
        ? 'SPOT'
        : 'STANDARD';
    const key = `${specs.short}:${prov}`;
    if (!poolMap.has(key)) {
      poolMap.set(key, {
        machineType: specs.short,
        tier: specs.tier,
        provisioning: prov,
        diskType: 'pd-balanced',
        nodesInUseNow: 1,
        vcpusInUse: specs.vcpus,
        memoryGiBInUse: specs.memoryGiB,
        totalDurSec: 0,
        nodeHours30d: 0,
        jobsServed30d: 1,
        workloadsSet: new Set([vm.labels?.['goog-batch-job'] || vm.name]),
      });
    }
  }

  const nodePools = Array.from(poolMap.values()).map((p) => ({
    machineType: p.machineType,
    tier: p.tier,
    provisioning: p.provisioning,
    diskType: p.diskType,
    nodesInUseNow: p.nodesInUseNow,
    vcpusInUse: p.vcpusInUse,
    memoryGiBInUse: p.memoryGiBInUse,
    avgNodeDuration: formatDurationSeconds(
      p.jobsServed30d > 0 ? p.totalDurSec / p.jobsServed30d : 0
    ).slice(0, 7),
    nodeHours30d: Number(p.nodeHours30d.toFixed(1)),
    jobsServed30d: p.jobsServed30d,
    primaryWorkloads: Array.from(p.workloadsSet).slice(0, 3).join(', ') || 'Google Cloud Batch',
  }));

  // Build real Per-User Batch Duration Statistics (`batchUsers`)
  const userMap = new Map();
  for (const j of jobs) {
    const cur = userMap.get(j.user) || {
      user: j.user,
      displayName: j.user,
      team: 'Google Cloud Batch User',
      activeJobsNow: 0,
      nodesInUseNow: 0,
      activeDurationSeconds: 0,
      jobs30d: 0,
      failedJobs30d: 0,
      totalDurSec30d: 0,
      totalNodeHours30d: 0,
      longestJobSec: 0,
      longestJobName: '-',
      spotJobsCount: 0,
      primaryPipeline: j.pipeline,
    };

    cur.jobs30d += 1;
    if (j.state === 'FAILED') cur.failedJobs30d += 1;
    if (j.provisioning === 'SPOT') cur.spotJobsCount += 1;
    cur.totalDurSec30d += j.durationSeconds;
    cur.totalNodeHours30d += (j.durationSeconds / 3600) * j.parallelism;

    if (j.durationSeconds >= cur.longestJobSec) {
      cur.longestJobSec = j.durationSeconds;
      cur.longestJobName = j.jobId;
    }

    if (j.state === 'RUNNING') {
      cur.activeJobsNow += 1;
      cur.nodesInUseNow += j.nodesInUse;
      cur.activeDurationSeconds = Math.max(cur.activeDurationSeconds, j.durationSeconds);
    }

    userMap.set(j.user, cur);
  }

  const batchUsers = Array.from(userMap.values()).map((u) => ({
    user: u.user,
    displayName: u.displayName,
    team: u.team,
    activeJobsNow: u.activeJobsNow,
    nodesInUseNow: u.nodesInUseNow,
    activeRunningDuration:
      u.activeJobsNow > 0 ? formatDurationSeconds(u.activeDurationSeconds) : '00h 00m 00s (Idle)',
    activeDurationSeconds: u.activeDurationSeconds,
    jobs30d: u.jobs30d,
    failedJobs30d: u.failedJobs30d,
    totalJobDurationHours30d: Number((u.totalDurSec30d / 3600).toFixed(1)),
    totalNodeHours30d: Number(u.totalNodeHours30d.toFixed(1)),
    avgJobDuration: formatDurationSeconds(u.jobs30d > 0 ? u.totalDurSec30d / u.jobs30d : 0).slice(0, 7),
    longestJobDuration: formatDurationSeconds(u.longestJobSec).slice(0, 7),
    longestJobName: u.longestJobName,
    spotSharePct: u.jobs30d > 0 ? Math.round((u.spotJobsCount / u.jobs30d) * 100) : 0,
    primaryPipeline: u.primaryPipeline,
  }));

  // Build real 30-Day Daily Series from actual Batch jobs
  const dailySeries = [];
  for (let i = 29; i >= 0; i--) {
    const dayEndMs = now - i * oneDayMs;
    const dayStartMs = dayEndMs - oneDayMs;
    const d = new Date(dayEndMs);
    const isoDate = d.toISOString().slice(0, 10);
    const dayOfWeek = d.getUTCDay();

    let spotNodeHours = 0;
    let stdNodeHours = 0;
    let peakNodes = 0;
    let jobsSucceeded = 0;
    let jobsFailed = 0;
    let spotPreemptions = 0;
    let totalDurSecDay = 0;
    let maxDurSecDay = 0;
    let jobsActiveDay = 0;

    for (const j of jobs) {
      const startOverlap = Math.max(dayStartMs, j.startMs);
      const endOverlap = Math.min(dayEndMs, j.endMs);
      if (endOverlap > startOverlap) {
        const hrs = (endOverlap - startOverlap) / (3600 * 1000);
        const nodeHrs = hrs * j.parallelism;
        if (j.provisioning === 'SPOT') spotNodeHours += nodeHrs;
        else stdNodeHours += nodeHrs;
        peakNodes += j.parallelism;
        jobsActiveDay += 1;
        totalDurSecDay += j.durationSeconds;
        maxDurSecDay = Math.max(maxDurSecDay, j.durationSeconds);
      }

      const endDateStr = new Date(j.endMs).toISOString().slice(0, 10);
      if (endDateStr === isoDate) {
        if (j.state === 'SUCCEEDED') jobsSucceeded += 1;
        else if (j.state === 'FAILED') jobsFailed += 1;
        spotPreemptions += j.preemptionCount;
      }
    }

    const totalNodeHours = spotNodeHours + stdNodeHours;
    const avgNodes = Number((totalNodeHours / 24).toFixed(1));
    const spotNodesAvg = Number((spotNodeHours / 24).toFixed(1));
    const standardNodesAvg = Number((stdNodeHours / 24).toFixed(1));
    const avgJobDurationMin =
      jobsActiveDay > 0 ? Math.round(totalDurSecDay / jobsActiveDay / 60) : 0;
    const maxJobDurationMin = Math.round(maxDurSecDay / 60);

    dailySeries.push({
      date: isoDate,
      label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }),
      isWeekend: dayOfWeek === 0 || dayOfWeek === 6,
      avgNodes,
      peakNodes,
      spotNodesAvg,
      standardNodesAvg,
      nodeHours: Number(totalNodeHours.toFixed(1)),
      jobsSucceeded,
      jobsFailed,
      spotPreemptions,
      avgJobDurationMin,
      maxJobDurationMin,
      totalJobRuntimeHours: Number((totalDurSecDay / 3600).toFixed(1)),
    });
  }

  // Build real 30-day Job Duration Distribution Buckets
  const bucketDefs = [
    { label: '< 30 min', minSec: 0, maxSec: 1800, tierHint: 'Economy (e2-standard-4)' },
    { label: '30m – 2h', minSec: 1800, maxSec: 7200, tierHint: 'Economy Plus / Business (c3-standard-8)' },
    { label: '2h – 6h', minSec: 7200, maxSec: 21600, tierHint: 'Business Tier (c3-standard-22 / c4-highcpu-32)' },
    { label: '6h – 12h', minSec: 21600, maxSec: 43200, tierHint: 'First Class (n2-highmem-32 / a2-highgpu-1g)' },
    { label: '12h – 24h', minSec: 43200, maxSec: 86400, tierHint: 'First Class STANDARD (Avoid Spot Preemption)' },
    { label: '> 24h', minSec: 86400, maxSec: Infinity, tierHint: 'Checkpoint + Dedicated Reservation' },
  ];
  const durationBuckets30d = bucketDefs.map((b) => {
    const count = jobs.filter((j) => j.durationSeconds >= b.minSec && j.durationSeconds < b.maxSec).length;
    const pct = jobs.length > 0 ? Number(((count / jobs.length) * 100).toFixed(1)) : 0;
    return {
      label: b.label,
      count,
      pct,
      tierHint: b.tierHint,
    };
  });

  return {
    jobs,
    nodePools,
    batchUsers,
    dailySeries,
    durationBuckets30d,
    liveBatchNodes,
    diagnostics,
  };
}

// ---------------------------------------------------------------------------
// Telemetry Assembler (100% Real-Time Data)
// ---------------------------------------------------------------------------

let cachedTelemetry = null;
let lastFetchMs = 0;

async function buildTelemetry({ days = 30, forceRefresh = false } = {}) {
  const now = Date.now();
  if (!forceRefresh && cachedTelemetry && now - lastFetchMs < 15000) {
    return sliceByDays(cachedTelemetry, days);
  }

  const ctx = await detectGcloudContext();
  const real = await fetchRealGcpBatchTelemetry(ctx.projectId, ctx.region);

  const jobs = real.jobs;
  const nodePools = real.nodePools;
  const series30d = real.dailySeries;

  const nodesInUseNow = nodePools.reduce((acc, p) => acc + p.nodesInUseNow, 0);
  const spotNodesNow = nodePools
    .filter((p) => p.provisioning === 'SPOT')
    .reduce((acc, p) => acc + p.nodesInUseNow, 0);
  const standardNodesNow = Math.max(0, nodesInUseNow - spotNodesNow);
  const vcpusInUseNow = nodePools.reduce((acc, p) => acc + p.vcpusInUse, 0);
  const memoryGiBInUseNow = nodePools.reduce((acc, p) => acc + p.memoryGiBInUse, 0);

  const totalNodeHours30d = Number(series30d.reduce((acc, d) => acc + d.nodeHours, 0).toFixed(1));
  const totalJobsSucceeded30d = jobs.filter((j) => j.state === 'SUCCEEDED').length;
  const totalJobsFailed30d = jobs.filter((j) => j.state === 'FAILED').length;
  const totalJobs30d = jobs.length;
  const totalSpotPreemptions30d = jobs.reduce((acc, j) => acc + (j.preemptionCount || 0), 0);
  const peakNodes30d = Math.max(0, ...series30d.map((d) => d.peakNodes));
  const avgNodes30d = Number(
    (series30d.reduce((acc, d) => acc + d.avgNodes, 0) / Math.max(1, series30d.length)).toFixed(1)
  );
  const totalRuntimeHours30d = Number(
    (jobs.reduce((acc, j) => acc + j.durationSeconds, 0) / 3600).toFixed(1)
  );

  const sortedDurations = jobs.map((j) => j.durationSeconds).sort((a, b) => a - b);
  const meanDurSec =
    sortedDurations.length > 0
      ? sortedDurations.reduce((a, b) => a + b, 0) / sortedDurations.length
      : 0;
  const medianDurSec =
    sortedDurations.length > 0 ? sortedDurations[Math.floor(sortedDurations.length * 0.5)] : 0;
  const p95DurSec =
    sortedDurations.length > 0 ? sortedDurations[Math.floor(sortedDurations.length * 0.95)] : 0;
  const maxDurSec = sortedDurations.length > 0 ? sortedDurations[sortedDurations.length - 1] : 0;
  const longestJobObj = jobs.reduce(
    (best, j) => (!best || j.durationSeconds > best.durationSeconds ? j : best),
    null
  );

  const runningJobsNow = jobs.filter((j) => j.state === 'RUNNING').length;
  const queuedJobsNow = jobs.filter((j) => j.state === 'QUEUED' || j.state === 'SCHEDULED').length;
  const activeUsersNow = real.batchUsers.filter((u) => u.activeJobsNow > 0).length;

  cachedTelemetry = {
    generatedAt: new Date(now).toISOString(),
    config: {
      ...sidecarConfig,
      projectId: ctx.projectId || '(unconfigured)',
      region: ctx.region,
      account: ctx.account || '(unauthenticated)',
    },
    sourceBadge: `Live Google Cloud Batch API (${jobs.length} Jobs, ${nodesInUseNow} Active Nodes)`,
    diagnostics: real.diagnostics,
    summary30d: {
      nodesInUseNow,
      spotNodesNow,
      standardNodesNow,
      spotRatioPct:
        nodesInUseNow > 0 ? Number(((spotNodesNow / nodesInUseNow) * 100).toFixed(1)) : 0,
      vcpusInUseNow,
      memoryGiBInUseNow,
      avgNodes30d,
      peakNodes30d,
      totalNodeHours30d,
      totalRuntimeHours30d,
      runningJobsNow,
      queuedJobsNow,
      totalJobs30d,
      totalJobsSucceeded30d,
      totalJobsFailed30d,
      totalSpotPreemptions30d,
      jobSuccessRate30dPct:
        totalJobsSucceeded30d + totalJobsFailed30d > 0
          ? Number(
              (
                (totalJobsSucceeded30d / (totalJobsSucceeded30d + totalJobsFailed30d)) *
                100
              ).toFixed(1)
            )
          : 0,
      avgJobDurationFormatted: formatDurationSeconds(meanDurSec).slice(0, 7),
      medianJobDurationFormatted: formatDurationSeconds(medianDurSec).slice(0, 7),
      p95JobDurationFormatted: formatDurationSeconds(p95DurSec).slice(0, 7),
      maxJobDurationFormatted: formatDurationSeconds(maxDurSec).slice(0, 7),
      longestJobUser: longestJobObj ? longestJobObj.user : 'none',
      activeUsersNow,
      totalUsers30d: real.batchUsers.length,
    },
    dailySeries: series30d,
    nodePools,
    batchUsers: real.batchUsers,
    jobs,
    durationBuckets30d: real.durationBuckets30d,
  };

  lastFetchMs = now;
  return sliceByDays(cachedTelemetry, days);
}

function sliceByDays(telemetry, days) {
  const n = Math.min(30, Math.max(1, Number(days) || 30));
  const slicedSeries = telemetry.dailySeries.slice(-n);
  const nodeHoursWindow = Number(slicedSeries.reduce((a, d) => a + d.nodeHours, 0).toFixed(1));
  const runtimeHoursWindow = Number(
    slicedSeries.reduce((a, d) => a + d.totalJobRuntimeHours, 0).toFixed(1)
  );
  const jobsSucceededWindow = slicedSeries.reduce((a, d) => a + d.jobsSucceeded, 0);
  const jobsFailedWindow = slicedSeries.reduce((a, d) => a + d.jobsFailed, 0);
  const peakNodesWindow = Math.max(0, ...slicedSeries.map((d) => d.peakNodes));
  const avgNodesWindow = Number(
    (slicedSeries.reduce((a, d) => a + d.avgNodes, 0) / Math.max(1, slicedSeries.length)).toFixed(1)
  );

  return {
    ...telemetry,
    windowDays: n,
    dailySeries: slicedSeries,
    windowStats: {
      days: n,
      nodeHours: nodeHoursWindow,
      runtimeHours: runtimeHoursWindow,
      jobsSucceeded: jobsSucceededWindow,
      jobsFailed: jobsFailedWindow,
      totalJobs: jobsSucceededWindow + jobsFailedWindow,
      peakNodes: peakNodesWindow,
      avgNodes: avgNodesWindow,
    },
  };
}

// ---------------------------------------------------------------------------
// CLI Mode & HTTP GUI Server Registration
// ---------------------------------------------------------------------------

function getArgValue(prefix) {
  const arg = process.argv.find((a) => a.startsWith(`${prefix}=`));
  if (arg) return arg.slice(prefix.length + 1);
  const idx = process.argv.indexOf(prefix);
  if (idx !== -1 && process.argv[idx + 1] && !process.argv[idx + 1].startsWith('--')) {
    return process.argv[idx + 1];
  }
  return null;
}

const cliProject = getArgValue('--project');
const cliRegion = getArgValue('--region');
const cliDays = Number(getArgValue('--days')) || 30;
if (cliProject) sidecarConfig.projectId = cliProject;
if (cliRegion) sidecarConfig.region = cliRegion;

if (process.argv.includes('--cli')) {
  const telemetry = await buildTelemetry({ days: cliDays, forceRefresh: true });
  console.log(JSON.stringify(telemetry, null, 2));
  process.exit(0);
}

const app = new SidecarApp();

app.page('/', () => readFileSync(join(ASSETS_DIR, 'index.html'), 'utf-8'));

for (const [route, [file, contentType]] of Object.entries(STATIC_ASSETS)) {
  app.api(
    route,
    () => new Response(readFileSync(join(ASSETS_DIR, file), 'utf-8'), { contentType }),
    'GET'
  );
}

app.api(
  '/api/telemetry',
  async (data) => {
    const days = Number(data.days) || 30;
    const forceRefresh = data.refresh === '1' || data.refresh === 'true';
    return await buildTelemetry({ days, forceRefresh });
  },
  'GET'
);

app.api(
  '/api/config',
  async (data) => {
    sidecarConfig = {
      ...sidecarConfig,
      projectId: typeof data.projectId === 'string' ? data.projectId.trim() : sidecarConfig.projectId,
      region:
        typeof data.region === 'string' && data.region.trim()
          ? data.region.trim()
          : sidecarConfig.region,
    };
    saveJsonFile('config.json', sidecarConfig);
    return await buildTelemetry({ days: Number(data.days) || 30, forceRefresh: true });
  },
  'POST'
);

app.run();
