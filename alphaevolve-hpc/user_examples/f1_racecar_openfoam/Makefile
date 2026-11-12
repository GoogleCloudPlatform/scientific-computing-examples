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

all: evaluator.sh

evaluator.sh:
	echo "#!/bin/bash" > evaluator.sh
	echo "set -euo pipefail" >> evaluator.sh
	echo "if [ -f /opt/openfoam14/etc/bashrc ]; then set +u; source /opt/openfoam14/etc/bashrc || true; set -u; fi" >> evaluator.sh
	echo "cd /app/experiment" >> evaluator.sh
	echo 'LOG_DIR="$${_MOUNT_PATH:-/tmp}/$${_USER_EXPERIMENT_NAME:-f1-racecar-openfoam}/logs"' >> evaluator.sh
	echo 'mkdir -p "$$LOG_DIR"' >> evaluator.sh
	echo 'PY_BIN=$$(command -v python || command -v python3)' >> evaluator.sh
	echo 'export PYTHONPATH="/app/src:/app/src/alpha_evolve:$${PYTHONPATH:-}"' >> evaluator.sh
	echo 'if [ -f /app/src/alpha_evolve/runner.py ]; then "$$PY_BIN" -m alpha_evolve.runner 2>&1 | tee "$$LOG_DIR/evaluator_$${_CANDIDATE_PROGRAM_ID:-local}.log"; else "$$PY_BIN" /app/src/alpha_evolve/cloud_evaluator.py 2>&1 | tee "$$LOG_DIR/evaluator_$${_CANDIDATE_PROGRAM_ID:-local}.log"; fi' >> evaluator.sh
	chmod +x evaluator.sh

clean:
	rm -f evaluator.sh

.PHONY: all clean evaluator.sh
