# HPC Cluster & Slurm Environment Monitor (`hpc_cluster_monitor`)

UI sidecar for the `hpc-agent-antigravity` plugin that renders an interactive dashboard in the Antigravity Auxiliary Pane (`SIDECAR_UI_ENTRYPOINT_AUX_PANE`).

## Key Capabilities

1. **Running HPC Instances Over Time (30-Day Statistics)**:
   - Tracks daily average and peak running HPC instances over a 7-, 14-, or 30-day window.
   - Breaks down active and historical compute capacity by machine family (`H4D`, `C4`, `C3`, `A3-MegaGPU`, `N4`).
   - Displays real-time Slurm partition states (`allocated`, `mixed`, `idle`, `down`) and 30-day utilization percentages.
2. **Slurm Environment & Per-User Workload**:
   - Shows how many jobs are currently running and queued per user/researcher (`squeue`), alongside 30-day completed job counts and core-hours (`sacct`).
   - Interactive user filtering and job inspection buttons that message `hpc-agent-antigravity` directly via `window.sidecar.agent.sendMessage`.
3. **Storage Systems in Use**:
   - Monitors mounted HPC storage systems including **Google Cloud Managed Lustre** (`/lustre/scratch`), **Cloud Filestore Regional/Enterprise** (`/home`), **Cloud Filestore Zonal High Scale** (`/apps`), **Cloud Storage FUSE** (`/mnt/gcs-datasets`), and **Node-Local NVMe / Hyperdisk Scratch** (`/tmp/scratch`).
   - Tracks 30-day storage capacity growth and peak aggregate I/O throughput (GB/s).

