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

ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=1

# Install build tools, OpenMPI, and OpenSSH services for MPI execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    g++ \
    make \
    openmpi-bin \
    libopenmpi-dev \
    openssh-server \
    openssh-client \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create evaluser and configure passwordless SSH for non-root execution
RUN useradd -m -u 1000 evaluser \
    && mkdir -p /var/run/sshd /home/evaluser/.ssh /root/.ssh \
    && ssh-keygen -t rsa -f /home/evaluser/.ssh/id_rsa -N "" \
    && cp /home/evaluser/.ssh/id_rsa.pub /home/evaluser/.ssh/authorized_keys \
    && cp /home/evaluser/.ssh/id_rsa.pub /root/.ssh/authorized_keys \
    && echo "Host *\n\tStrictHostKeyChecking no\n\tUserKnownHostsFile /dev/null" > /home/evaluser/.ssh/config \
    && chmod 700 /home/evaluser/.ssh \
    && chmod 600 /home/evaluser/.ssh/id_rsa /home/evaluser/.ssh/authorized_keys /home/evaluser/.ssh/config \
    && chown -R evaluser:evaluser /home/evaluser/.ssh

ARG CLOUD_BUCKET_NAME
ARG PROJECT_ID
ARG MOUNT_PATH="/mnt/disks/share"

ENV _CLOUD_BUCKET_NAME=${CLOUD_BUCKET_NAME}
ENV _PROJECT_ID=${PROJECT_ID}
ENV _JOB_ID=""
ENV _CANDIDATE_PROGRAM_ID=""
ENV _MOUNT_PATH=${MOUNT_PATH}
ENV _PROGRAMS_DIR=""
ENV _CLIENT_EVALUATOR_SCRIPT=""
ENV _CLIENT_EVALUATOR_METHOD=""
ENV _CANDIDATE_DIR=""

# Copy and install core platform requirements with secure hash verification
COPY infrastructure/requirements.txt /app/requirements.txt
RUN python3 -m pip install --break-system-packages --ignore-installed --no-cache-dir --require-hashes -r /app/requirements.txt

# Set workdir and copy AlphaEvolve base packages
WORKDIR /app/src/alpha_evolve
COPY google_framework/alpha_evolve /app/src/alpha_evolve
ENV PYTHONPATH="/app/src:${PYTHONPATH:-}"

# Copy the experiment code
COPY user_examples/fsi_var_monte_carlo/ /app/experiment/
RUN chmod +x /app/experiment/run-ssh.sh
RUN chown -R evaluser:evaluser /app/experiment
USER evaluser

ENTRYPOINT ["/bin/bash", "-c", "\
    echo \"[BATCH DEBUG] Container started for Program ID: $_CANDIDATE_PROGRAM_ID\" && \
    mkdir -p ${_MOUNT_PATH}/${_USER_EXPERIMENT_NAME}/logs 2>/dev/null || true; \
    if [ -f \"/app/experiment/Makefile\" ]; then \
      echo \"[BATCH DEBUG] Found Makefile under directory: /app/experiment\"; \
      echo \"[BATCH DEBUG] Copying generated C++ code from $_CANDIDATE_DIR to /app/experiment...\"; \
      cp -r $_CANDIDATE_DIR/* /app/experiment/ 2>/dev/null || true; \
      echo \"[BATCH DEBUG] Generating evaluation script...\" && \
      make -C /app/experiment evaluator.sh || exit 1; \
      echo \"[BATCH DEBUG] Build finished.\"; \
    else \
      echo \"[BATCH DEBUG] INFO: No Makefile found, skipping build.\"; \
      exit 0; \
    fi && \
    echo \"[BATCH DEBUG] Running evaluator...\" && \
    bash /app/experiment/evaluator.sh \
"]
