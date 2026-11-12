#!/usr/bin/env python3
"""
DeepMind Science Skills <-> GCP HPC Molecular Dynamics, HTVS & Nextflow Bridge.

Connects tools from `https://github.com/google-deepmind/science-skills` directly
with Google Cloud HPC simulation, virtual screening, VMD visualization, and
Nextflow Cloud Batch pipelines:

1. `afdb-gatekeeper`:
   Bridges `alphafold_database_fetch_and_analyze`, `uniprot_database`, `pdb_database`,
   `foldseek_structural_search`, and `pymol` with `gromacs_tuner.py` and `visualizer.py`.
   Evaluates AFDB pLDDT/PAE confidence, detects intrinsically disordered tails (pLDDT < 50)
   that bloat explicit-solvent MD water boxes, computes cropped rigid core domain atom
   counts, and outputs tuned GROMACS + VMD + PyMOL commands.

2. `chembl-htvs-bridge`:
   Bridges `chembl_database` (`chembl_api.py`) and `pubchem_database` (`pubchem_api.py`)
   with `split_docking_library.py` and `rank_docking_results.py`. Converts ChEMBL/PubChem
   JSON outputs into deduplicated, bioactivity-normalized (nM) SMILES/CSV libraries for
   Slurm job array docking (`vina_screening_array.sh`), and enriches top docking leads
   with experimental IC50/Ki, clinical phase, and OpenTargets follow-up commands.

3. `nextflow-variant-bridge`:
   Bridges Nextflow on Google Cloud Batch (`nextflow_batch_optimizer.py` GATK/DeepVariant)
   to `alphagenome_variant_impact_score`, `alphagenome_single_variant_analysis`,
   `clinvar_database`, `gnomad_database`, `ensembl_database`, and `gtex_database`.
"""

import argparse
import csv
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Import tune_gromacs from sibling gromacs_tuner.py when available
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    from gromacs_tuner import tune_gromacs
except ImportError:
    tune_gromacs = None  # type: ignore


UNIT_TO_NM_FACTOR: Dict[str, float] = {
    "m": 1e9,
    "mol/l": 1e9,
    "mm": 1e6,
    "mmol/l": 1e6,
    "um": 1e3,
    "µm": 1e3,
    "μm": 1e3,
    "umol/l": 1e3,
    "nm": 1.0,
    "nmol/l": 1.0,
    "pm": 1e-3,
    "pmol/l": 1e-3,
    "fm": 1e-6,
    "fmol/l": 1e-6,
}

# Mass-per-volume to (nM * MW) conversion factors: nM = (value * factor) / MW
MASS_CONC_TO_NM_MW_FACTOR: Dict[str, float] = {
    "ug/ml": 1e6,
    "µg/ml": 1e6,
    "μg/ml": 1e6,
    "ug.ml-1": 1e6,
    "mg/l": 1e6,
    "ng/ml": 1e3,
    "ug/l": 1e3,
    "mg/ml": 1e9,
    "g/l": 1e9,
}


def normalize_concentration_to_nm(
    value: Optional[Union[float, int, str]],
    units: Optional[str],
    mw: Optional[Union[float, int, str]] = None,
) -> Optional[float]:
    """
    Normalizes molar bioactivity concentrations (M, mM, uM/µM, nM, pM, fM) to nanomolar (nM),
    matching `uv run scripts/chembl_api.py activity --normalize`. Also converts mass/volume
    units (`ug/mL`, `ng/mL`, `mg/L`) when molecular weight (`mw` in g/mol) is provided.
    Returns None for non-convertible units (`%`, `mg/kg`, etc.).
    """
    if value is None or units is None:
        return None
    try:
        numeric_val = float(value)
    except (ValueError, TypeError):
        return None
    if numeric_val < 0:
        return None
    unit_clean = units.strip().lower()
    factor = UNIT_TO_NM_FACTOR.get(unit_clean)
    if factor is not None:
        return round(numeric_val * factor, 6)

    mass_factor = MASS_CONC_TO_NM_MW_FACTOR.get(unit_clean)
    if mass_factor is not None and mw is not None:
        try:
            mw_val = float(mw)
            if mw_val > 0:
                return round((numeric_val * mass_factor) / mw_val, 6)
        except (ValueError, TypeError):
            return None
    return None


def _fallback_tune_gromacs(
    atoms: int, gpus: int, gpu_type: str, cpu_cores: int, nodes: int = 1
) -> Dict[str, Any]:
    if tune_gromacs is not None:
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            raw_res = tune_gromacs(
                atoms=atoms,
                gpus=gpus,
                gpu_type=gpu_type,
                cpu_cores=cpu_cores,
                nodes=nodes,
            )
        norm = dict(raw_res)
        total_ranks = norm.get("total_mpi_ranks") or norm.get("mpi_ranks") or norm.get("total_ranks")
        norm["total_mpi_ranks"] = str(total_ranks)
        norm["mpi_ranks"] = int(total_ranks) if total_ranks is not None else 0
        norm["threads_per_rank"] = str(norm.get("threads_per_rank", 1))
        if "srun_cmd" not in norm and "command" in norm:
            norm["srun_cmd"] = norm["command"]
        if "command" not in norm and "srun_cmd" in norm:
            norm["command"] = norm["srun_cmd"]
        if "mode_desc" not in norm and "offload_mode" in norm:
            norm["mode_desc"] = norm["offload_mode"]
        return norm
    threads_per_rank = max(1, cpu_cores // max(1, gpus)) if gpus > 0 else 2
    ranks_per_node = gpus if gpus > 0 else max(1, cpu_cores // 2)
    total_mpi_ranks = ranks_per_node * nodes
    offload = "-nb gpu -pme gpu -bonded gpu -update gpu" if gpus > 0 else ""
    cmd = (
        f"srun --ntasks={total_mpi_ranks} --ntasks-per-node={ranks_per_node} "
        f"--cpus-per-task={threads_per_rank} gmx_mpi mdrun -v -deffnm topol "
        f"-ntomp {threads_per_rank} {offload} -pin on"
    ).strip()
    return {
        "nodes": str(nodes),
        "total_mpi_ranks": str(total_mpi_ranks),
        "mpi_ranks": total_mpi_ranks,
        "threads_per_rank": str(threads_per_rank),
        "mode_desc": "FULL GPU RESIDENT" if gpus > 0 else "CPU-ONLY VECTORIZED",
        "srun_cmd": cmd,
        "command": cmd,
    }


def _segment_plddt_regions(
    residue_plddts: List[float],
    confident_cutoff: float = 70.0,
    disorder_cutoff: float = 50.0,
    min_domain_len: int = 5,
    min_linker_len: int = 5,
) -> Dict[str, Any]:
    """
    Segments per-residue pLDDTs into contiguous confident domains and identifies both
    N/C-terminal disordered tails and internal disordered linkers (pLDDT < 50).
    Filters out isolated 1-2 residue spikes so stray terminal residues do not prevent cropping.
    """
    n = len(residue_plddts)
    if n == 0:
        return {
            "core_start": 1,
            "core_end": 1,
            "confident_domains": [(1, 1)],
            "internal_disordered_linkers": [],
        }

    # Find contiguous runs where pLDDT >= confident_cutoff (bridging 1-2 residue dips >= disorder_cutoff)
    raw_runs: List[Tuple[int, int]] = []
    in_run = False
    run_start = 1
    for idx, val in enumerate(residue_plddts, start=1):
        if val >= confident_cutoff:
            if not in_run:
                run_start = idx
                in_run = True
        else:
            if in_run:
                raw_runs.append((run_start, idx - 1))
                in_run = False
    if in_run:
        raw_runs.append((run_start, n))

    # Merge runs separated by very short (< min_linker_len) non-disordered gaps
    merged_runs: List[Tuple[int, int]] = []
    for s, e in raw_runs:
        if not merged_runs:
            merged_runs.append((s, e))
        else:
            prev_s, prev_e = merged_runs[-1]
            gap_vals = residue_plddts[prev_e : s - 1]
            num_very_low = sum(1 for v in gap_vals if v < disorder_cutoff)
            if (s - prev_e - 1) < min_linker_len and num_very_low < min_linker_len:
                merged_runs[-1] = (prev_s, e)
            else:
                merged_runs.append((s, e))

    # Filter out tiny isolated spikes (< min_domain_len) unless no larger domain exists
    min_len = min(min_domain_len, max(1, n // 4))
    confident_domains = [(s, e) for s, e in merged_runs if (e - s + 1) >= min_len]
    if not confident_domains and merged_runs:
        confident_domains = [max(merged_runs, key=lambda r: r[1] - r[0])]

    if confident_domains:
        core_start = confident_domains[0][0]
        core_end = confident_domains[-1][1]
    else:
        core_start = 1
        core_end = n
        confident_domains = [(1, n)]

    # Identify internal disordered linkers (contiguous runs of pLDDT < disorder_cutoff inside [core_start, core_end])
    internal_linkers: List[Dict[str, int]] = []
    in_dis = False
    dis_start = core_start
    for idx in range(core_start, core_end + 1):
        val = residue_plddts[idx - 1]
        if val < disorder_cutoff:
            if not in_dis:
                dis_start = idx
                in_dis = True
        else:
            if in_dis:
                dis_end = idx - 1
                if (dis_end - dis_start + 1) >= min_linker_len and dis_start > core_start and dis_end < core_end:
                    internal_linkers.append(
                        {"start": dis_start, "end": dis_end, "length": dis_end - dis_start + 1}
                    )
                in_dis = False

    return {
        "core_start": core_start,
        "core_end": core_end,
        "confident_domains": confident_domains,
        "internal_disordered_linkers": internal_linkers,
    }


def _parse_pae_data(
    pae_data: Optional[Union[str, Dict[str, Any], List[Any]]],
    fallback_domains: List[Tuple[int, int]],
    window_size: int = 10,
    pae_cutoff: float = 10.0,
) -> Dict[str, Any]:
    """
    Parses AlphaFold PAE data from a file path, dict (`predicted_aligned_error` or `domains`),
    or 2D PAE matrix ($N \\times N$), matching `alphafold_database_fetch_and_analyze/scripts/analyze_pae.py`.
    Detects rigid PAE blocks, inter-domain PAE independence, and multimeric/inter-chain PAE asymmetry.
    """
    loaded: Any = pae_data
    if isinstance(pae_data, str):
        if os.path.exists(pae_data):
            with open(pae_data, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        else:
            loaded = None

    domains: List[Tuple[int, int]] = []
    matrix: Optional[List[List[float]]] = None

    if isinstance(loaded, list) and len(loaded) > 0:
        if isinstance(loaded[0], dict):
            loaded = loaded[0]
        elif isinstance(loaded[0], list):
            matrix = loaded  # Raw 2D matrix

    if isinstance(loaded, dict):
        if "domains" in loaded and isinstance(loaded["domains"], list):
            for dom in loaded["domains"]:
                if isinstance(dom, (list, tuple)) and len(dom) == 2:
                    domains.append((int(dom[0]), int(dom[1])))
                elif isinstance(dom, dict) and "start" in dom and "end" in dom:
                    domains.append((int(dom["start"]), int(dom["end"])))
        if "predicted_aligned_error" in loaded and isinstance(loaded["predicted_aligned_error"], list):
            matrix = loaded["predicted_aligned_error"]
        elif "pae" in loaded and isinstance(loaded["pae"], list):
            matrix = loaded["pae"]

    mean_pae: Optional[float] = None
    max_asymmetry: float = 0.0
    inter_domain_pae: Optional[float] = None

    if matrix and len(matrix) > 0 and isinstance(matrix[0], list):
        n = len(matrix)
        total_pae = 0.0
        count = 0
        for i in range(n):
            row = matrix[i]
            for j in range(min(n, len(row))):
                val_ij = float(row[j])
                total_pae += val_ij
                count += 1
                if j > i and j < len(matrix) and i < len(matrix[j]):
                    asym = abs(val_ij - float(matrix[j][i]))
                    if asym > max_asymmetry:
                        max_asymmetry = asym
        mean_pae = round(total_pae / max(1, count), 2)

        # Segment rigid domains along diagonal if not explicitly supplied
        if not domains:
            w = max(2, min(window_size, max(2, n // 4)))
            confident_res: List[bool] = []
            for i in range(n):
                w_start = max(0, i - w // 2)
                w_end = min(n, i + w // 2 + 1)
                sub_vals = [
                    float(matrix[r][c])
                    for r in range(w_start, w_end)
                    for c in range(w_start, w_end)
                ]
                w_mean = sum(sub_vals) / max(1, len(sub_vals))
                confident_res.append(w_mean <= pae_cutoff)

            raw_doms: List[Tuple[int, int]] = []
            in_dom = False
            d_start = 1
            for idx, is_conf in enumerate(confident_res, start=1):
                if is_conf and not in_dom:
                    d_start = idx
                    in_dom = True
                elif not is_conf and in_dom:
                    if (idx - d_start) >= max(3, w // 2):
                        raw_doms.append((d_start, idx - 1))
                    in_dom = False
            if in_dom and (n - d_start + 1) >= max(3, w // 2):
                raw_doms.append((d_start, n))

            # Merge domains whose cross-block PAE is also low (<= pae_cutoff)
            for s, e in raw_doms:
                if not domains:
                    domains.append((s, e))
                else:
                    ps, pe = domains[-1]
                    cross_vals = [
                        (float(matrix[r - 1][c - 1]) + float(matrix[c - 1][r - 1])) / 2.0
                        for r in range(ps, pe + 1)
                        for c in range(s, e + 1)
                    ]
                    cross_mean = sum(cross_vals) / max(1, len(cross_vals))
                    if cross_mean <= pae_cutoff and (s - pe) <= w:
                        domains[-1] = (ps, e)
                    else:
                        domains.append((s, e))

        # Compute inter-domain mean PAE when >= 2 domains exist
        if len(domains) >= 2:
            d1_s, d1_e = domains[0]
            d2_s, d2_e = domains[1]
            cross = [
                (float(matrix[r - 1][c - 1]) + float(matrix[c - 1][r - 1])) / 2.0
                for r in range(max(1, d1_s), min(n, d1_e) + 1)
                for c in range(max(1, d2_s), min(n, d2_e) + 1)
            ]
            if cross:
                inter_domain_pae = round(sum(cross) / len(cross), 2)

    if not domains:
        domains = list(fallback_domains)

    return {
        "domains": domains,
        "mean_pae": mean_pae,
        "inter_domain_pae": inter_domain_pae,
        "max_pae_asymmetry": round(max_asymmetry, 2),
        "independent_domains_detected": bool(inter_domain_pae is not None and inter_domain_pae > 15.0),
    }


def analyze_afdb_for_md(
    uniprot_id: str,
    metadata: Optional[Union[str, Dict[str, Any]]] = None,
    pae_data: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
    residue_plddts: Optional[List[float]] = None,
    sequence_length: Optional[int] = None,
    active_site_residues: Optional[List[int]] = None,
    gpus: int = 1,
    gpu_type: str = "H100",
    cpu_cores: int = 16,
    nodes: int = 1,
    disorder_threshold: float = 0.30,
) -> Dict[str, Any]:
    """
    Pre-MD / Pre-AF3 Gatekeeper that analyzes AlphaFold DB (AFDB) structural confidence
    (`alphafold_database_fetch_and_analyze`) and prepares downstream GROMACS, VMD, and PyMOL commands.
    """
    uid = (uniprot_id or "").strip().upper()
    if not uid or not re.match(r"^[A-Z0-9_-]{3,20}$", uid):
        raise ValueError(f"Invalid UniProt accession ID: '{uniprot_id}'")

    meta_dict: Dict[str, Any] = {}
    if isinstance(metadata, str):
        if os.path.exists(metadata):
            with open(metadata, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list) and len(loaded) > 0 and isinstance(loaded[0], dict):
                meta_dict = loaded[0]
            elif isinstance(loaded, dict):
                meta_dict = loaded
    elif isinstance(metadata, dict):
        meta_dict = dict(metadata)

    if residue_plddts is None and "residue_plddts" in meta_dict:
        residue_plddts = [float(x) for x in meta_dict["residue_plddts"]]

    core_start = 1
    core_end = sequence_length or int(meta_dict.get("uniprotEnd") or meta_dict.get("sequence_length") or 129)
    internal_linkers: List[Dict[str, int]] = []
    plddt_domains: List[Tuple[int, int]] = []

    if residue_plddts and len(residue_plddts) > 0:
        seq_len = len(residue_plddts)
        mean_plddt = sum(residue_plddts) / seq_len
        p_very_high = sum(1 for v in residue_plddts if v >= 90.0) / seq_len
        p_confident = sum(1 for v in residue_plddts if 70.0 <= v < 90.0) / seq_len
        p_low = sum(1 for v in residue_plddts if 50.0 <= v < 70.0) / seq_len
        p_very_low = sum(1 for v in residue_plddts if v < 50.0) / seq_len

        seg = _segment_plddt_regions(residue_plddts)
        core_start = seg["core_start"]
        core_end = seg["core_end"]
        plddt_domains = seg["confident_domains"]
        internal_linkers = seg["internal_disordered_linkers"]
    else:
        seq_len = max(1, core_end)
        mean_plddt = float(meta_dict.get("globalMetricValue", meta_dict.get("mean_plddt", 88.5)))
        p_very_high = float(meta_dict.get("fractionPlddtVeryHigh", 0.62))
        p_confident = float(meta_dict.get("fractionPlddtConfident", 0.26))
        p_low = float(meta_dict.get("fractionPlddtLow", 0.07))
        p_very_low = float(meta_dict.get("fractionPlddtVeryLow", 0.05))
        # Estimate core domain if N/C disordered fraction is present
        trimmed_residues = int(round(seq_len * p_very_low))
        if trimmed_residues > 0 and trimmed_residues < seq_len:
            n_trim = trimmed_residues // 2
            c_trim = trimmed_residues - n_trim
            core_start = 1 + n_trim
            core_end = max(core_start, seq_len - c_trim)
        plddt_domains = [(core_start, core_end)]

    pae_info = _parse_pae_data(pae_data, fallback_domains=plddt_domains)
    pae_domains = pae_info["domains"]

    # If PAE matrix segmented a tighter core and pLDDTs were not explicitly provided, adopt PAE bounds
    if pae_data is not None and not residue_plddts and pae_domains:
        core_start = pae_domains[0][0]
        core_end = pae_domains[-1][1]

    # Sum confident residue lengths across domains (excluding long internal disordered linkers if multi-domain)
    if len(plddt_domains) > 1 and internal_linkers:
        confident_residue_count = sum(e - s + 1 for s, e in plddt_domains)
    else:
        confident_residue_count = max(1, core_end - core_start + 1)

    core_length = max(1, core_end - core_start + 1)
    # Explicit-solvent water box atom estimation:
    # Uncropped proteins with disordered tails/linkers require significantly larger periodic water boxes
    # because extended disordered chains increase maximum diameter D (`V ~ (D + 2*d)^3`).
    disorder_inflation = 1.0 + (2.2 * p_very_low)
    full_solvated_atoms = int(round(seq_len * 260 * disorder_inflation))
    cropped_solvated_atoms = int(round(confident_residue_count * 260))

    has_long_internal_linker = any(lk["length"] >= 15 for lk in internal_linkers)
    needs_cropping = (
        p_very_low >= disorder_threshold
        or mean_plddt < 70.0
        or has_long_internal_linker
        or pae_info["independent_domains_detected"]
    )
    recommended_atoms = cropped_solvated_atoms if needs_cropping else full_solvated_atoms

    warning_msg: Optional[str] = None
    if needs_cropping:
        savings_pct = round(
            100.0 * (1.0 - (cropped_solvated_atoms / max(1, full_solvated_atoms))), 1
        )
        linker_note = ""
        if internal_linkers:
            lk_ranges = ", ".join(f"{lk['start']}-{lk['end']}" for lk in internal_linkers)
            linker_note = f" Internal disordered linker(s) detected at resid {lk_ranges}."
        pae_note = ""
        if pae_info["independent_domains_detected"]:
            pae_note = (
                f" High inter-domain PAE ({pae_info['inter_domain_pae']} A > 15 A) indicates "
                f"uncoupled domain orientations; consider simulating rigid PAE domains independently."
            )
        warning_msg = (
            f"DISORDER GATEKEEPER WARNING: {uid} has {p_very_low * 100:.1f}% very-low confidence "
            f"residues (pLDDT < 50) and mean pLDDT {mean_plddt:.1f}.{linker_note}{pae_note} "
            f"Solvating the full-length model in GROMACS/OpenMM will inflate the periodic water box "
            f"to ~{full_solvated_atoms:,} atoms. Crop to rigid core domain resid {core_start}-{core_end} "
            f"(~{cropped_solvated_atoms:,} atoms, saving {savings_pct}% solvent overhead), or run "
            f"AlphaFold 3 (`examples/af3_inference_sbatch.sh`) with binding partners/ligands."
        )

    gmx_tuning = _fallback_tune_gromacs(
        atoms=recommended_atoms,
        gpus=gpus,
        gpu_type=gpu_type,
        cpu_cores=cpu_cores,
        nodes=nodes,
    )

    active_resid_str = (
        " ".join(str(r) for r in active_site_residues)
        if active_site_residues
        else f"{core_start} {core_end}"
    )

    return {
        "uniprot_id": uid,
        "sequence_length": seq_len,
        "mean_plddt": round(mean_plddt, 2),
        "confidence_fractions": {
            "very_high_ge_90": round(p_very_high, 4),
            "confident_70_to_90": round(p_confident, 4),
            "low_50_to_70": round(p_low, 4),
            "very_low_lt_50": round(p_very_low, 4),
        },
        "needs_domain_cropping": needs_cropping,
        "disorder_gatekeeper_warning": warning_msg,
        "recommended_core_domain": {
            "start_residue": core_start,
            "end_residue": core_end,
            "length": core_length,
            "confident_residue_count": confident_residue_count,
        },
        "internal_disordered_linkers": internal_linkers,
        "pae_rigid_domains": [{"start": s, "end": e} for s, e in pae_domains],
        "pae_metrics": {
            "mean_pae": pae_info["mean_pae"],
            "inter_domain_pae": pae_info["inter_domain_pae"],
            "max_pae_asymmetry": pae_info["max_pae_asymmetry"],
            "independent_domains_detected": pae_info["independent_domains_detected"],
        },
        "estimated_solvated_atoms": {
            "full_length": full_solvated_atoms,
            "cropped_core": cropped_solvated_atoms,
            "recommended_for_md": recommended_atoms,
        },
        "gromacs_tuning": gmx_tuning,
        "science_skills_commands": {
            "fetch_afdb": f"uv run scripts/fetch_structure.py {uid} --output-dir ./afdb_{uid}",
            "analyze_plddt": f"uv run scripts/analyze_plddt.py ./afdb_{uid}/AF-{uid}-F1-metadata.json",
            "analyze_pae": f"uv run scripts/analyze_pae.py ./afdb_{uid}/AF-{uid}-F1-predicted_aligned_error_v4.json",
            "uniprot_active_sites": f"uv run scripts/uniprot_tools.py get {uid} --format json > ./afdb_{uid}/{uid}_uniprot.json",
            "pymol_static_qc": (
                f"pymol -cq -d 'load ./afdb_{uid}/AF-{uid}-F1-model_v4.cif, {uid}; "
                f"hide everything; show cartoon, resi {core_start}-{core_end}; "
                f"spectrum b, red_yellow_green_cyan_blue, minimum=50, maximum=90; "
                f"ray 1600, 1200; png ./afdb_{uid}/{uid}_plddt_qc.png'"
            ),
        },
        "hpc_commands": {
            "gromacs_tuner": (
                f"python3 scripts/gromacs_tuner.py --atoms {recommended_atoms} "
                f"--gpus {gpus} --gpu-type {gpu_type} --cpu-cores {cpu_cores} --nodes {nodes}"
            ),
            "vmd_visualizer": (
                f"python3 scripts/visualizer.py --structure {uid}_production.gro "
                f"--trajectory {uid}_production.xtc --active-site \"resid {active_resid_str}\" "
                f"--output-tcl {uid}_vmd_scene.tcl"
            ),
        },
    }


def convert_chembl_to_htvs(
    chembl_json_data: Union[str, List[Dict[str, Any]], Dict[str, Any]],
    output_smi_path: Optional[str] = None,
    max_activity_nm: Optional[float] = 10000.0,
    max_ro5_violations: int = 2,
    chunk_size: int = 5000,
) -> Dict[str, Any]:
    """
    Converts `chembl_database` (`chembl_api.py molecule` / `activity --normalize`) or
    `pubchem_database` (`pubchem_api.py`) JSON outputs into a deduplicated, Lipinski/activity-filtered
    SMILES library (`.smi`) ready for `scripts/split_docking_library.py`.
    """
    if isinstance(chembl_json_data, str):
        with open(chembl_json_data, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = chembl_json_data

    records: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        records = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        for key in ("molecules", "activities", "results", "compounds", "data"):
            if isinstance(raw.get(key), list):
                records = [r for r in raw[key] if isinstance(r, dict)]
                break
        if not records and ("molecule_chembl_id" in raw or "canonical_smiles" in raw or "cid" in raw):
            records = [raw]

    seen_ids = set()
    seen_smiles = set()
    accepted: List[Dict[str, Any]] = []
    skipped_reasons = {
        "missing_smiles": 0,
        "duplicate": 0,
        "ro5_filtered": 0,
        "activity_filtered": 0,
        "non_molar_units": 0,
    }

    for rec in records:
        mol_id = str(
            rec.get("molecule_chembl_id")
            or rec.get("chembl_id")
            or rec.get("cid")
            or rec.get("CID")
            or rec.get("id")
            or ""
        ).strip()

        smiles = rec.get("canonical_smiles") or rec.get("CanonicalSMILES") or rec.get("smiles")
        if not smiles and isinstance(rec.get("molecule_structures"), dict):
            smiles = rec["molecule_structures"].get("canonical_smiles")
        smiles = str(smiles or "").strip()

        if not smiles:
            skipped_reasons["missing_smiles"] += 1
            continue

        if not mol_id:
            mol_id = f"CMPD_{len(accepted) + 1:05d}"

        if mol_id in seen_ids or smiles in seen_smiles:
            skipped_reasons["duplicate"] += 1
            continue

        # Check Lipinski Rule-of-5 violations if present
        mol_props = rec.get("molecule_properties") if isinstance(rec.get("molecule_properties"), dict) else {}
        ro5 = rec.get("num_ro5_violations")
        if ro5 is None:
            ro5 = mol_props.get("num_ro5_violations")
        if ro5 is not None:
            try:
                if int(ro5) > max_ro5_violations:
                    skipped_reasons["ro5_filtered"] += 1
                    continue
            except (ValueError, TypeError):
                pass

        # Extract molecular weight if available (for ug/mL -> nM conversion)
        mw = (
            rec.get("mw_freebase")
            or rec.get("full_mwt")
            or rec.get("MolecularWeight")
            or mol_props.get("mw_freebase")
            or mol_props.get("full_mwt")
        )

        # Normalize activity to nM if present
        has_activity_field = (
            "standard_value" in rec
            or "normalized_value" in rec
            or "standard_units" in rec
        )
        std_val = rec.get("standard_value")
        std_unit = rec.get("standard_units")
        if rec.get("normalized_value") is not None and str(rec.get("normalized_units", "nM")).lower() == "nm":
            try:
                norm_nm: Optional[float] = round(float(rec["normalized_value"]), 6)
            except (ValueError, TypeError):
                norm_nm = None
        elif std_val is not None:
            norm_nm = normalize_concentration_to_nm(std_val, std_unit or "nM", mw=mw)
        else:
            norm_nm = None

        if max_activity_nm is not None:
            if norm_nm is not None and norm_nm > max_activity_nm:
                skipped_reasons["activity_filtered"] += 1
                continue
            # If the record came from an activity query with non-convertible units (e.g., '%', 'mg/kg',
            # or 'ug/mL' without molecular weight), do NOT let it silently bypass the nM threshold.
            if has_activity_field and norm_nm is None and (std_val is not None or std_unit is not None):
                skipped_reasons["activity_filtered"] += 1
                skipped_reasons["non_molar_units"] += 1
                continue

        seen_ids.add(mol_id)
        seen_smiles.add(smiles)
        accepted.append(
            {
                "molecule_id": mol_id,
                "canonical_smiles": smiles,
                "pref_name": rec.get("pref_name") or rec.get("IUPACName") or "",
                "activity_nm": norm_nm,
                "pchembl_value": rec.get("pchembl_value"),
                "max_phase": rec.get("max_phase"),
            }
        )

    if output_smi_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_smi_path)), exist_ok=True)
        with open(output_smi_path, "w", encoding="utf-8") as sf:
            for item in accepted:
                sf.write(f"{item['canonical_smiles']} {item['molecule_id']}\n")

    smi_target = output_smi_path or "chembl_filtered_library.smi"
    return {
        "input_records": len(records),
        "accepted_molecules": len(accepted),
        "skipped_breakdown": skipped_reasons,
        "output_smi_path": output_smi_path,
        "molecules": accepted,
        "next_step_commands": {
            "split_library": (
                f"python3 scripts/split_docking_library.py --input {smi_target} "
                f"--chunk-size {chunk_size} --output-dir ./docking_chunks"
            ),
            "submit_slurm_array": "sbatch --array=1-100%32 examples/vina_screening_array.sh",
            "rank_results": (
                "python3 scripts/rank_docking_results.py --results-dir ./results "
                "--top-n 50 --output top_leads.csv --json-output top_leads.json"
            ),
        },
    }


def enrich_docking_hits(
    docking_hits: Union[str, List[Dict[str, Any]]],
    chembl_metadata: Union[str, List[Dict[str, Any]], Dict[str, Any]],
    output_json_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Enriches ranked docking results (`rank_docking_results.py`) with ChEMBL/PubChem
    bioactivity (`activity_nm`, `pchembl_value`), clinical `max_phase`, and canonical SMILES.
    """
    if isinstance(docking_hits, str):
        with open(docking_hits, "r", encoding="utf-8") as f:
            hits_list = json.load(f)
    else:
        hits_list = list(docking_hits)

    converted = convert_chembl_to_htvs(
        chembl_metadata,
        output_smi_path=None,
        max_activity_nm=None,
        max_ro5_violations=99,
    )
    meta_by_id: Dict[str, Dict[str, Any]] = {
        m["molecule_id"].upper(): m for m in converted["molecules"]
    }

    enriched_hits: List[Dict[str, Any]] = []
    for hit in hits_list:
        mol_name = str(hit.get("molecule", "")).strip()
        mol_key = mol_name.upper()
        affinity = float(hit.get("affinity_kcal_mol", 0.0))
        meta = meta_by_id.get(mol_key, {})

        smiles = meta.get("canonical_smiles", "")
        # Estimate heavy atom count from SMILES non-H element symbols
        heavy_atoms = max(1, len(re.findall(r"Br|Cl|[BCNOPSFIbcnops]", smiles))) if smiles else 25
        ligand_efficiency = round(-affinity / heavy_atoms, 4) if affinity < 0 else 0.0

        enriched_item = dict(hit)
        enriched_item.update(
            {
                "canonical_smiles": smiles,
                "pref_name": meta.get("pref_name", ""),
                "experimental_activity_nm": meta.get("activity_nm"),
                "pchembl_value": meta.get("pchembl_value"),
                "clinical_max_phase": meta.get("max_phase"),
                "estimated_ligand_efficiency": ligand_efficiency,
            }
        )
        enriched_hits.append(enriched_item)

    if output_json_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as out_f:
            json.dump(enriched_hits, out_f, indent=2)

    return enriched_hits


def _parse_variant_components(variant_str: str) -> Tuple[str, str, int, str, str]:
    """
    Parses a variant identifier such as 'chr7:140753336:A>T', 'chr7:140753336:A:T',
    or '7-140753336-A-T' into (chrom_with_chr, chrom_no_chr, pos, ref, alt).
    """
    m = re.match(
        r"^(?:chr)?([0-9XYM]+|MT)[:_-](\d+)[:_-]([ACGTN]+)[>:_-]([ACGTN]+)$",
        variant_str.strip(),
        re.IGNORECASE,
    )
    if m:
        chrom_no_chr = m.group(1).upper()
        if chrom_no_chr == "MT":
            chrom_no_chr = "M"
        chrom_chr = f"chr{chrom_no_chr}"
        pos = int(m.group(2))
        ref = m.group(3).upper()
        alt = m.group(4).upper()
        return chrom_chr, chrom_no_chr, pos, ref, alt
    return "chr7", "7", 140753336, "A", "T"


def generate_variant_analysis_plan(
    variants: List[str],
    tissue_ontology: str = "UBERON:0002107",
    gene_symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bridges Nextflow on Google Cloud Batch (`nextflow_batch_optimizer.py` GATK/DeepVariant)
    variant calls to DeepMind Science Skills (`alphagenome_variant_impact_score`,
    `alphagenome_single_variant_analysis`, `clinvar_database`, `gnomad_database`).
    """
    cleaned_variants = [v.strip() for v in variants if v and v.strip()]
    if not cleaned_variants:
        raise ValueError("At least one genomic variant (e.g. chr7:140753336:A>T) must be provided.")

    commands_per_variant: List[Dict[str, Any]] = []
    for var in cleaned_variants:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", var)
        chrom_chr, chrom_no_chr, pos, ref, alt = _parse_variant_components(var)
        avi_var = f"{chrom_chr}:{pos}:{ref}>{alt}"
        gnomad_var = f"{chrom_no_chr}-{pos}-{ref}-{alt}"
        gene_flag = f" --gene {gene_symbol}" if gene_symbol else ""
        commands_per_variant.append(
            {
                "variant": var,
                "alphagenome_avi_triage": (
                    f"uv run scripts/alphagenome_atlas_avi.py query \"{avi_var}\" "
                    f"--format json --output avi_{safe_id}.json"
                ),
                "alphagenome_effect_prediction": (
                    f"uv run scripts/visualize_variant_effects.py "
                    f"--chrom {chrom_chr} --pos {pos} --ref {ref} --alt {alt}{gene_flag} "
                    f"--ontology {tissue_ontology} --tracks rna_seq splice_junctions atac "
                    f"--output_dir ./effects_{safe_id}"
                ),
                "clinvar_lookup": (
                    f"uv run scripts/clinvar_api.py search --query \"{var}\" --output clinvar_{safe_id}.json"
                ),
                "gnomad_frequency": (
                    f"uv run scripts/get_variant_frequency.py --variant_id \"{gnomad_var}\" "
                    f"--output gnomad_{safe_id}.json"
                ),
            }
        )

    return {
        "total_variants": len(cleaned_variants),
        "tissue_ontology": tissue_ontology,
        "gene_symbol": gene_symbol,
        "required_env": ["ALPHAGENOME_API_KEY"],
        "safe_credential_check": 'grep -sq "^ALPHAGENOME_API_KEY=" ~/.env && echo "Configured" || echo "Missing"',
        "variant_workflows": commands_per_variant,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bridge DeepMind Science Skills outputs with GCP HPC Molecular Dynamics, HTVS, and Nextflow."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. afdb-gatekeeper
    afdb_p = subparsers.add_parser(
        "afdb-gatekeeper",
        help="Analyze AFDB structure pLDDT/PAE confidence and generate cropped GROMACS + VMD + PyMOL commands",
    )
    afdb_p.add_argument("--uniprot-id", required=True, help="UniProt accession (e.g., P00698)")
    afdb_p.add_argument("--metadata-json", default=None, help="Path to AFDB metadata JSON")
    afdb_p.add_argument("--pae-json", default=None, help="Optional path to AFDB PAE JSON file")
    afdb_p.add_argument("--seq-length", type=int, default=129, help="Protein sequence length")
    afdb_p.add_argument("--gpus", type=int, default=1, help="GPUs per node for GROMACS tuning")
    afdb_p.add_argument("--gpu-type", default="H100", help="GPU architecture (B200, H200, H100, L4)")
    afdb_p.add_argument("--cpu-cores", type=int, default=16, help="CPU cores per node")
    afdb_p.add_argument("--nodes", type=int, default=1, help="Compute nodes")

    # 2. chembl-htvs-bridge
    chembl_p = subparsers.add_parser(
        "chembl-htvs-bridge",
        help="Convert ChEMBL/PubChem JSON to HTVS SMILES library or enrich ranked docking hits",
    )
    chembl_p.add_argument("--chembl-json", required=True, help="Path to ChEMBL/PubChem JSON file")
    chembl_p.add_argument("--output-smi", default=None, help="Output .smi library path for split_docking_library.py")
    chembl_p.add_argument("--docking-hits-json", default=None, help="Optional top_leads.json from rank_docking_results.py to enrich")
    chembl_p.add_argument("--enriched-output", default=None, help="Output path for enriched docking hits JSON")
    chembl_p.add_argument("--max-activity-nm", type=float, default=10000.0, help="Max normalized bioactivity in nM")

    # 3. nextflow-variant-bridge
    nf_p = subparsers.add_parser(
        "nextflow-variant-bridge",
        help="Generate AlphaGenome, ClinVar, and gnomAD follow-up commands for Nextflow variant calls",
    )
    nf_p.add_argument("--variants", required=True, help="Comma-separated variants (e.g., chr7:140753336:A>T)")
    nf_p.add_argument("--tissue-ontology", default="UBERON:0002107", help="UBERON tissue ontology ID")
    nf_p.add_argument("--gene", default=None, help="Optional gene symbol")

    args = parser.parse_args()

    if args.subcommand == "afdb-gatekeeper":
        res = analyze_afdb_for_md(
            uniprot_id=args.uniprot_id,
            metadata=args.metadata_json,
            pae_data=args.pae_json,
            sequence_length=args.seq_length,
            gpus=args.gpus,
            gpu_type=args.gpu_type,
            cpu_cores=args.cpu_cores,
            nodes=args.nodes,
        )
        print(json.dumps(res, indent=2))
    elif args.subcommand == "chembl-htvs-bridge":
        if args.docking_hits_json:
            res_hits = enrich_docking_hits(
                docking_hits=args.docking_hits_json,
                chembl_metadata=args.chembl_json,
                output_json_path=args.enriched_output,
            )
            print(json.dumps(res_hits, indent=2))
        else:
            res_lib = convert_chembl_to_htvs(
                chembl_json_data=args.chembl_json,
                output_smi_path=args.output_smi,
                max_activity_nm=args.max_activity_nm,
            )
            print(json.dumps(res_lib, indent=2))
    elif args.subcommand == "nextflow-variant-bridge":
        var_list = [v.strip() for v in args.variants.split(",") if v.strip()]
        res_nf = generate_variant_analysis_plan(
            variants=var_list,
            tissue_ontology=args.tissue_ontology,
            gene_symbol=args.gene,
        )
        print(json.dumps(res_nf, indent=2))


if __name__ == "__main__":
    main()
