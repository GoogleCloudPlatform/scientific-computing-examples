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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installing Python dependencies for drug_discovery_docking..."
if command -v uv >/dev/null 2>&1; then
  uv pip install --no-cache-dir -r "${SCRIPT_DIR}/requirements.txt"
else
  python3 -m pip install --no-cache-dir --break-system-packages -r "${SCRIPT_DIR}/requirements.txt" || \
    python3 -m pip install --no-cache-dir -r "${SCRIPT_DIR}/requirements.txt"
fi
python3 -c "import numpy, scipy; print('Verified numpy', numpy.__version__, 'and scipy', scipy.__version__)"
