# Computer-Aided Engineering (CAE), CFD & ParaView Visualization Skill

Domain expert tooling, ParaView 3D remote visualization pipelines, and optimization recipes for CFD and FEA workloads on Google Cloud.

## Modules & Scripts
- `scripts/decompose_helper.py`: Calculates optimal 3D sub-domain decomposition for OpenFOAM across modern CPU shapes.
- `scripts/decompose_helper_test.py`: Unit tests for domain decomposition factorizer.
- `scripts/residual_parser.py`: Multi-solver residual monitor for OpenFOAM and ANSYS Fluent.
- `scripts/residual_parser_test.py`: Unit tests for residual parsing and convergence tracking.
- `scripts/paraview_cae_visualizer.py`: Generates pre-baked binary `.vtp`/`.vti` VTK asset exporters, 4 switchable animated ParaView CFD visualizations (`1_3D_StreamTubes`, `2_Velocity_Slice`, `3_Wake_Turbulence`, `4_Quad_Dashboard`), speed-control macros (`5_Play_Animation`, `6_Turbo_Speed`), and `ParaView5.10.0.ini` configuration.
- `scripts/paraview_cae_visualizer_test.py`: Unit tests verifying binary VTK export (`DataMode="Binary"`), `CellDatatoPointData` decimation, `TimeTrack` disabling, and `PythonAnimationCue` generation.
- `scripts/license_check.sh`: Network probe for FlexLM/RLM licensing servers.

## Supported Solvers, Post-Processing & Workloads
- **ParaView 3D CFD Visualization & Fast Animation**: Cloud desktop setup (`examples/paraview_remote_viz_setup.sh`) with `Xvfb` + `XFCE4` + `x11vnc` + `noVNC` and pre-baked binary VTK caches achieving **17+ FPS (~20x–60x loop speedup)** on CPU-only software OpenGL nodes (`references/paraview_remote_visualization_guide.md`).
- **Siemens STAR-CCM+**: Multi-node CFD simulation (`examples/star_ccm_sbatch.sh`) with Intel MPI Libfabric tuning, automated hostfile creation, and CD-adapco / SALT license configuration.
- **OpenFOAM**: Motorbike benchmark (`examples/openfoam_motorbike_sbatch.sh`) with automated `motorBike.obj.gz` extraction, `snappyHexMesh`, `potentialFoam`, `simpleFoam`, `reconstructPar`, and `foamToVTK -latestTime`.
- **ANSYS Fluent**: Multi-node execution (`examples/ansys_fluent_sbatch.sh`) with `-cnf` host expansion and Intel MPI fabric configuration.
- **SIMULIA Abaqus**: Standard & Explicit sparse matrix solver (`examples/abaqus_sbatch.sh`) with Hyperdisk Balanced scratch.
- **LS-DYNA**: MPP explicit crash simulations (`examples/ls_dyna_mpp_sbatch.sh`) with hybrid MPI + OpenMP core binding.
