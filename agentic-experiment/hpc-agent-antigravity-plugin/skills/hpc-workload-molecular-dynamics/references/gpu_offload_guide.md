# GPU Offload & Multi-Node Scaling Guide for Molecular Dynamics

## 1. GPU Architecture Comparison

| GPU Family | GCP VM Shape | VRAM | Interconnect | Best Fit |
| :--- | :--- | :--- | :--- | :--- |
| **NVIDIA B200 SXM** | `a4-highgpu-8g` | 192 GB HBM3e | NVLink 1.8 TB/s + 400 Gbps network | Next-gen MD, generative chemistry, billion-atom simulations |
| **NVIDIA GB200 NVL72** | `a4x-highgpu-4g` | Rack-scale NVLink domain | NVLink 1.8 TB/s | Ultra-scale molecular simulations and exascale AI |
| **NVIDIA H200 SXM5** | `a3-ultragpu-8g` | 141 GB HBM3e | NVLink 900 GB/s + RoCEv2 (3.2 Tbps) | Large language models for biology (ESM-2/3), massive MD |
| **NVIDIA H100 SXM5** | `a3-highgpu-8g` / `a3-megagpu-8g` | 80 GB HBM3 | NVLink 900 GB/s + RoCEv2 (up to 3.2 Tbps) | Extreme-scale GROMACS, LAMMPS, AlphaFold3, CryoSPARC |
| **NVIDIA L4** | `g2-standard-48` / `g2-standard-96` | 24 GB GDDR6 | PCIe Gen4 | Cost-effective virtual screening, inference, moderate MD |

## 2. GROMACS Offload Matrix

- **Full GPU Offload** (`-nb gpu -pme gpu -bonded gpu -update gpu`):
  - Minimizes CPU-GPU transfers. Recommended when all ranks fit cleanly on GPU and system size is under 500k-1M atoms.
- **Hybrid Offload** (`-nb gpu -pme gpu -bonded gpu`):
  - Balances GPU throughput with CPU update steps for large systems.
- **Dedicated PME Ranks** (`-npme <N>`):
  - Essential for multi-node scaling where 3D FFT communication across nodes causes GPU stalling. Typically allocate 1/4 of total ranks for PME.
