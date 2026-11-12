#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

OF14_DIR="${OPENFOAM14_ROOT:-/opt/openfoam14}"
if [ -f "${OF14_DIR}/etc/bashrc" ]; then
  set +u
  # shellcheck disable=SC1090,SC1091
  source "${OF14_DIR}/etc/bashrc" || true
  set -u
fi

if command -v foamRun >/dev/null 2>&1; then
  echo "Detected OpenFOAM Foundation solver: $(command -v foamRun)"
elif [ -x "${OF14_DIR}/platforms/linux64GccDPInt32Opt/bin/foamRun" ]; then
  echo "Detected OpenFOAM-14 installation at ${OF14_DIR}"
elif command -v simpleFoam >/dev/null 2>&1; then
  echo "Detected OpenFOAM solver: $(command -v simpleFoam)"
elif [ -n "${OPENFOAM_BIN_DIR:-}" ] && [ -x "${OPENFOAM_BIN_DIR}/simpleFoam" ]; then
  echo "Detected OpenFOAM solver at ${OPENFOAM_BIN_DIR}/simpleFoam"
else
  echo "Note: OpenFOAM binary not found on PATH; evaluator will use OpenFOAM-calibrated 3D RANS surrogate until OpenFOAM is installed."
fi
