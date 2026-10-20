# CAE Hardware Tuning & Memory Sizing Guide

## 1. CFD vs FEA Hardware Characteristics

- **CFD (OpenFOAM, Fluent, STAR-CCM+)**:
  - Bound by memory bandwidth (DDR channels) and inter-node MPI latency.
  - Scale best on `h4d-standard-192` (AMD Turin, 192c) or `h3-standard-88` (Intel Sapphire Rapids, 8 memory channels per socket, DDR5 4800 MT/s).
  - Target cell count per core: 50,000 – 150,000 cells/core. Below 25k cells/core, MPI latency dominates.

- **FEA (Abaqus, Ansys Mechanical, Nastran)**:
  - Bound by CPU frequency, L3 cache, and large sparse matrix solver I/O.
  - Scale well on `c4-standard-192` (Emerald Rapids), `c4d-standard-384` (Turin), `c3-standard-88` (Sapphire Rapids), or `c3d-standard-180` (Genoa).
  - Scratch disk write speed is critical: always use Local SSD RAID-0 or Hyperdisk Balanced for solver temp files.

## 2. MPI Flag Optimization for GCP Tier 1 Network

When using Intel MPI:
```bash
export I_MPI_FABRICS=shm:ofi
export I_MPI_PIN=1
export I_MPI_PIN_DOMAIN=core
export I_MPI_DEBUG=5
```

When using OpenMPI / UCX:
```bash
mpirun --mca pml ucx --mca btl ^openib --bind-to core --map-by numa ...
```
