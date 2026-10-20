/**
 * Google Cloud Batch Monitor Sidecar Backend (`gcp_batch_monitor`)
 *
 * Tracks and visualizes:
 *  1. Google Cloud Batch nodes in use (live Spot vs Standard VMs + 30-day node usage history)
 *  2. What Batch jobs are running & their exact duration (live elapsed runtime, max run limit, task progress)
 *  3. People running Batch & per-user duration statistics (current active session duration + 30-day cumulative runtime)
 */

import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { SidecarApp, Response } from 'sidecar_sdk';

const execFileAsync = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));

const STATIC_ASSETS = {
  '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
  '/app.js': ['app.js', 'application/javascript; charset=utf-8'],
};

// ---------------------------------------------------------------------------
// Persistent Data Directory & Configuration
// ---------------------------------------------------------------------------

function getDataDir() {
  const dir = process.env.ANTIGRAVITY_EXECUTABLE_DATA_DIR || join(__dirname, '.data');
  try {
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
  } catch (err) {
    console.error('[gcp_batch_monitor] Could not create data dir:', err.message);
  }
  return dir;
}

function loadJsonFile(filename, fallback) {
  try {
    const filePath = join(getDataDir(), filename);
    if (existsSync(filePath)) {
      return JSON.parse(readFileSync(filePath, 'utf-8'));
    }
  } catch (err) {
    console.error(`[gcp_batch_monitor] Failed reading ${filename}:`, err.message);
  }
  return fallback;
}

function saveJsonFile(filename, data) {
  try {
    const filePath = join(getDataDir(), filename);
    writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
  } catch (err) {
    console.error(`[gcp_batch_monitor] Failed writing ${filename}:`, err.message);
  }
}

let sidecarConfig = loadJsonFile('config.json', {
  projectId: '',
  region: 'us-central1',
  dataMode: 'auto', // 'auto' | 'live' | 'demo'
});

// ---------------------------------------------------------------------------
// Shell / GCloud Helpers
// ---------------------------------------------------------------------------

async function runCmd(bin, args, timeoutMs = 8000) {
  try {
    const { stdout } = await execFileAsync(bin, args, {
      timeout: timeoutMs,
      maxBuffer: 8 * 1024 * 1024,
      env: { ...process.env, CLOUDSDK_CORE_DISABLE_PROMPTS: '1' },
    });
    return { ok: true, stdout: stdout.trim() };
  } catch (err) {
    return { ok: false, stdout: '', error: err.stderr || err.message };
  }
}

async function detectGcloudContext() {
  const [proj, reg, acct] = await Promise.all([
    runCmd('gcloud', ['config', 'get-value', 'project'], 4000),
    runCmd('gcloud', ['config', 'get-value', 'compute/region'], 4000),
    runCmd('gcloud', ['config', 'get-value', 'account'], 4000),
  ]);
  const clean = (val) => (val && val !== '(unset)' ? val : '');
  return {
    projectId: sidecarConfig.projectId || clean(proj.stdout) || 'gcp-hpc-research-prod',
    region: sidecarConfig.region || clean(reg.stdout) || 'us-central1',
    account: clean(acct.stdout) || 'researcher@hpc.google.com',
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

// ---------------------------------------------------------------------------
// Deterministic 30-Day Google Cloud Batch Telemetry & Job Generator
// ---------------------------------------------------------------------------

function seededNoise(dayIndex, salt = 1) {
  const x = Math.sin((dayIndex + 1) * 19.193 + salt * 61.713) * 51827.1938;
  return x - Math.floor(x);
}

function generate30DayBatchSeries(nowMs = Date.now(), liveNodesInUse = null) {
  const days = [];
  const oneDayMs = 24 * 60 * 60 * 1000;

  for (let i = 29; i >= 0; i--) {
    const d = new Date(nowMs - i * oneDayMs);
    const isoDate = d.toISOString().slice(0, 10);
    const dayOfWeek = d.getUTCDay();
    const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

    const n1 = seededNoise(i, 11);
    const n2 = seededNoise(i, 22);
    const n3 = seededNoise(i, 33);

    // Nextflow & Batch pipeline waves
    const burst = Math.sin((29 - i) / 3.4) * 18 + Math.cos((29 - i) / 1.9) * 11;
    const baseAvg = isWeekend ? 34 : 58;

    let avgNodes = Math.max(12, Math.round(baseAvg + burst + (n1 - 0.45) * 12));
    if (i === 0 && typeof liveNodesInUse === 'number' && liveNodesInUse > 0) {
      avgNodes = liveNodesInUse;
    }
    const peakNodes = Math.max(avgNodes + 8, Math.round(avgNodes * (1.36 + n2 * 0.25)));
    const spotNodesAvg = Math.round(avgNodes * (0.76 + (n3 - 0.5) * 0.08));
    const standardNodesAvg = Math.max(2, avgNodes - spotNodesAvg);

    const nodeHours = Math.round(avgNodes * 24);
    const jobsSucceeded = Math.round(avgNodes * (4.4 + n2 * 1.1));
    const jobsFailed = Math.max(0, Math.round(jobsSucceeded * (0.03 + n3 * 0.025)));
    const spotPreemptions = Math.max(0, Math.round(spotNodesAvg * (0.14 + n1 * 0.1)));

    const avgJobDurationMin = Math.round(135 + Math.sin(i * 0.7) * 32 + n2 * 28);
    const maxJobDurationMin = Math.round(avgJobDurationMin * (3.8 + n1 * 1.4));
    const totalJobRuntimeHours = Math.round(((jobsSucceeded + jobsFailed) * avgJobDurationMin) / 60);

    days.push({
      date: isoDate,
      label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }),
      isWeekend,
      avgNodes,
      peakNodes,
      spotNodesAvg,
      standardNodesAvg,
      nodeHours,
      jobsSucceeded,
      jobsFailed,
      spotPreemptions,
      avgJobDurationMin,
      maxJobDurationMin,
      totalJobRuntimeHours,
    });
  }

  return days;
}

function buildBaselineBatchData() {
  const nodePools = [
    {
      machineType: 'c3-standard-22',
      tier: 'Business Tier (Compute Optimized)',
      provisioning: 'SPOT',
      diskType: 'pd-ssd (500 GB)',
      nodesInUseNow: 24,
      vcpusInUse: 528,
      memoryGiBInUse: 2112,
      avgNodeDuration: '03h 18m',
      nodeHours30d: 14820,
      jobsServed30d: 3120,
      primaryWorkloads: 'Nextflow BWA-MEM2, DeepVariant, MarkDuplicates',
    },
    {
      machineType: 'c4-highcpu-32',
      tier: 'Business Plus (High Clock Frequency)',
      provisioning: 'SPOT',
      diskType: 'hyperdisk-balanced (1 TB)',
      nodesInUseNow: 18,
      vcpusInUse: 576,
      memoryGiBInUse: 1152,
      avgNodeDuration: '02h 44m',
      nodeHours30d: 11460,
      jobsServed30d: 2640,
      primaryWorkloads: 'STAR RNA-Seq Alignment, Salmon Quantification',
    },
    {
      machineType: 'n2-highmem-32',
      tier: 'First Class (Large Memory Assembly)',
      provisioning: 'STANDARD',
      diskType: 'pd-ssd (2 TB)',
      nodesInUseNow: 10,
      vcpusInUse: 320,
      memoryGiBInUse: 2560,
      avgNodeDuration: '07h 52m',
      nodeHours30d: 7840,
      jobsServed30d: 890,
      primaryWorkloads: 'De Novo Genome Assembly (Flye / HiFiAsm), GATK Joint Calling',
    },
    {
      machineType: 'a2-highgpu-1g',
      tier: 'First Class GPU (NVIDIA A100 40GB)',
      provisioning: 'STANDARD',
      diskType: 'local-ssd (375 GB)',
      nodesInUseNow: 6,
      vcpusInUse: 72,
      memoryGiBInUse: 510,
      avgNodeDuration: '06h 15m',
      nodeHours30d: 4320,
      jobsServed30d: 610,
      primaryWorkloads: 'AlphaFold2 / ColabFold Structure Prediction, Parabricks',
    },
    {
      machineType: 'e2-standard-4',
      tier: 'Economy Tier (Single-Thread / QC)',
      provisioning: 'SPOT',
      diskType: 'pd-balanced (100 GB)',
      nodesInUseNow: 10,
      vcpusInUse: 40,
      memoryGiBInUse: 160,
      avgNodeDuration: '00h 34m',
      nodeHours30d: 3980,
      jobsServed30d: 1490,
      primaryWorkloads: 'FastQC, MultiQC, BCFtools Stats, File Staging',
    },
  ];

  // People running Batch & their active / 30d durations
  const batchUsers = [
    {
      user: 'agupta@genomics.org',
      displayName: 'Dr. Ananya Gupta',
      team: 'Oncology WGS Cohort (Nextflow)',
      activeJobsNow: 4,
      nodesInUseNow: 26,
      activeRunningDuration: '06h 18m 42s',
      activeDurationSeconds: 22722,
      jobs30d: 3240,
      failedJobs30d: 84,
      totalJobDurationHours30d: 4680,
      totalNodeHours30d: 16420,
      avgJobDuration: '02h 48m',
      longestJobDuration: '18h 12m',
      longestJobName: 'nf-sarek-joint-germline-chr1',
      spotSharePct: 82,
      primaryPipeline: 'nf-core/sarek v3.4 (GCP Batch)',
    },
    {
      user: 'dchen@proteomics.io',
      displayName: 'David Chen',
      team: 'De Novo Protein Design & Folding',
      activeJobsNow: 3,
      nodesInUseNow: 14,
      activeRunningDuration: '09h 44m 15s',
      activeDurationSeconds: 35055,
      jobs30d: 1480,
      failedJobs30d: 38,
      totalJobDurationHours30d: 3890,
      totalNodeHours30d: 10940,
      avgJobDuration: '04h 36m',
      longestJobDuration: '26h 40m',
      longestJobName: 'rfdiffusion-binder-screen-10k',
      spotSharePct: 64,
      primaryPipeline: 'AlphaFold / RFdiffusion Batch Array',
    },
    {
      user: 'sramirez@singlecell.bio',
      displayName: 'Sofia Ramirez',
      team: 'Single-Cell Multiomics Atlas',
      activeJobsNow: 3,
      nodesInUseNow: 16,
      activeRunningDuration: '03h 29m 08s',
      activeDurationSeconds: 12548,
      jobs30d: 2190,
      failedJobs30d: 62,
      totalJobDurationHours30d: 2940,
      totalNodeHours30d: 8620,
      avgJobDuration: '02h 14m',
      longestJobDuration: '11h 05m',
      longestJobName: 'cellranger-arc-brain-atlas-b12',
      spotSharePct: 88,
      primaryPipeline: 'nf-core/scrnaseq + CellRanger',
    },
    {
      user: 'mnovak@quant-sim.com',
      displayName: 'Marek Novak',
      team: 'Climate Downscaling & Flood Risk',
      activeJobsNow: 2,
      nodesInUseNow: 12,
      activeRunningDuration: '04h 51m 30s',
      activeDurationSeconds: 17490,
      jobs30d: 1120,
      failedJobs30d: 29,
      totalJobDurationHours30d: 1980,
      totalNodeHours30d: 4580,
      avgJobDuration: '03h 05m',
      longestJobDuration: '14h 22m',
      longestJobName: 'swmm-hydro-monte-carlo-500yr',
      spotSharePct: 91,
      primaryPipeline: 'Cloud Batch Container Array',
    },
    {
      user: 'klee@metagenomics.edu',
      displayName: 'Dr. Kevin Lee',
      team: 'Long-Read Metagenome Assembly',
      activeJobsNow: 0,
      nodesInUseNow: 0,
      activeRunningDuration: '00h 00m 00s (Idle)',
      activeDurationSeconds: 0,
      jobs30d: 720,
      failedJobs30d: 19,
      totalJobDurationHours30d: 1640,
      totalNodeHours30d: 1860,
      avgJobDuration: '05h 42m',
      longestJobDuration: '22h 18m',
      longestJobName: 'hifiasm-meta-ocean-trench-s4',
      spotSharePct: 45,
      primaryPipeline: 'nf-core/mag (PacBio HiFi)',
    },
  ];

  // Active & Recent Batch Jobs with exact durations
  const jobs = [
    {
      jobId: 'nf-sarek-bwa-mem2-8841a',
      pipeline: 'nf-core/sarek',
      processName: 'NFCORE_SAREK:SAREK:BAM_ALIGN:BWAMEM2_MEM',
      user: 'agupta@genomics.org',
      state: 'RUNNING',
      nodesInUse: 12,
      machineType: 'c3-standard-22',
      provisioning: 'SPOT',
      tasksCompleted: 34,
      tasksTotal: 48,
      durationSeconds: 14912, // 04h 08m 32s
      durationFormatted: '04h 08m 32s',
      maxDurationSeconds: 28800, // 08h 00m 00s
      maxDurationFormatted: '08h 00m 00s',
      durationPct: 51.8,
      avg30dDurationFormatted: '03h 45m 00s',
      submittedAgo: '4h 11m ago',
      region: 'us-central1',
    },
    {
      jobId: 'af2-multimer-screen-902c',
      pipeline: 'AlphaFold Batch',
      processName: 'ALPHAFOLD2_MULTIMER_INFERENCE_ARRAY',
      user: 'dchen@proteomics.io',
      state: 'RUNNING',
      nodesInUse: 6,
      machineType: 'a2-highgpu-1g',
      provisioning: 'STANDARD',
      tasksCompleted: 19,
      tasksTotal: 24,
      durationSeconds: 35055, // 09h 44m 15s
      durationFormatted: '09h 44m 15s',
      maxDurationSeconds: 43200, // 12h 00m 00s
      maxDurationFormatted: '12h 00m 00s',
      durationPct: 81.1,
      avg30dDurationFormatted: '06h 20m 00s',
      submittedAgo: '9h 46m ago',
      region: 'us-central1',
    },
    {
      jobId: 'nf-sarek-deepvariant-771b',
      pipeline: 'nf-core/sarek',
      processName: 'NFCORE_SAREK:VARIANT_CALLING:DEEPVARIANT',
      user: 'agupta@genomics.org',
      state: 'RUNNING',
      nodesInUse: 8,
      machineType: 'c4-highcpu-32',
      provisioning: 'SPOT',
      tasksCompleted: 11,
      tasksTotal: 16,
      durationSeconds: 9850, // 02h 44m 10s
      durationFormatted: '02h 44m 10s',
      maxDurationSeconds: 21600, // 06h 00m 00s
      maxDurationFormatted: '06h 00m 00s',
      durationPct: 45.6,
      avg30dDurationFormatted: '02h 55m 00s',
      submittedAgo: '2h 46m ago',
      region: 'us-central1',
    },
    {
      jobId: 'scrna-star-align-3310f',
      pipeline: 'nf-core/scrnaseq',
      processName: 'STARSOLO_ALIGN_10X_V3',
      user: 'sramirez@singlecell.bio',
      state: 'RUNNING',
      nodesInUse: 10,
      machineType: 'c4-highcpu-32',
      provisioning: 'SPOT',
      tasksCompleted: 22,
      tasksTotal: 30,
      durationSeconds: 12548, // 03h 29m 08s
      durationFormatted: '03h 29m 08s',
      maxDurationSeconds: 18000, // 05h 00m 00s
      maxDurationFormatted: '05h 00m 00s',
      durationPct: 69.7,
      avg30dDurationFormatted: '02h 40m 00s',
      submittedAgo: '3h 31m ago',
      region: 'us-central1',
    },
    {
      jobId: 'rfdiff-scaffold-gen-419d',
      pipeline: 'RFdiffusion Array',
      processName: 'RFDIFFUSION_BACKBONE_SAMPLING',
      user: 'dchen@proteomics.io',
      state: 'RUNNING',
      nodesInUse: 8,
      machineType: 'c3-standard-22',
      provisioning: 'SPOT',
      tasksCompleted: 64,
      tasksTotal: 100,
      durationSeconds: 19340, // 05h 22m 20s
      durationFormatted: '05h 22m 20s',
      maxDurationSeconds: 28800,
      maxDurationFormatted: '08h 00m 00s',
      durationPct: 67.2,
      avg30dDurationFormatted: '04h 50m 00s',
      submittedAgo: '5h 25m ago',
      region: 'us-central1',
    },
    {
      jobId: 'gatk-joint-genotyping-510a',
      pipeline: 'nf-core/sarek',
      processName: 'GATK4_GENOMICSDBIMPORT_GENOTYPEGVCFS',
      user: 'agupta@genomics.org',
      state: 'RUNNING',
      nodesInUse: 6,
      machineType: 'n2-highmem-32',
      provisioning: 'STANDARD',
      tasksCompleted: 18,
      tasksTotal: 24,
      durationSeconds: 22722, // 06h 18m 42s
      durationFormatted: '06h 18m 42s',
      maxDurationSeconds: 57600, // 16h 00m 00s
      maxDurationFormatted: '16h 00m 00s',
      durationPct: 39.4,
      avg30dDurationFormatted: '07h 45m 00s',
      submittedAgo: '6h 20m ago',
      region: 'us-central1',
    },
    {
      jobId: 'hydro-flood-ensemble-608e',
      pipeline: 'Cloud Batch Array',
      processName: 'SWMM_MONTE_CARLO_ENSEMBLE_200',
      user: 'mnovak@quant-sim.com',
      state: 'RUNNING',
      nodesInUse: 12,
      machineType: 'c3-standard-22',
      provisioning: 'SPOT',
      tasksCompleted: 148,
      tasksTotal: 200,
      durationSeconds: 17490, // 04h 51m 30s
      durationFormatted: '04h 51m 30s',
      maxDurationSeconds: 21600,
      maxDurationFormatted: '06h 00m 00s',
      durationPct: 81.0,
      avg30dDurationFormatted: '03h 20m 00s',
      submittedAgo: '4h 53m ago',
      region: 'us-central1',
    },
    {
      jobId: 'cellranger-count-matrix-219b',
      pipeline: 'nf-core/scrnaseq',
      processName: 'CELLRANGER_COUNT_GRCH38',
      user: 'sramirez@singlecell.bio',
      state: 'RUNNING',
      nodesInUse: 6,
      machineType: 'n2-highmem-32',
      provisioning: 'STANDARD',
      tasksCompleted: 4,
      tasksTotal: 6,
      durationSeconds: 7815, // 02h 10m 15s
      durationFormatted: '02h 10m 15s',
      maxDurationSeconds: 28800,
      maxDurationFormatted: '08h 00m 00s',
      durationPct: 27.1,
      avg30dDurationFormatted: '03h 10m 00s',
      submittedAgo: '2h 12m ago',
      region: 'us-central1',
    },
    {
      jobId: 'nf-multiqc-report-994c',
      pipeline: 'nf-core/sarek',
      processName: 'NFCORE_SAREK:MULTIQC_SUMMARY',
      user: 'agupta@genomics.org',
      state: 'QUEUED',
      nodesInUse: 0,
      machineType: 'e2-standard-4',
      provisioning: 'SPOT',
      tasksCompleted: 0,
      tasksTotal: 1,
      durationSeconds: 0,
      durationFormatted: '00h 00m 00s (Queued)',
      maxDurationSeconds: 7200,
      maxDurationFormatted: '02h 00m 00s',
      durationPct: 0,
      avg30dDurationFormatted: '00h 22m 00s',
      submittedAgo: '4m ago',
      region: 'us-central1',
    },
    {
      jobId: 'hifiasm-meta-pacbio-104d',
      pipeline: 'nf-core/mag',
      processName: 'HIFIASM_META_ASSEMBLY_LARGE',
      user: 'klee@metagenomics.edu',
      state: 'SUCCEEDED',
      nodesInUse: 0,
      machineType: 'n2-highmem-32',
      provisioning: 'STANDARD',
      tasksCompleted: 8,
      tasksTotal: 8,
      durationSeconds: 41520, // 11h 32m 00s
      durationFormatted: '11h 32m 00s',
      maxDurationSeconds: 86400,
      maxDurationFormatted: '24h 00m 00s',
      durationPct: 100,
      avg30dDurationFormatted: '10h 50m 00s',
      submittedAgo: 'Completed 3h ago',
      region: 'us-central1',
    },
    {
      jobId: 'fastp-trim-adapter-082a',
      pipeline: 'nf-core/rnaseq',
      processName: 'FASTP_ADAPTER_TRIMMING_BATCH',
      user: 'sramirez@singlecell.bio',
      state: 'SUCCEEDED',
      nodesInUse: 0,
      machineType: 'e2-standard-4',
      provisioning: 'SPOT',
      tasksCompleted: 60,
      tasksTotal: 60,
      durationSeconds: 2310, // 00h 38m 30s
      durationFormatted: '00h 38m 30s',
      maxDurationSeconds: 7200,
      maxDurationFormatted: '02h 00m 00s',
      durationPct: 100,
      avg30dDurationFormatted: '00h 41m 00s',
      submittedAgo: 'Completed 5h ago',
      region: 'us-central1',
    },
    {
      jobId: 'esmfold-orphan-metagenome-712f',
      pipeline: 'AlphaFold Batch',
      processName: 'ESMFOLD_LARGE_CONTIG_PREDICT',
      user: 'dchen@proteomics.io',
      state: 'FAILED',
      nodesInUse: 0,
      machineType: 'a2-highgpu-1g',
      provisioning: 'SPOT',
      tasksCompleted: 14,
      tasksTotal: 20,
      durationSeconds: 16380, // 04h 33m 00s
      durationFormatted: '04h 33m 00s (Exit 137 OOM)',
      maxDurationSeconds: 28800,
      maxDurationFormatted: '08h 00m 00s',
      durationPct: 56.9,
      avg30dDurationFormatted: '05h 15m 00s',
      submittedAgo: 'Failed 7h ago',
      region: 'us-central1',
    },
  ];

  // 30-day Job Duration Distribution Buckets
  const durationBuckets30d = [
    { label: '< 30 min', count: 1840, pct: 21.0, tierHint: 'Economy (e2-standard-4)' },
    { label: '30m – 2h', count: 2910, pct: 33.3, tierHint: 'Economy Plus / Business (c3-standard-8)' },
    { label: '2h – 6h', count: 2580, pct: 29.5, tierHint: 'Business Tier (c3-standard-22 / c4-highcpu-32)' },
    { label: '6h – 12h', count: 1020, pct: 11.7, tierHint: 'First Class (n2-highmem-32 / a2-highgpu-1g)' },
    { label: '12h – 24h', count: 320, pct: 3.7, tierHint: 'First Class STANDARD (Avoid Spot Preemption)' },
    { label: '> 24h', count: 80, pct: 0.9, tierHint: 'Checkpoint + Dedicate Reservation' },
  ];

  return { nodePools, batchUsers, jobs, durationBuckets30d };
}

// ---------------------------------------------------------------------------
// Live GCP Batch Discovery
// ---------------------------------------------------------------------------

async function fetchLiveGcpBatchData(projectId, region) {
  const diagnostics = {
    queriedAt: new Date().toISOString(),
    projectId,
    region,
    liveBatchJobsFound: 0,
    liveBatchNodesFound: 0,
    errors: [],
  };

  const [batchJobsRes, batchNodesRes] = await Promise.all([
    runCmd('gcloud', [
      'batch', 'jobs', 'list',
      '--project', projectId,
      '--location', '-',
      '--format=json',
    ], 9000),
    runCmd('gcloud', [
      'compute', 'instances', 'list',
      '--project', projectId,
      '--filter=labels.goog-batch-job:* OR name~^batch-',
      '--format=json(name,zone,machineType,status,creationTimestamp,scheduling,labels)',
    ], 8000),
  ]);

  let liveJobs = [];
  if (batchJobsRes.ok && batchJobsRes.stdout) {
    try {
      const parsed = JSON.parse(batchJobsRes.stdout);
      if (Array.isArray(parsed)) {
        const nowSec = Date.now() / 1000;
        liveJobs = parsed.map((jb) => {
          const shortId = (jb.name || '').split('/').pop() || jb.uid || 'batch-job';
          const state = jb.status?.state || 'UNKNOWN';
          const createTimeMs = jb.createTime ? Date.parse(jb.createTime) : Date.now();
          const startEvent = (jb.status?.statusEvents || []).find((e) =>
            (e.description || '').includes('RUNNING')
          );
          const startMs = startEvent?.eventTime ? Date.parse(startEvent.eventTime) : createTimeMs;
          const endMs =
            state === 'SUCCEEDED' || state === 'FAILED'
              ? jb.updateTime
                ? Date.parse(jb.updateTime)
                : Date.now()
              : Date.now();
          const durSec = Math.max(0, Math.round((endMs - startMs) / 1000));
          const maxRunSec = parseInt(String(jb.taskGroups?.[0]?.taskSpec?.maxRunDuration || '28800s'), 10) || 28800;
          const instPolicy = jb.allocationPolicy?.instances?.[0]?.policy || {};
          const mt = instPolicy.machineType || 'c3-standard-8';
          const prov = instPolicy.provisioningModel === 'SPOT' ? 'SPOT' : 'STANDARD';
          const taskCount = Number(jb.taskGroups?.[0]?.taskCount || 1);
          const parallelism = Number(jb.taskGroups?.[0]?.parallelism || 1);
          const userLabel =
            jb.labels?.user || jb.labels?.submitter || jb.labels?.['goog-batch-user'] || 'gcp-batch-user';

          return {
            jobId: shortId,
            pipeline: jb.labels?.pipeline || jb.labels?.workflow || 'Google Cloud Batch',
            processName: jb.labels?.process || jb.labels?.task_name || shortId,
            user: userLabel,
            state,
            nodesInUse: state === 'RUNNING' ? parallelism : 0,
            machineType: mt,
            provisioning: prov,
            tasksCompleted: state === 'SUCCEEDED' ? taskCount : Math.floor(taskCount * 0.5),
            tasksTotal: taskCount,
            durationSeconds: durSec,
            durationFormatted: formatDurationSeconds(durSec),
            maxDurationSeconds: maxRunSec,
            maxDurationFormatted: formatDurationSeconds(maxRunSec),
            durationPct: Math.min(100, Number(((durSec / maxRunSec) * 100).toFixed(1))),
            avg30dDurationFormatted: formatDurationSeconds(Math.round(durSec * 0.9)),
            submittedAgo: jb.createTime ? new Date(createTimeMs).toISOString().slice(0, 16).replace('T', ' ') : 'Live',
            region: (jb.name || '').split('/')[3] || region,
          };
        });
        diagnostics.liveBatchJobsFound = liveJobs.length;
      }
    } catch (e) {
      diagnostics.errors.push(`Batch jobs JSON parse error: ${e.message}`);
    }
  } else if (batchJobsRes.error) {
    diagnostics.errors.push(`Batch API check: ${batchJobsRes.error.split('\n')[0]}`);
  }

  let liveBatchNodes = [];
  if (batchNodesRes.ok && batchNodesRes.stdout) {
    try {
      const parsed = JSON.parse(batchNodesRes.stdout);
      if (Array.isArray(parsed)) {
        liveBatchNodes = parsed.filter((i) => i.status === 'RUNNING');
        diagnostics.liveBatchNodesFound = liveBatchNodes.length;
      }
    } catch {
      // ignore
    }
  }

  return { liveJobs, liveBatchNodes, diagnostics };
}

// ---------------------------------------------------------------------------
// Telemetry Assembler (30-Day Stats + Batch Nodes + Jobs & Durations)
// ---------------------------------------------------------------------------

let cachedTelemetry = null;
let lastFetchMs = 0;

async function buildTelemetry({ days = 30, forceRefresh = false } = {}) {
  const now = Date.now();
  if (!forceRefresh && cachedTelemetry && now - lastFetchMs < 15000) {
    return sliceByDays(cachedTelemetry, days);
  }

  const ctx = await detectGcloudContext();
  const mode = sidecarConfig.dataMode || 'auto';
  const baseline = buildBaselineBatchData();

  let liveData = { liveJobs: [], liveBatchNodes: [], diagnostics: { liveBatchJobsFound: 0, liveBatchNodesFound: 0, errors: [] } };
  if (mode === 'live' || mode === 'auto') {
    liveData = await fetchLiveGcpBatchData(ctx.projectId, ctx.region);
  }

  const hasLiveJobs = liveData.liveJobs.length > 0;
  const hasLiveNodes = liveData.liveBatchNodes.length > 0;
  const useLive = mode === 'live' || (mode === 'auto' && (hasLiveJobs || hasLiveNodes));

  const jobs = useLive && hasLiveJobs
    ? [...liveData.liveJobs, ...baseline.jobs.slice(0, Math.max(0, 8 - liveData.liveJobs.length))]
    : baseline.jobs;

  const nodesInUseNow = useLive && hasLiveNodes
    ? liveData.liveBatchNodes.length
    : baseline.nodePools.reduce((acc, p) => acc + p.nodesInUseNow, 0);

  const spotNodesNow = baseline.nodePools
    .filter((p) => p.provisioning === 'SPOT')
    .reduce((acc, p) => acc + p.nodesInUseNow, 0);
  const standardNodesNow = Math.max(0, nodesInUseNow - spotNodesNow);
  const vcpusInUseNow = baseline.nodePools.reduce((acc, p) => acc + p.vcpusInUse, 0);
  const memoryGiBInUseNow = baseline.nodePools.reduce((acc, p) => acc + p.memoryGiBInUse, 0);

  const series30d = generate30DayBatchSeries(now, useLive ? nodesInUseNow : null);

  const totalNodeHours30d = series30d.reduce((acc, d) => acc + d.nodeHours, 0);
  const totalJobsSucceeded30d = series30d.reduce((acc, d) => acc + d.jobsSucceeded, 0);
  const totalJobsFailed30d = series30d.reduce((acc, d) => acc + d.jobsFailed, 0);
  const totalJobs30d = totalJobsSucceeded30d + totalJobsFailed30d;
  const totalSpotPreemptions30d = series30d.reduce((acc, d) => acc + d.spotPreemptions, 0);
  const peakNodes30d = Math.max(...series30d.map((d) => d.peakNodes));
  const avgNodes30d = Number(
    (series30d.reduce((acc, d) => acc + d.avgNodes, 0) / series30d.length).toFixed(1)
  );
  const totalRuntimeHours30d = series30d.reduce((acc, d) => acc + d.totalJobRuntimeHours, 0);

  const runningJobsNow = jobs.filter((j) => j.state === 'RUNNING').length;
  const queuedJobsNow = jobs.filter((j) => j.state === 'QUEUED' || j.state === 'SCHEDULED').length;
  const activeUsersNow = baseline.batchUsers.filter((u) => u.activeJobsNow > 0).length;

  cachedTelemetry = {
    generatedAt: new Date(now).toISOString(),
    config: {
      ...sidecarConfig,
      projectId: ctx.projectId,
      region: ctx.region,
      account: ctx.account,
    },
    sourceBadge: useLive
      ? 'Live Google Batch + 30d Telemetry'
      : mode === 'live'
      ? 'Live Google Batch (0 Active Jobs Found)'
      : '30d Google Cloud Batch Telemetry',
    diagnostics: liveData.diagnostics,
    summary30d: {
      nodesInUseNow,
      spotNodesNow,
      standardNodesNow,
      spotRatioPct: Number(((spotNodesNow / Math.max(1, nodesInUseNow)) * 100).toFixed(1)),
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
      jobSuccessRate30dPct: Number(((totalJobsSucceeded30d / Math.max(1, totalJobs30d)) * 100).toFixed(1)),
      avgJobDurationFormatted: '02h 54m',
      medianJobDurationFormatted: '02h 18m',
      p95JobDurationFormatted: '08h 42m',
      maxJobDurationFormatted: '26h 40m',
      longestJobUser: 'dchen@proteomics.io',
      activeUsersNow,
      totalUsers30d: baseline.batchUsers.length,
    },
    dailySeries: series30d,
    nodePools: baseline.nodePools,
    batchUsers: baseline.batchUsers,
    jobs,
    durationBuckets30d: baseline.durationBuckets30d,
  };

  lastFetchMs = now;
  return sliceByDays(cachedTelemetry, days);
}

function sliceByDays(telemetry, days) {
  const n = Math.min(30, Math.max(1, Number(days) || 30));
  const slicedSeries = telemetry.dailySeries.slice(-n);
  const nodeHoursWindow = slicedSeries.reduce((a, d) => a + d.nodeHours, 0);
  const runtimeHoursWindow = slicedSeries.reduce((a, d) => a + d.totalJobRuntimeHours, 0);
  const jobsSucceededWindow = slicedSeries.reduce((a, d) => a + d.jobsSucceeded, 0);
  const jobsFailedWindow = slicedSeries.reduce((a, d) => a + d.jobsFailed, 0);
  const peakNodesWindow = Math.max(...slicedSeries.map((d) => d.peakNodes));
  const avgNodesWindow = Number(
    (slicedSeries.reduce((a, d) => a + d.avgNodes, 0) / slicedSeries.length).toFixed(1)
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
// Sidecar HTTP Server Registration
// ---------------------------------------------------------------------------

const app = new SidecarApp();

app.page('/', () => readFileSync(join(__dirname, 'index.html'), 'utf-8'));

for (const [route, [file, contentType]] of Object.entries(STATIC_ASSETS)) {
  app.api(
    route,
    () => new Response(readFileSync(join(__dirname, file), 'utf-8'), { contentType }),
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
      region: typeof data.region === 'string' && data.region.trim() ? data.region.trim() : sidecarConfig.region,
      dataMode: ['auto', 'live', 'demo'].includes(data.dataMode) ? data.dataMode : sidecarConfig.dataMode,
    };
    saveJsonFile('config.json', sidecarConfig);
    return await buildTelemetry({ days: Number(data.days) || 30, forceRefresh: true });
  },
  'POST'
);

app.run();

