# Google Cloud Batch Nodes & Job Duration Monitor (`gcp_batch_monitor`)

UI sidecar for the `hpc-agent-antigravity` plugin that renders an interactive Google Cloud Batch monitoring dashboard in the Antigravity Auxiliary Pane (`SIDECAR_UI_ENTRYPOINT_AUX_PANE`).

## Key Capabilities

1. **Google Cloud Batch Nodes in Use (Live & 30-Day History)**:
   - Tracks active Google Cloud Batch VM nodes broken down by **Spot** vs. **Standard** provisioning models and machine shapes (`c3-standard-22`, `c4-highcpu-32`, `n2-highmem-32`, `a2-highgpu-1g`, `e2-standard-4`).
   - Interactive 30-day chart of daily average/peak Batch nodes in use, cumulative runtime hours, and jobs executed.
2. **People Running Batch & Duration Analytics**:
   - Displays every user/researcher running Google Cloud Batch workloads, how many Batch nodes they are currently consuming, their **live active running duration**, and their 30-day cumulative runtime hours, node-hours, average job duration, and longest single job.
3. **What Jobs & Duration (Live Ticking Duration Tracker)**:
   - Lists active (`RUNNING`, `QUEUED`) and completed (`SUCCEEDED`, `FAILED`) Batch jobs (including Nextflow pipeline tasks, AlphaFold arrays, and Batch container arrays).
   - Tracks real-time ticking duration (`HHh MMm SSs`), progress against `maxRunDuration`, comparison to the 30-day average baseline, and 30-day job duration distribution histograms.
   - Integrates with `hpc-agent-antigravity` via `window.sidecar.agent.sendMessage` for one-click Nextflow & Google Cloud Batch optimization.

