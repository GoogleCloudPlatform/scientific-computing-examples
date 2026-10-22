# HPC Spend & Monthly Budget Monitor (`hpc_spend_monitor`)

> [!CAUTION]
> **Disclaimer — Experimental & Demonstration Notice**: This work is for demo and experimental purpose only. Use at your own risk. This sidecar is provided "AS IS" without warranty or support of any kind, express or implied, and is not an officially supported Google product.

An Antigravity UI Sidecar for `hpc-agent-antigravity` that monitors GCP Billing every **4 hours**, decomposes the total cloud bill to isolate the **HPC portion** of spend, prompts the user for their **Maximum Monthly HPC Spend ($ USD)**, resets accumulated counters on the **1st of every month**, and dispatches an **automatic alert notification in the agent** whenever accumulated monthly HPC spend exceeds the user's cap.

## Key Capabilities

1. **Every-4-Hour GCP Billing Poll (`4 * 60 * 60 * 1000` ms)**:
   - Queries `gcloud billing projects describe`, `gcloud billing budgets list`, optional BigQuery Cloud Billing Export (`bq query`), and live HPC resources (`gcloud compute instances list`, `gcloud batch jobs list`, `gcloud lustre instances list`, `gcloud filestore instances list`).
   - Decomposes the total GCP bill into:
     - **HPC Portion**: Slurm Compute Partitions (H4D/C4/C3), GPU Accelerators (A3/A2), Google Cloud Batch Workers (Spot/Standard), Managed Lustre & Cloud Filestore, and HPC Networking (gVNIC/RDMA/Hyperdisk).
     - **Non-HPC Portion**: BigQuery, general-purpose VMs, Cloud Logging/Monitoring (excluded from the HPC cap).

2. **Interactive User Max Monthly Spend Prompt**:
   - Prompts the user for the maximum amount ($ USD) they plan to spend on HPC for the current month.
   - Compares accumulated monthly HPC spend against the user's cap on every 4-hour interval and upon budget updates.

3. **Automatic Monthly Rollover & Reset**:
   - Tracks the active billing month (`YYYY-MM`).
   - Automatically resets accumulated HPC spend, 4-hour interval logs, and alert state on the **1st of each calendar month at `00:00 UTC`**, archiving the prior month's summary.

4. **Agent Alert Notification on Budget Exceeded**:
   - When `accumulatedHpcSpendUsd > maxMonthlyBudgetUsd`, immediately dispatches a structured alert notification into the active agent conversation via `app.sendMessage` / `app.startConversation` (`sidecar_sdk` `agentapi`) and `window.sidecar.agent.sendMessage`, plus displays a high-visibility red alert banner in the sidecar UI.

## CLI & Standalone Usage

```bash
# Print the 4-hour GCP Billing & HPC portion JSON snapshot
node sidecars/hpc_spend_monitor/main.mjs --cli

# Run standalone UI server on http://127.0.0.1:8793
PORT=8793 node sidecars/hpc_spend_monitor/main.mjs
```

