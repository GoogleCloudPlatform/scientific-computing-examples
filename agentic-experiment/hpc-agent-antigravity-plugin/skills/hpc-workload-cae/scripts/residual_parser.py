#!/usr/bin/env python3
"""
Residual and Convergence Parser for CFD Solvers (OpenFOAM / Fluent).
Parses solver output logs in real-time or post-run to verify convergence.
"""

import argparse
import re
import sys
from typing import Any, Dict, List

def parse_openfoam_log(logfile: str) -> List[Dict[str, Any]]:
    time_step_pattern = re.compile(r"^Time = ([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)")
    residual_pattern = re.compile(
        r"Solving for (Ux|Uy|Uz|p|p_rgh|k|omega|epsilon|nuTilda|h|e|T|gammaInt|ReThetat|pcorr), "
        r"Initial residual = ([0-9.eE+-]+), Final residual = ([0-9.eE+-]+)"
    )

    current_time = None
    residuals = {}
    history = []
    
    try:
        with open(logfile, "r") as f:
            for line in f:
                time_match = time_step_pattern.match(line)
                if time_match:
                    if current_time is not None and residuals:
                        history.append({"time": current_time, "residuals": dict(residuals)})
                    current_time = time_match.group(1)
                    residuals = {}
                    continue
                
                res_match = residual_pattern.search(line)
                if res_match:
                    var, init_res, final_res = res_match.groups()
                    residuals[var] = float(final_res)

            # Flush last timestep at EOF
            if current_time is not None and residuals:
                history.append({"time": current_time, "residuals": dict(residuals)})

        if history:
            print(f"[+] Total Timesteps Parsed: {len(history)}")
            latest = history[-1]
            print(f"Latest Timestep: {latest['time']}")
            print("Latest Residuals:")
            for k, v in latest["residuals"].items():
                status = "OK" if v < 1e-4 else "CONVERGING"
                print(f"  - {k:10s}: {v:12.4e} [{status}]")
        else:
            print("[!] No completed timesteps found in log.")
        return history
    except Exception as e:
        print(f"[-] Error reading log file: {e}")
        return history

def parse_fluent_log(logfile: str) -> List[Dict[str, Any]]:
    """Parse Fluent residual iteration table from log file."""
    header_pattern = re.compile(r"^\s*iter\s+continuity\s+", re.IGNORECASE)
    data_pattern = re.compile(r"^\s*(\d+)\s+([0-9.eE+-]+.*)")
    
    headers = []
    history = []
    in_table = False
    
    try:
        with open(logfile, "r") as f:
            for line in f:
                if header_pattern.match(line):
                    in_table = True
                    headers = line.strip().split()
                    continue
                
                if in_table:
                    match = data_pattern.match(line)
                    if match:
                        tokens = line.strip().split()
                        iter_num = tokens[0]
                        res_dict = {}
                        for idx, val_str in enumerate(tokens[1:], start=1):
                            if idx < len(headers):
                                col_name = headers[idx]
                                try:
                                    res_dict[col_name] = float(val_str)
                                except ValueError:
                                    pass
                        if res_dict:
                            history.append({"time": iter_num, "residuals": res_dict})
                    elif line.strip() == "" or "solution is converged" in line.lower():
                        pass

        if history:
            print(f"[+] Total Fluent Iterations Parsed: {len(history)}")
            latest = history[-1]
            print(f"Latest Iteration: {latest['time']}")
            print("Latest Residuals:")
            for k, v in latest["residuals"].items():
                status = "OK" if v < 1e-4 else "CONVERGING"
                print(f"  - {k:12s}: {v:12.4e} [{status}]")
        else:
            print("[!] No completed iterations found in Fluent log.")
        return history
    except Exception as e:
        print(f"[-] Error reading Fluent log file: {e}")
        return history

def main():
    parser = argparse.ArgumentParser(description="CFD Residual Parser")
    parser.add_argument("--logfile", required=True, help="Path to solver log file")
    parser.add_argument("--solver", default="simpleFoam", choices=["simpleFoam", "pimpleFoam", "fluent"], help="Solver type")
    args = parser.parse_args()

    print(f"Parsing log: {args.logfile} (Solver: {args.solver})")
    if args.solver == "fluent":
        parse_fluent_log(args.logfile)
    else:
        parse_openfoam_log(args.logfile)

if __name__ == "__main__":
    main()
