#!/usr/bin/env python3
"""
Splits large chemical libraries (SDF, PDBQT, SMILES, CSV) into batches for distributed
Slurm job array or Google Batch virtual screening execution.
"""

import argparse
import os
import re
from typing import List, Optional

def detect_format(input_file: str, sample_lines: int = 100) -> str:
    """Auto-detect file format from extension or initial file contents."""
    lower_name = input_file.lower()
    if lower_name.endswith(".sdf"):
        return "sdf"
    elif lower_name.endswith(".pdbqt"):
        return "pdbqt"
    elif lower_name.endswith((".smi", ".smiles")):
        return "smi"
    elif lower_name.endswith(".csv"):
        return "csv"
    elif lower_name.endswith(".tsv"):
        return "tsv"

    # Content-based sniffing
    try:
        with open(input_file, "r", errors="ignore") as f:
            for _ in range(sample_lines):
                line = f.readline()
                if not line:
                    break
                if line.strip() == "$$$$":
                    return "sdf"
                if line.strip().startswith("ENDMDL") or line.strip().startswith("MODEL"):
                    return "pdbqt"
    except Exception:
        pass

    return "line"

def split_sdf(input_file: str, chunk_size: int, output_dir: str) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    chunk_idx = 1
    mol_count = 0
    current_lines = []
    chunk_paths = []
    
    with open(input_file, "r", errors="ignore") as f:
        for line in f:
            current_lines.append(line)
            if line.strip() == "$$$$":
                mol_count += 1
                if mol_count >= chunk_size:
                    out_path = os.path.join(output_dir, f"chunk_{chunk_idx:04d}.sdf")
                    with open(out_path, "w") as out_f:
                        out_f.writelines(current_lines)
                    chunk_paths.append(out_path)
                    chunk_idx += 1
                    mol_count = 0
                    current_lines = []

    if current_lines:
        out_path = os.path.join(output_dir, f"chunk_{chunk_idx:04d}.sdf")
        with open(out_path, "w") as out_f:
            out_f.writelines(current_lines)
        chunk_paths.append(out_path)

    return chunk_paths

def split_pdbqt(input_file: str, chunk_size: int, output_dir: str) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    chunk_idx = 1
    mol_count = 0
    current_lines = []
    chunk_paths = []
    
    with open(input_file, "r", errors="ignore") as f:
        for line in f:
            current_lines.append(line)
            if line.strip().startswith("ENDMDL"):
                mol_count += 1
                if mol_count >= chunk_size:
                    out_path = os.path.join(output_dir, f"chunk_{chunk_idx:04d}.pdbqt")
                    with open(out_path, "w") as out_f:
                        out_f.writelines(current_lines)
                    chunk_paths.append(out_path)
                    chunk_idx += 1
                    mol_count = 0
                    current_lines = []

    if current_lines:
        out_path = os.path.join(output_dir, f"chunk_{chunk_idx:04d}.pdbqt")
        with open(out_path, "w") as out_f:
            out_f.writelines(current_lines)
        chunk_paths.append(out_path)

    return chunk_paths

def split_line_based(input_file: str, chunk_size: int, output_dir: str, ext: str = "smi", has_header: bool = False) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    chunk_idx = 1
    mol_count = 0
    current_lines = []
    header_line = None
    chunk_paths = []
    
    with open(input_file, "r", errors="ignore") as f:
        if has_header:
            header_line = f.readline()
            
        for line in f:
            if not line.strip():
                continue
            current_lines.append(line)
            mol_count += 1
            if mol_count >= chunk_size:
                out_path = os.path.join(output_dir, f"chunk_{chunk_idx:04d}.{ext}")
                with open(out_path, "w") as out_f:
                    if header_line:
                        out_f.write(header_line)
                    out_f.writelines(current_lines)
                chunk_paths.append(out_path)
                chunk_idx += 1
                mol_count = 0
                current_lines = []

    if current_lines:
        out_path = os.path.join(output_dir, f"chunk_{chunk_idx:04d}.{ext}")
        with open(out_path, "w") as out_f:
            if header_line:
                out_f.write(header_line)
            out_f.writelines(current_lines)
        chunk_paths.append(out_path)

    return chunk_paths

def split_library(input_file: str, chunk_size: int, output_dir: str, file_format: str = "auto") -> List[str]:
    if file_format == "auto":
        fmt = detect_format(input_file)
    else:
        fmt = file_format.lower()
        
    print(f"[+] Detected/Selected Library Format: {fmt.upper()}")
    
    if fmt == "sdf":
        chunks = split_sdf(input_file, chunk_size, output_dir)
    elif fmt == "pdbqt":
        chunks = split_pdbqt(input_file, chunk_size, output_dir)
    elif fmt == "csv":
        chunks = split_line_based(input_file, chunk_size, output_dir, ext="csv", has_header=True)
    elif fmt == "tsv":
        chunks = split_line_based(input_file, chunk_size, output_dir, ext="tsv", has_header=True)
    else:  # smi / line
        chunks = split_line_based(input_file, chunk_size, output_dir, ext="smi", has_header=False)

    print(f"\n[✓] Library split complete! Total chunks created: {len(chunks)}")
    if chunks:
        print(f"Submit Slurm array with: sbatch --array=1-{len(chunks)}%32 examples/vina_screening_array.sh")
    return chunks

def main():
    parser = argparse.ArgumentParser(description="Split chemical library for distributed docking")
    parser.add_argument("--input", "--input-file", "--input-sdf", dest="input_file", required=True, help="Input chemical library file (SDF, PDBQT, SMI, CSV)")
    parser.add_argument("--format", default="auto", choices=["auto", "sdf", "pdbqt", "smi", "csv", "tsv", "line"], help="Library file format")
    parser.add_argument("--chunk-size", type=int, default=5000, help="Number of molecules per chunk")
    parser.add_argument("--output-dir", default="./docking_chunks", help="Output directory for chunks")
    args = parser.parse_args()

    split_library(args.input_file, args.chunk_size, args.output_dir, args.format)

if __name__ == "__main__":
    main()
