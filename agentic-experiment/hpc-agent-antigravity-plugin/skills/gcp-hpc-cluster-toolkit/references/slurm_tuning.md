# Slurm Optimization & Node Tuning for GCP

## 1. NUMA & Core Pinning Rules

### Intel Sapphire Rapids (H3: 88 physical cores)
- **1:1 physical core mapping**: SMT is disabled on `h3-standard-88`.
- 2 NUMA sockets (44 cores per socket).
- Sub-NUMA Clustering (SNC-2) creates 4 NUMA nodes (22 cores per NUMA node).
- Core pinning flags for OpenMPI:
  ```bash
  mpirun --bind-to core --map-by numa -np 88 ...
  ```
- Core pinning flags for Intel MPI:
  ```bash
  export I_MPI_PIN=1
  export I_MPI_PIN_DOMAIN=core
  export I_MPI_PIN_ORDER=compact
  ```

### Hybrid MPI + OpenMP Pinning
When running solvers with $M$ MPI ranks and $T$ OpenMP threads per rank:
```bash
export OMP_NUM_THREADS=$T
export OMP_PROC_BIND=close
export OMP_PLACES=cores

# In Slurm sbatch:
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=11

srun --cpu-bind=cores ./solver_executable
```

## 2. Cloud Autoscaling Parameter Tuning

In `slurm.conf`:
- `SuspendTime=300`: Grace period in seconds before an idle node is powered off.
- `ResumeTimeout=600`: Time allowed for Compute Engine API to boot and configure instance before marking node as down.
- `SuspendTimeout=300`: Time allowed for graceful node shutdown.
- `TreeWidth=50`: Controller tree fanout for high-node-count clusters.
