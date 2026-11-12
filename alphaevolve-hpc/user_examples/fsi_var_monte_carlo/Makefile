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

CXX := $(shell command -v mpicxx >/dev/null 2>&1 && echo mpicxx || echo g++)
MPI_FLAGS := $(shell command -v mpicxx >/dev/null 2>&1 && echo -DUSE_MPI || echo "")
CXXFLAGS = -O3 -mavx2 -mfma -fopenmp -std=c++17 $(MPI_FLAGS)
TARGET := /var/tmp/var_mc_sim

.PHONY: all clean evaluator.sh

all: $(TARGET) evaluator.sh

$(TARGET): main.cpp
	$(CXX) $(CXXFLAGS) main.cpp -o $(TARGET)

evaluator.sh:
	echo "#!/bin/bash" > evaluator.sh
	echo "cd /app/experiment" >> evaluator.sh
	echo "mkdir -p \$$_MOUNT_PATH/\$$_USER_EXPERIMENT_NAME/logs" >> evaluator.sh
	echo 'python3 /app/src/alpha_evolve/cloud_evaluator.py 2>&1 | tee $$_MOUNT_PATH/$$_USER_EXPERIMENT_NAME/logs/evaluator_$$_CANDIDATE_PROGRAM_ID.log' >> evaluator.sh
	chmod +x evaluator.sh

clean:
	rm -f $(TARGET) var_mc_sim evaluator.sh
