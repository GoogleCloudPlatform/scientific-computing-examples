# ISV License Proxy & Firewall Configuration Guide

## 1. License Server Architecture
In a hybrid cloud deployment, compute nodes in GCP connect to an on-premises or dedicated cloud VM license manager (FlexLM / RLM).

```
Compute Nodes (GCP VPC) ──► Cloud VPN / Interconnect ──► On-Prem FlexLM Server
       (e.g. 10.50.0.0/16)                                (e.g. 10.100.0.5:1055)
```

## 2. Required Firewall Ports
- **FlexLM Master Daemon**: Typically TCP port `1055` or `27000-27009`.
- **Vendor Daemon**: Dynamic by default; recommend locking to a static port in the license file (e.g., `VENDOR ansyslmd port=1056`).
- **RLM Master Daemon**: Typically TCP port `5053`.

## 3. High Latency Mitigation
If round-trip latency to on-premises license server exceeds 30ms:
1. Increase FlexLM checkout timeout on compute nodes:
   ```bash
   export FLEXLM_TIMEOUT=5000000 # 5 seconds
   ```
2. Deploy a local caching license replica or cloud-hosted secondary license server.
