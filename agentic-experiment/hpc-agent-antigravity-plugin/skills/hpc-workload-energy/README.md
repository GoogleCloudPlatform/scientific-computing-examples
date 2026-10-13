# Energy & Subsurface Geoscience HPC Solution Skill

Domain expert tooling, cluster blueprints, simulation solvers, and interactive 3D remote visualization recipes for Seismic Exploration and Reservoir Simulation on Google Cloud.

---

## 1. Modules & Scripts

* **`scripts/benchmark_fetcher.py`**: Ingests and generates standard Marmousi 2 structural velocity models and SPE 10 / Norne heterogeneous channel models.
* **`scripts/seismic_engine.py`**: 4th-order acoustic wave forward modeling engine with absorbing boundaries and receiver gather recording.
* **`scripts/seismic_engine_test.py`**: Unit tests for wavelet generation, boundary damping, and wavefield propagation.
* **`scripts/reservoir_engine.py`**: Multiphase Darcy flow simulator with sparse linear pressure solving and upwind saturation transport.
* **`scripts/reservoir_engine_test.py`**: Unit tests for relative permeability and reservoir simulation solver.
* **`scripts/visualizer.py`**: Scientific visualization generator producing publication-ready 3-panel PNG plots for wave propagation, shot gathers, permeability fields, and production curves.
* **`scripts/paraview_energy_pipeline.py`**: End-to-end Python pipeline that produces equal-scale Legacy VTK datasets ($4,000\,\text{m} \times 2,500\,\text{m}$) and builds an unoccluded, animated side-by-side ParaView 3D scene.

---

## 2. Examples & Slurm Recipes

* **`examples/energy_cluster_blueprint.yaml`**: Production-grade Slurm cluster blueprint generated via `blueprint_generator.py` targeting `h4d-standard-192` with compact placement, Tier 1 networking, and Hyperdisk Balanced scratch.
* **`examples/seismic_marmousi_sbatch.sh`**: Distributed Devito forward modeling & RTM job script.
* **`examples/reservoir_norne_sbatch.sh`**: Hybrid MPI + OpenMP OPM Flow reservoir simulation job script.
* **`examples/paraview_viz_startup.sh`**: GCE startup script that fully provisions an interactive 3D ParaView remote visualization VM with ThinLinc, noVNC, and Cloudflare tunnels.

---

## 3. Technical References

* **`references/seismic_modeling_guide.md`**: CFL stability conditions, spatial dispersion criteria, and absorbing boundary implementations.
* **`references/reservoir_simulation_guide.md`**: ECLIPSE / OPM Flow keyword structure, linear solver configurations, and well control formulas.
* **`references/paraview_energy_visualization_guide.md`**: Architectural reference for 3D depth layering, equal-scaling, Legacy VTK formatting, and remote streaming.

---

## 4. Benchmark Highlights

* **Seismic Wave Modeling (Marmousi 2):** $401 \times 201$ grid with 1,000 time steps executed under Slurm in $0.92\,\text{s}$ ($4.81 \times 10^7$ grid-points/sec).
* **Reservoir Waterflood (SPE 10 Layer):** $81 \times 51$ grid across 1,000 days executed under Slurm in $7.38\,\text{s}$ (average $0.74\,\text{s}$ per report interval).
* **Interactive 3D Dual-Domain Render:** Synchronized playback of acoustic wave propagation and waterflood displacement in ParaView at matched $4,000\,\text{m} \times 2,500\,\text{m}$ physical scales with unoccluded $Y = -40\,\text{m}$ foreground layers.
