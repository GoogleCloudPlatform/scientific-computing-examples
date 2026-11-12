# HPC Cluster Troubleshooting & Failure Recovery

## 1. Node Provisioning Failures

| Error | Root Cause | Remediation |
| :--- | :--- | :--- |
| `ZONE_RESOURCE_POOL_EXHAUSTED` | Requested VM shape (e.g. H3 or A3) is temporarily unavailable in the target zone. | Update blueprint to a secondary zone or region with reservation (e.g., `us-central1-a` -> `us-central1-f`). |
| `QUOTA_EXCEEDED` | GCP project lacks compute core quota (e.g. `CPUS_ALL_REGIONS` or `H3_CPUS`). | Request quota increase via Cloud Console or reduce `max_node_count`. |
| `Node failed to register within timeout` | Startup script failed or NFS mount timed out. | Check instance serial console logs: `gcloud compute instances get-serial-port-output <NODE>`. |

## 2. Slurm Node Recovery Runbook

If nodes show `drain*` or `down*`:

```bash
# 1. Check why the node was drained
scontrol show node <NODE_NAME> | grep -i reason

# 2. Test SSH from controller to node
ssh <NODE_NAME> hostname

# 3. Resume the node once resolved
sudo scontrol update NodeName=<NODE_NAME> State=RESUME

# 4. If node is completely unresponsive, reboot via gcloud:
gcloud compute instances reset <NODE_NAME> --zone=<ZONE>
```
