#!/bin/bash
# ==============================================================================
# OPM Flow 3D Reservoir Simulation Runner: Ninth SPE Comparative Solution Project
# Solves 3-phase black-oil flow across a 9,000-cell 15-layer dipping reservoir
# ==============================================================================
set -e

SIM_DIR="${1:-/apps/energy/simulations/spe9}"
DECK_PATH="${2:-/apps/energy/opm-tests/spe9/SPE9.DATA}"
OUTPUT_DIR="${SIM_DIR}/output"

mkdir -p "${OUTPUT_DIR}"
cd "${SIM_DIR}"

echo "================================================================================"
echo "⚡ RUNNING FULL 3D OPM FLOW SIMULATION: $(basename "${DECK_PATH}")"
echo "================================================================================"

# Execute OPM Flow with native VTK generation enabled
flow "${DECK_PATH}" \
    --enable-vtk-output=true \
    --output-dir="${OUTPUT_DIR}" \
    2>&1 | tee "${SIM_DIR}/flow_execution.log"

echo "[+] Simulation Completed Successfully!"
echo "[+] Summary metrics:"
tail -n 35 "${OUTPUT_DIR}/SPE9.PRT"

echo "[+] Generated 3D VTK output for ParaView:"
ls -lh "${OUTPUT_DIR}"/SPE9*.vtu | head -n 5
echo "... [total $(ls "${OUTPUT_DIR}"/SPE9*.vtu | wc -l) 3D timesteps generated]"
echo "[+] ParaView collection index: ${OUTPUT_DIR}/SPE9.pvd"
