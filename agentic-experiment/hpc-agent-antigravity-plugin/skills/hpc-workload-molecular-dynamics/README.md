# Molecular Dynamics, VMD Visualization & Nextflow Solution Skill

High-Performance Computing procedures, parameter calculators, Nextflow Google Cloud Batch workflow optimizers, VMD molecular visualizers, and Slurm recipes for Molecular Dynamics, Virtual Screening, and Protein Structure Prediction on Google Cloud.

## Modules & Scripts
- `scripts/visualizer.py`: Comprehensive VMD (Visual Molecular Dynamics) scene automation, headless trajectory frame export, two-pass FFmpeg differential palette GIF compiler, and publication-ready 4-panel MD stability plotter (Backbone RMSD, Radius of Gyration, Potential Energy, and RMSF).
- `scripts/compile_vmd_gif.sh`: High-performance FFmpeg two-pass palette extraction with differential statistics and Bayer scale 3 dithering for ultra-smooth molecular trajectory GIFs.
- `scripts/visualizer_test.py`: Unit tests covering Tcl scene generation, representation styling, XVG data parsing, and synthesis plots.
- `scripts/nextflow_batch_optimizer.py`: Nextflow + Google Cloud Batch workflow optimizer and QA validation gatekeeper. Parses case-sensitive processes, maps biological hardware tiers, queries the `gce-instance-selector` (`resources/instances.json`) catalog, emits `gce-flexibility` Cloud Batch `instanceFlexibilityPolicy` payloads (`--emit-flexibility-json`), calculates dynamic `--max_forks` concurrency to prevent quota exhaustion, and enforces zero-tolerance GCP disk support matrices.
- `scripts/nextflow_batch_optimizer_test.py`: Unit tests for process extraction, biological hardware tiering, `gce-instance-selector` + `gce-flexibility` batch policy generation, dynamic concurrency, and QA gatekeeper audits.
- `scripts/gromacs_tuner.py`: Calculates MPI ranks, OpenMP threads, and GPU offloading flags (with multi-node PME rank recommendation).
- `scripts/gromacs_tuner_test.py`: Assertion-backed unit tests for GROMACS tuning logic.
- `scripts/split_docking_library.py`: Multi-format compound library sharding (SDF, PDBQT, SMILES, CSV/TSV).
- `scripts/split_docking_library_test.py`: Unit tests for chemical library splitting.
- `scripts/rank_docking_results.py`: Distributed docking score aggregation and lead ranking across single and multi-molecule batch logs.
- `scripts/rank_docking_results_test.py`: Unit tests for docking score ranking.

## Supported Workloads & Accelerators
- **Interactive 3D Remote Visualization (VMD v1.9.3)**: Remote desktop workstation on Google Cloud (`c2-standard-16` / `c4-standard-16`) running `Xvfb :1` (1920x1080), XFCE4 desktop session with `xfwm4` window manager, x11vnc, noVNC, ThinLinc, and permanent Cloud Run direct VPC egress reverse proxy.
- **GROMACS Molecular Dynamics**: Multi-threaded CPU execution with AVX2 SIMD or multi-GPU resident and hybrid offload on B200, H200, H100, and L4 with dedicated PME rank scaling.
- **Nextflow on Google Cloud Batch**: Dynamic bioinformatic process hardware tiering (FastQC, BWA, STAR, GATK, Kraken2, Salmon, MultiQC) with zero-tolerance disk checks.
- **AlphaFold 3 / ColabFold**: GPU-accelerated structure prediction with local NVMe database cache staging and XLA memory pre-allocation.
- **LAMMPS**: Kokkos CUDA multi-node scaling with 1 rank per GPU.
- **AutoDock Vina**: Large-scale virtual screening campaigns using Slurm job arrays and multi-format chunking.
