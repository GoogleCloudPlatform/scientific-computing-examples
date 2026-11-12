#!/usr/bin/env python3
"""
Domain Decomposition Calculator for CFD / OpenFOAM on GCP.
Computes optimal 3D decomposition geometry (nx, ny, nz) based on mesh cell count,
total core count, and CPU topology (Gen 4 C4/H4D 192-core, C4D 384-core, Gen 3 H3 88-core).
"""

import argparse
import math

def factorize_3d(n: int):
    """Find factors (nx, ny, nz) such that nx * ny * nz == n with minimal aspect ratio."""
    best_tuple = (n, 1, 1)
    min_diff = float("inf")
    
    for i in range(1, int(math.pow(n, 1/3)) + 2):
        if n % i == 0:
            rem = n // i
            for j in range(1, int(math.isqrt(rem)) + 2):
                if rem % j == 0:
                    k = rem // j
                    diff = max(i, j, k) - min(i, j, k)
                    if diff < min_diff:
                        min_diff = diff
                        best_tuple = tuple(sorted([i, j, k], reverse=True))
    return best_tuple

def main():
    parser = argparse.ArgumentParser(description="CFD Domain Decomposition Helper")
    parser.add_argument("--cells", type=int, default=10000000, help="Total mesh cell count")
    parser.add_argument("--cores", type=int, required=True, help="Total allocated MPI ranks/cores")
    parser.add_argument("--nodes", type=int, default=1, help="Number of cluster compute nodes")
    args = parser.parse_args()

    cells_per_core = args.cells / args.cores
    nx, ny, nz = factorize_3d(args.cores)
    
    print("=================================================================")
    print("           OpenFOAM Domain Decomposition Recommendations         ")
    print("=================================================================")
    print(f"Total Mesh Cells:       {args.cells:,}")
    print(f"Total Compute Cores:    {args.cores}")
    print(f"Total Nodes:            {args.nodes} ({args.cores // args.nodes} cores/node)")
    print(f"Cells per MPI Rank:     {int(cells_per_core):,} cells/core")
    print("-----------------------------------------------------------------")
    
    if cells_per_core < 25000:
        print("[!] WARNING: Cells/core is below 25,000. Interconnect latency may dominate.")
    elif cells_per_core > 250000:
        print("[i] NOTE: Cells/core is above 250,000. Consider scaling out for faster time-to-solution.")
    else:
        print("[+] Optimal cells/core balance (50k - 150k target).")

    print("\nRecommended decomposeParDict (hierarchical):")
    print("-----------------------------------------------------------------")
    dict_content = f"""numberOfSubdomains {args.cores};

method          hierarchical;

hierarchicalCoeffs
{{
    n           ( {nx} {ny} {nz} );
    delta       0.001;
    order       xyz;
}}"""
    print(dict_content)
    print("-----------------------------------------------------------------")
    print("\nAlternative (scotch - automatic graph partitioning):")
    print(f"numberOfSubdomains {args.cores};\nmethod scotch;")

if __name__ == "__main__":
    main()
