#!/usr/bin/env bash
#SBATCH --job-name=openfoam-motorbike
#SBATCH --partition=h3-cae
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=88
#SBATCH --cpus-per-task=1
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%j.out

set -e

echo "=== Starting OpenFOAM Motorbike Benchmark ==="
echo "Nodes allocated: $SLURM_JOB_NUM_NODES"
echo "Total MPI ranks: $SLURM_NTASKS"

# 1. Load Environment / Spack / System OpenFOAM
source /apps/spack/share/spack/setup-env.sh 2>/dev/null || true
spack load openfoam@2312 2>/dev/null || module load openfoam 2>/dev/null || source /usr/lib/openfoam/openfoam1912/etc/bashrc 2>/dev/null || true

# 2. Setup Case Directory on Shared /scratch Storage
WORK_DIR="/scratch/${USER:-openfoam}/motorBike"
mkdir -p "$WORK_DIR"
cp -r "$FOAM_TUTORIALS"/incompressible/simpleFoam/motorBike/* "$WORK_DIR/"
cd "$WORK_DIR"

# Extract motorBike geometry STL/OBJ into constant/triSurface
mkdir -p constant/triSurface
if [[ -f "$FOAM_TUTORIALS/resources/geometry/motorBike.obj.gz" ]]; then
  gzip -dc "$FOAM_TUTORIALS/resources/geometry/motorBike.obj.gz" > constant/triSurface/motorBike.obj
fi

# 3. Modify Domain Decomposition for allocated MPI ranks
sed -i "s/numberOfSubdomains [0-9]*;/numberOfSubdomains ${SLURM_NTASKS};/g" system/decomposeParDict
sed -i "s/method .*/method scotch;/g" system/decomposeParDict

# 4. Generate Background & SnappyHexMesh
echo "Generating mesh with blockMesh and snappyHexMesh..."
blockMesh > log.blockMesh 2>&1
if command -v surfaceFeatures >/dev/null 2>&1; then
  surfaceFeatures > log.surfaceFeatures 2>&1
else
  surfaceFeatureExtract > log.surfaceFeatures 2>&1
fi
decomposePar -copyZero > log.decomposePar 2>&1

srun --mpi=pmix -n "$SLURM_NTASKS" snappyHexMesh -parallel -overwrite > log.snappyHexMesh 2>&1

# 5. Initialize Potential Flow & Run Steady-State Turbulent Solver (simpleFoam)
echo "Initializing flow with potentialFoam and executing simpleFoam in parallel..."
srun --mpi=pmix -n "$SLURM_NTASKS" potentialFoam -parallel > log.potentialFoam 2>&1 || true
srun --mpi=pmix -n "$SLURM_NTASKS" --cpu-bind=core simpleFoam -parallel > log.simpleFoam 2>&1

# 6. Reconstruct Mesh, Solution & Export VTK + ParaView .foam Marker
echo "Reconstructing mesh, solution, and VTK post-processing caches..."
reconstructParMesh -constant > log.reconstructParMesh 2>&1
reconstructPar -latestTime > log.reconstructPar 2>&1
foamToVTK -latestTime > log.foamToVTK 2>&1
touch motorBike.foam

echo "=== OpenFOAM Benchmark & VTK Post-Processing Export Complete ==="
