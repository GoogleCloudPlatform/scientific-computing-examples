# External Skill Ecosystems Integration Guide: Google Skills (`google/skills`) & DeepMind Science Skills (`google-deepmind/science-skills`)

This reference guide teaches agents using the Google Cloud HPC Skills Suite (`gcp-hpc-cluster-toolkit`, `hpc-workload-molecular-dynamics`, `hpc-workload-cae`, and `hpc-workload-energy`) how to discover, install, validate, and chain specialized skills from:

1. **Google Skills (`https://github.com/google/skills`)**: Official agent skills for Google Cloud infrastructure, `gcloud` CLI, Cloud Storage FUSE (`gcsfuse`), Filestore NFS, GKE Batch/HPC (`JobSet`, `Kueue`, Compact Placement), Cloud Run VPC Egress, IAM troubleshooting, Cloud Logging/Monitoring, and the Well-Architected Framework.
2. **DeepMind Science Skills (`https://github.com/google-deepmind/science-skills`)**: 40 scientific research skills covering AlphaFold DB (pLDDT/PAE), AlphaGenome variant impact, ChEMBL, PubChem, RCSB PDB, UniProt, Foldseek, OpenTargets, ClinVar, gnomAD, Ensembl, GTEx, Reactome, STRING, PyMOL, arXiv/bioRxiv/OpenAlex/PubMed literature search, and `workflow_skill_creator`.

--------------------------------------------------------------------------------

## 1. Installation & Automated Router CLI

### Installing External Skill Suites
```bash
# Install Official Google Skills (https://github.com/google/skills)
npx skills add google/skills

# Install DeepMind Science Skills (https://github.com/google-deepmind/science-skills)
npx skills add google-deepmind/science-skills/
```

### Automated Skill Discovery & Routing CLI
Use `scripts/google_skills_router.py` (in `gcp-hpc-cluster-toolkit`) to query both catalogs simultaneously by workload domain or natural-language task:
```bash
# Route skills for Molecular Dynamics + AlphaFold DB + GCS FUSE caching
python3 gcp-hpc-cluster-toolkit/scripts/google_skills_router.py \
  --domain md \
  --query "alphafold plddt gcsfuse local ssd cache"

# Route skills for High-Throughput Virtual Screening (ChEMBL / PubChem -> Vina)
python3 gcp-hpc-cluster-toolkit/scripts/google_skills_router.py \
  --domain cheminformatics \
  --query "chembl sdf bioactivity ic50 docking"

# Fetch and validate the live google/skills index.json catalog
python3 gcp-hpc-cluster-toolkit/scripts/google_skills_router.py \
  --live --domain storage --query "filestore autoscale mount eacces"
```

--------------------------------------------------------------------------------

## 2. Mandatory Operational & Security Protocols

### A. `finding-google-skills` On-Demand Discovery Protocol (`google/skills`)
When encountering a Google Cloud product, API, or troubleshooting task not fully covered by local templates:
1. **Fetch Catalog Once Per Session**:
   ```bash
   curl -sSL https://raw.githubusercontent.com/google/skills/main/index.json -o skills-index.json
   ```
2. **Strict Validation & TLS Security Rules**:
   - Verify `skills-index.json` parses as valid JSON with a top-level `"skills"` array where each item has `"name"`, `"description"`, and `"entrypoint"`.
   - **NEVER** retry failed downloads by disabling TLS certificate verification (`curl -k` or `--insecure`). If TLS validation fails, stop and report the network/certificate error to the user.
   - If `index.json` is unavailable, fall back to the GitHub Trees API: `https://api.github.com/repos/google/skills/git/trees/main?recursive=1`.
3. **Load Matched Skill Entrypoint**:
   ```bash
   curl -sSL "https://raw.githubusercontent.com/google/skills/main/<ENTRYPOINT>"
   ```
4. **Cleanup**: Delete temporary `skills-index.json` when finished.

### B. `gcloud` Leaf-Command Help Verification Protocol (`google/skills/skills/cloud/gcloud`)
Before proposing or running any `gcloud` CLI command (especially `gcloud compute instances create`, `gcloud beta batch jobs submit`, `gcloud filestore`, or `gcloud run deploy`):
- **Always** verify the leaf command's exact positional vs. flag syntax first:
  ```bash
  gcloud help <command_path>
  # Example:
  gcloud help compute instances create
  gcloud help run deploy
  ```
- Never guess flag names or assume a resource identifier is a flag (`--instance`) vs. a positional argument.

### C. `uv` Runtime Prerequisite (`google-deepmind/science-skills/skills/uv`)
All Python scripts in `google-deepmind/science-skills` declare inline PEP 723 dependencies or package requirements and **must** be executed via `uv run`:
1. Check availability:
   ```bash
   uv --version || "$HOME/.local/bin/uv" --version
   ```
2. If missing, install `uv`:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Run science skill scripts exclusively via:
   ```bash
   uv run scripts/<script_name>.py [args...] --output <results.json>
   ```

### D. Safe Credentials Protocol (`google-deepmind/science-skills/skills/credentials`)
Several DeepMind Science Skills require API keys or user identification in `~/.env` (e.g., `ALPHAGENOME_API_KEY` for `alphagenome_single_variant_analysis`, `OPENALEX_API_KEY` for `literature_search_openalex`, `USER_EMAIL` for NCBI/EBI rate-limit compliance).
- **STRICT PROHIBITION**: **NEVER** read or print `~/.env` (`cat ~/.env`, `head ~/.env`, `echo $ALPHAGENOME_API_KEY`, `env`, `printenv`). Exposing secret values in terminal output or LLM context is a security violation.
- **Verify Key Presence Silently**:
  ```bash
  grep -sq "^ALPHAGENOME_API_KEY=" ~/.env && echo "Configured" || echo "Missing"
  ```
- **Prompt with Hidden Input if Missing**:
  ```bash
  printf "Enter ALPHAGENOME_API_KEY (typing hidden): " && read -s val && echo && \
    [ -n "$(tail -c1 ~/.env 2>/dev/null)" ] && echo >> ~/.env; \
    echo "ALPHAGENOME_API_KEY=$val" >> ~/.env && echo "Saved."
  ```
- Or use `google_skills_router.py --check-env ALPHAGENOME_API_KEY,OPENALEX_API_KEY`.

### E. Third-Party Data License Notification (`SKILL_LICENSES.md`)
Before invoking a third-party scientific database skill (`alphafold_database_fetch_and_analyze`, `chembl_database`, `pubchem_database`, `uniprot_database`, `clinvar_database`, `gnomad_database`, etc.) for the first time in a workspace:
1. Check whether `.licenses/<skill_name>_LICENSE.txt` exists in the workspace root.
2. If not, notify the user of the database's terms of use (e.g., CC-BY-4.0 for AlphaFold DB / UniProt / ChEMBL; non-commercial/research terms in `SKILL_LICENSES.md`) and record the notification receipt via `check_science_prerequisites(..., write_license_receipt=True)`.

--------------------------------------------------------------------------------

## 3. End-to-End Multi-Skill Chaining Workflows

### Workflow 1: Pre-MD / Pre-AF3 Structural Triage & Domain Cropping (`hpc-workload-molecular-dynamics`)
Before launching an expensive multi-GPU AlphaFold 3 Slurm job (`examples/af3_inference_sbatch.sh`) or solvating a raw structure in GROMACS (`scripts/gromacs_tuner.py`):

1. **Fetch Canonical Sequence & Active Sites (`uniprot_database`)**:
   ```bash
   uv run scripts/uniprot_tools.py get P00698 --format json > P00698_uniprot.json
   ```
2. **Check Experimental & Predicted Structures (`pdb_database` & `alphafold_database_fetch_and_analyze`)**:
   ```bash
   # Check RCSB PDB for experimental holo/apo structures
   uv run scripts/search_pdb.py --query "P00698" --return_type entry --output pdb_hits.json

   # Fetch AlphaFold DB structure, pLDDT confidence, and PAE matrix
   uv run scripts/fetch_structure.py P00698 --output-dir ./afdb_P00698
   uv run scripts/analyze_plddt.py ./afdb_P00698/AF-P00698-F1-metadata.json
   uv run scripts/analyze_pae.py ./afdb_P00698/AF-P00698-F1-predicted_aligned_error_v4.json
   ```
3. **Run the AFDB -> GROMACS Gatekeeper Bridge (`science_skills_bridge.py afdb-gatekeeper`)**:
   ```bash
   python3 hpc-workload-molecular-dynamics/scripts/science_skills_bridge.py afdb-gatekeeper \
     --uniprot-id P00698 \
     --metadata-json ./afdb_P00698/AF-P00698-F1-metadata.json \
     --pae-json ./afdb_P00698/AF-P00698-F1-predicted_aligned_error_v4.json \
     --gpus 8 --gpu-type H100 --cpu-cores 88 --nodes 1
   ```
   - **Why This Matters**: If `fractionPlddtVeryLow` (`pLDDT < 50`) exceeds 30%, extended unstructured N/C-terminal tails dramatically increase the maximum molecular diameter $D$, inflating the cubic explicit-solvent water box volume $V \propto (D + 2d)^3$ by 40–70%. `afdb-gatekeeper` flags this, computes the cropped rigid core domain boundaries (`resid <start>-<end>`), recalculates the reduced atom count, and invokes `tune_gromacs()`.
4. **Static QC Render (`pymol`) + Dynamic Trajectory Animation (`visualizer.py` VMD)**:
   - Use `pymol` (headless CPU OSMesa) for static pLDDT B-factor quality-control renders and structural superpositions (`cmd.align`).
   - Use `scripts/visualizer.py` + `scripts/compile_vmd_gif.sh` (VMD v1.9.3 on `Xvfb :1` with ThinLinc/noVNC) for time-resolved `.xtc`/`.dcd` trajectory playback and 30× compressed differential-palette GIF animations.

### Workflow 2: Target-to-Lead High-Throughput Virtual Screening (`chembl_database` + `pubchem_database` -> HTVS)
1. **Assess Target Druggability (`opentargets_database`)**:
   ```bash
   uv run scripts/query_opentargets.py --output target_tractability.json get-target-druggability ENSG00000146648
   ```
2. **Fetch Known Bioactive Scaffolds & Analogs (`chembl_database` & `pubchem_database`)**:
   ```bash
   # Retrieve target bioactivities normalized to nanomolar (nM)
   uv run scripts/chembl_api.py activity --filter target_chembl_id=CHEMBL203 standard_type=IC50 --normalize --limit 1000 --output egfr_ic50.json

   # Search molecules by name or download 3D/2D SDF structure
   uv run scripts/chembl_api.py molecule --search "erlotinib" --limit 20 --output erlotinib_search.json
   uv run scripts/chembl_api.py molecule --id CHEMBL553 --dl_format sdf --output erlotinib.sdf
   ```
3. **Convert, Filter & Shard for Distributed Slurm Docking (`science_skills_bridge.py` + `split_docking_library.py`)**:
   ```bash
   # Filter by Lipinski Ro5 and normalized IC50 <= 10,000 nM, and emit .smi library
   python3 hpc-workload-molecular-dynamics/scripts/science_skills_bridge.py chembl-htvs-bridge \
     --chembl-json egfr_ic50.json \
     --output-smi egfr_candidates.smi \
     --max-activity-nm 10000

   # Shard into chunks for Slurm job array execution
   python3 hpc-workload-molecular-dynamics/scripts/split_docking_library.py \
     --input egfr_candidates.smi --chunk-size 5000 --output-dir ./docking_chunks
   ```
4. **Rank Docking Poses & Enrich Top Leads with Clinical/Bioactivity Data**:
   ```bash
   python3 hpc-workload-molecular-dynamics/scripts/rank_docking_results.py \
     --results-dir ./results --top-n 50 --output top_leads.csv --json-output top_leads.json

   python3 hpc-workload-molecular-dynamics/scripts/science_skills_bridge.py chembl-htvs-bridge \
     --chembl-json egfr_ic50.json \
     --docking-hits-json top_leads.json \
     --enriched-output top_leads_enriched.json
   ```
   Follow up on top leads with `clinical_trials_database` and `openfda_database` for repurposing and safety profiling.

### Workflow 3: Nextflow on Google Cloud Batch -> AlphaGenome & Clinical Variant Interpretation
1. **Optimize & Audit Nextflow Pipeline for Cloud Batch (`nextflow_batch_optimizer.py`)**:
   ```bash
   python3 hpc-workload-molecular-dynamics/scripts/nextflow_batch_optimizer.py \
     --main-nf main.nf --project-id MY_PROJECT --region us-central1 \
     --workdir gs://my-bucket/nf-work --samples 100 --output nextflow.config
   ```
2. **Generate Downstream Variant Interpretation Plan (`science_skills_bridge.py nextflow-variant-bridge`)**:
   ```bash
   python3 hpc-workload-molecular-dynamics/scripts/science_skills_bridge.py nextflow-variant-bridge \
     --variants "chr7:140753336:A>T,chr17:43044295:G>A" \
     --tissue-ontology "UBERON:0002107" \
     --gene "BRAF"
   ```
   - Triages candidate variants with `alphagenome_variant_impact_score` (`alphagenome_atlas_avi.py`), runs multi-modal regulatory/splicing predictions with `alphagenome_single_variant_analysis` (`visualize_variant_effects.py`), and annotates clinical significance (`clinvar_database`) and population allele frequency (`gnomad_database`).

### Workflow 4: Infrastructure, Storage, GKE & Remote Visualization (`gcp-hpc-cluster-toolkit`, `hpc-workload-cae`, `hpc-workload-energy`)
| Task Scenario | External Skill(s) to Load | Integration with Local HPC Tools |
| :--- | :--- | :--- |
| **Select & Rank Optimal GCE Machine Types & Hyperdisk Layout (`gce-instance-selector`)** | `gce-instance-selector` | Query `resources/instances.json` via `blueprint_generator.py --select-instances` to rank Gen 4 -> Gen 3 -> Gen 2 instances, display the mandatory `_metadata.createdAt` & `us-central1` pricing notice, select `hyperdisk-balanced` (Gen 3+) vs `pd-balanced` (Gen 1/2) boot disks, and compute multi-volume Hyperdisk scaling. |
| **Mitigate Stockouts Across Bulk Insert, MIGs & Cloud Batch (`gce-flexibility`)** | `gce-flexibility` | Chain after `gce-instance-selector` using `blueprint_generator.py --emit-flexibility-target {bulk-insert,mig,batch-job}` to build named `instanceSelections` (`gen4-preferred` rank 0, `gen3-fallback` rank 1) with bare machine type names. |
| **Stage 3.5TB AlphaFold DBs, Seismic Gathers, or OpenFOAM Archives on GCS** | `google-cloud-storage-bucket-architect`, `google-cloud-storage-fuse`, `google-cloud-storage-basics` | Configure HNS bucket + `gcsfuse` `file-cache` on Local SSD RAID-0 (`/scratch`) in `blueprint_generator.py` startup scripts. |
| **Prevent `/home` or `/apps` NFS Capacity Exhaustion or `drain*` Mount Failures** | `google-cloud-filestore-autoscale`, `google-cloud-filestore-log-troubleshooting`, `google-cloud-filestore-nfs-browser` | Pair with `cluster_diagnostics.sh` to auto-scale Filestore High Scale/Enterprise shares and debug `EACCES` mount errors. |
| **Run Containerized MPI / Batch Workloads on GKE Instead of Slurm** | `gke-batch-hpc`, `gke-compute-classes`, `gke-storage`, `gke-ai-troubleshooting-jobset-interruption` | Translate `blueprint_generator.py --emit-batch-policy` generational rankings into GKE Custom Compute Classes and `JobSet` + `Kueue` manifests with compact placement. |
| **Expose Zero-External-IP ParaView, VMD, or ResInsight Workstations Permanently** | `cloud-run-basics`, `gcloud`, `iam-helper-for-policy-management` | Deploy Cloud Run Direct VPC Egress (`--vpc-egress=all-traffic --session-affinity`) pointing to internal VM port 80/6080 (`paraview_remote_viz_setup.sh`, `vmd_thinlinc_viz_startup.sh`, `resinsight_thinlinc_viz_startup.sh`). |
| **Fetch Benchmark Validation Literature for CFD/FEA (`cae`) or Seismic/Reservoir (`energy`)** | `literature_search_arxiv`, `literature_search_openalex` | Query experimental Reynolds/Mach numbers, NACA/motorBike drag coefficients, or Marmousi/SPE relative permeability curves before running `decompose_helper.py`, `seismic_engine.py`, or `reservoir_engine.py`. |
| **Distill Multi-Step Simulation Campaign into a New Skill** | `workflow_skill_creator` | Package repeatable simulation + visualization pipelines into new modular skills with `SKILL.md` and `scripts/`. |
