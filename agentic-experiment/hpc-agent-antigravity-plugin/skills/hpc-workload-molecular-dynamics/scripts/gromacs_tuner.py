#!/usr/bin/env python3
"""
GROMACS Performance Tuner for GCP Compute Instances.
Computes optimal MPI ranks, OpenMP threads, and GPU offloading flags
based on system atom count and GCP accelerator topology (B200, H200, H100, L4, CPU).
"""

import argparse
from typing import Any, Dict

def tune_gromacs(atoms: int, gpus: int, gpu_type: str, cpu_cores: int, nodes: int = 1, pme_ranks: int = 0) -> Dict[str, Any]:
    print("=================================================================")
    print("          GROMACS Execution & Hardware Tuning Guide              ")
    print("=================================================================")
    print(f"System Size:         {atoms:,} atoms")
    print(f"Nodes:               {nodes}")
    print(f"GPU Setup:           {gpus}x {gpu_type} (per node)")
    print(f"Available CPU Cores: {cpu_cores} (per node)")
    print("-----------------------------------------------------------------")
    
    total_gpus = gpus * nodes
    total_cores = cpu_cores * nodes
    
    if gpus > 0:
        threads_per_rank = max(1, cpu_cores // gpus)
        mpi_ranks = total_gpus
        
        # Calculate dedicated PME ranks for multi-node scaling if requested/applicable
        if pme_ranks <= 0 and nodes > 1 and total_gpus >= 8:
            # Standard heuristic: 1/4 to 1/3 of ranks for separate PME on large multi-node runs
            recommended_pme = max(1, total_gpus // 4)
        else:
            recommended_pme = pme_ranks
            
        print(f"[+] Detected GPU-accelerated configuration ({gpu_type}).")
        print(f"  - Recommended Total MPI Ranks:          {mpi_ranks} ({gpus} per node)")
        print(f"  - Recommended OpenMP Threads (-ntomp):  {threads_per_rank}")
        if recommended_pme > 0:
            print(f"  - Dedicated PME Ranks (-npme):          {recommended_pme}")
        
        if atoms < 500000:
            offload_mode = "FULL_GPU_RESIDENT"
            offload_flags = "-nb gpu -pme gpu -bonded gpu -update gpu"
            print("  - Offload Mode: FULL GPU RESIDENT (PME, Nonbonded, Bonded, Update on GPU)")
        else:
            offload_mode = "HYBRID_GPU"
            offload_flags = "-nb gpu -pme gpu -bonded gpu"
            print("  - Offload Mode: HYBRID GPU/CPU (PME + Nonbonded on GPU)")
            
        pme_arg = f" -npme {recommended_pme}" if recommended_pme > 0 else ""
        if nodes > 1:
            cmd = f"mpirun -np {mpi_ranks} gmx_mpi mdrun -v -deffnm topol -ntomp {threads_per_rank} {offload_flags}{pme_arg} -pin on"
        else:
            cmd = f"gmx mdrun -v -deffnm topol -ntmpi {mpi_ranks} -ntomp {threads_per_rank} {offload_flags}{pme_arg} -pin on"
    else:
        threads_per_rank = 2
        mpi_ranks = total_cores // threads_per_rank
        recommended_pme = pme_ranks if pme_ranks > 0 else (mpi_ranks // 4 if nodes > 1 else 0)
        offload_mode = "CPU_ONLY"
        offload_flags = ""
        print("[+] Detected CPU-only configuration (e.g. H4D/H3/C4).")
        print(f"  - Recommended Total MPI Ranks:          {mpi_ranks}")
        print(f"  - Recommended OpenMP Threads (-ntomp):  {threads_per_rank}")
        if recommended_pme > 0:
            print(f"  - Dedicated PME Ranks (-npme):          {recommended_pme}")
            
        pme_arg = f" -npme {recommended_pme}" if recommended_pme > 0 else ""
        if nodes > 1:
            cmd = f"mpirun -np {mpi_ranks} gmx_mpi mdrun -v -deffnm topol -ntomp {threads_per_rank}{pme_arg} -pin on -pinstride 1"
        else:
            cmd = f"gmx mdrun -v -deffnm topol -ntmpi {mpi_ranks} -ntomp {threads_per_rank}{pme_arg} -pin on -pinstride 1"

    print("-----------------------------------------------------------------")
    print("Recommended gmx mdrun command line:")
    print(f"\n  {cmd}\n")
    print("-----------------------------------------------------------------")
    
    return {
        "mpi_ranks": mpi_ranks,
        "threads_per_rank": threads_per_rank,
        "offload_mode": offload_mode,
        "offload_flags": offload_flags,
        "pme_ranks": recommended_pme,
        "nodes": nodes,
        "total_ranks": mpi_ranks,
        "command": cmd,
    }

def main():
    parser = argparse.ArgumentParser(description="GROMACS GCP Performance Tuner")
    parser.add_argument("--atoms", type=int, default=200000, help="Total number of atoms in simulation")
    parser.add_argument("--gpus", type=int, default=8, help="Number of GPUs available per node")
    parser.add_argument("--gpu-type", default="H100", choices=["B200", "GB200", "H200", "H100", "L4", "A100", "None"], help="GPU architecture")
    parser.add_argument("--cpu-cores", type=int, default=88, help="Total CPU cores available on node")
    parser.add_argument("--nodes", type=int, default=1, help="Number of compute nodes")
    parser.add_argument("--pme-ranks", type=int, default=0, help="Number of dedicated PME ranks (0 for auto)")
    args = parser.parse_args()

    tune_gromacs(args.atoms, args.gpus, args.gpu_type, args.cpu_cores, args.nodes, args.pme_ranks)

if __name__ == "__main__":
    main()
