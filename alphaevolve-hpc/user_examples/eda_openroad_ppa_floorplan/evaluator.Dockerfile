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
FROM docker.io/openroad/orfs:26Q3-586-gfbc8fa48d

USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git make && \
    rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python
ENV VIRTUAL_ENV=/opt/venv
RUN if [ ! -d "$VIRTUAL_ENV" ]; then \
      uv python install 3.12 && uv venv --python 3.12 $VIRTUAL_ENV; \
    fi
ENV PATH="$VIRTUAL_ENV/bin:/OpenROAD-Flow-Scripts/tools/install/OpenROAD/bin:$PATH"
ENV ORFS_FLOW_DIR="/OpenROAD-Flow-Scripts/flow"

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

WORKDIR /app

# Copy and install core framework requirements
COPY infrastructure/requirements.txt .
RUN uv pip install --require-hashes -r requirements.txt

# Copy core framework library
COPY google_framework/alpha_evolve ./src/alpha_evolve
ENV PYTHONPATH="/app/src:${PYTHONPATH:-}"

# Copy experiment files
COPY user_examples/eda_openroad_ppa_floorplan/ /app/experiment/

RUN chmod -R a+rx /opt/uv /opt/venv /app/src && \
    (id -u 1000 >/dev/null 2>&1 || useradd -m -u 1000 evaluser) && \
    chown -R 1000:1000 /app/experiment

WORKDIR /app/src/alpha_evolve
USER 1000

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
