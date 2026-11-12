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

USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

ARG OPENRADIOSS_VERSION=20230915
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    make \
    curl \
    wget \
    xz-utils \
    ca-certificates \
    libgomp1 \
    libquadmath0 \
    libgfortran5 && \
    mkdir -p /opt && \
    wget -q -O /tmp/OpenRadioss_linux64.tar.xz \
      "http://www.phoronix-test-suite.com/benchmark-files/OpenRadioss_linux64_${OPENRADIOSS_VERSION}.tar.xz" && \
    tar -xf /tmp/OpenRadioss_linux64.tar.xz -C /opt && \
    rm -f /tmp/OpenRadioss_linux64.tar.xz && \
    ln -sf "/opt/OpenRadioss_linux64_${OPENRADIOSS_VERSION}/OpenRadioss" /opt/OpenRadioss && \
    rm -rf /var/lib/apt/lists/*

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

ENV OPENRADIOSS_PATH="/opt/OpenRadioss"
ENV RAD_CFG_PATH="/opt/OpenRadioss/hm_cfg_files"
ENV LD_LIBRARY_PATH="/opt/OpenRadioss/extlib/hm_reader/linux64:/opt/OpenRadioss/extlib/h3d/lib/linux64"
ENV OMP_STACKSIZE="400m"

WORKDIR /app

# Copy and install core AlphaEvolve dependencies with security hashes enabled
COPY infrastructure/requirements.txt .
RUN python3 -m pip install --no-cache-dir --require-hashes -r requirements.txt --break-system-packages

# Copy shared AlphaEvolve framework source code
COPY google_framework/alpha_evolve /app/src/alpha_evolve
ENV PYTHONPATH="/app/src:${PYTHONPATH:-}"

# Copy experiment files
COPY user_examples/coronary_stent_openradioss/ /app/experiment/

# Execute setup.sh at build time if present
RUN if [ -f /app/experiment/setup.sh ]; then \
      chmod +x /app/experiment/setup.sh && \
      /app/experiment/setup.sh; \
    fi

WORKDIR /app/src/alpha_evolve

RUN useradd -m -u 1000 evaluser && \
    chown -R evaluser:evaluser /app/experiment
USER evaluser

ENTRYPOINT ["/bin/bash", "-c", "\
    echo \"[BATCH DEBUG] Container started for Program ID: $_CANDIDATE_PROGRAM_ID\" && \
    mkdir -p $_MOUNT_PATH/logs && \
    if [ -f \"/app/experiment/Makefile\" ]; then \
      echo \"[BATCH DEBUG] Found Makefile under directory: /app/experiment\"; \
      echo \"[BATCH DEBUG] Copying generated code from $_CANDIDATE_DIR to /app/experiment...\" && \
      cp -r $_CANDIDATE_DIR/* /app/experiment/ 2>/dev/null || true && \
      echo \"[BATCH DEBUG] Generating evaluator.sh via Makefile...\" && \
      make -C /app/experiment all || exit 1; \
      echo \"[BATCH DEBUG] Build finished.\"; \
    else \
      echo \"[BATCH DEBUG] ERROR: No Makefile found, exiting.\"; \
      exit 1; \
    fi && \
    echo \"[BATCH DEBUG] Running evaluator...\" && \
    bash /app/experiment/evaluator.sh \
"]
