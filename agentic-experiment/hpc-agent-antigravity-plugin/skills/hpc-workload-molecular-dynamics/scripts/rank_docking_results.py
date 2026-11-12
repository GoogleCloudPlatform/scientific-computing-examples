#!/usr/bin/env python3
"""
Aggregates docking scores across all parallel Slurm/Batch task outputs and
ranks the top N highest affinity compounds. Supports single-molecule and
multi-molecule batch log files.
"""

import argparse
import csv
import glob
import os
import re
from typing import Any, Dict, List, Optional

def parse_vina_logs(results_dir: str, top_n: int = 50, output_csv: Optional[str] = None) -> List[Dict[str, Any]]:
    log_files = glob.glob(os.path.join(results_dir, "**/*.log"), recursive=True)
    print(f"[+] Found {len(log_files)} docking log files to parse...")

    score_pattern = re.compile(r"^\s*1\s+([-\d.]+)\s+", re.MULTILINE)
    mol_id_pattern = re.compile(r"(?:Ligand|Compound|ID|MODEL|Processing|Docking):\s*(\S+)", re.IGNORECASE)

    results = []

    for log_path in log_files:
        try:
            with open(log_path, "r", errors="ignore") as f:
                content = f.read()

            matches = list(score_pattern.finditer(content))
            if not matches:
                continue

            base_name = os.path.splitext(os.path.basename(log_path))[0]
            last_pos = 0

            for idx, match in enumerate(matches, start=1):
                score = float(match.group(1))
                block_preceding = content[last_pos:match.start()]
                last_pos = match.end()

                # Extract molecule name from preceding context
                id_match = mol_id_pattern.search(block_preceding)
                if id_match:
                    mol_name = id_match.group(1)
                elif len(matches) == 1:
                    mol_name = base_name
                else:
                    mol_name = f"{base_name}_mol_{idx}"

                results.append({
                    "molecule": mol_name,
                    "affinity_kcal_mol": score,
                    "log_path": log_path,
                })
        except Exception:
            continue

    # Sort ascending (lower kcal/mol is stronger binding)
    results.sort(key=lambda x: x["affinity_kcal_mol"])
    top_hits = results[:top_n]

    print(f"\nTop {min(top_n, len(top_hits))} Binding Hits:")
    print("-----------------------------------------------------------------")
    print(f"{'Rank':<6} {'Molecule ID':<30} {'Affinity (kcal/mol)':<20}")
    print("-----------------------------------------------------------------")
    for rank, hit in enumerate(top_hits, 1):
        print(f"{rank:<6} {hit['molecule']:<30} {hit['affinity_kcal_mol']:<20.2f}")
    print("-----------------------------------------------------------------")

    if output_csv:
        with open(output_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["molecule", "affinity_kcal_mol", "log_path"])
            writer.writeheader()
            writer.writerows(top_hits)
        print(f"\n[✓] Results exported to {output_csv}")

    return top_hits

def main():
    parser = argparse.ArgumentParser(description="Rank distributed docking results")
    parser.add_argument("--results-dir", required=True, help="Directory containing docking logs")
    parser.add_argument("--top-n", type=int, default=50, help="Number of top hits to extract")
    parser.add_argument("--output", default="top_leads.csv", help="Output CSV path")
    args = parser.parse_args()

    parse_vina_logs(args.results_dir, args.top_n, args.output)

if __name__ == "__main__":
    main()
