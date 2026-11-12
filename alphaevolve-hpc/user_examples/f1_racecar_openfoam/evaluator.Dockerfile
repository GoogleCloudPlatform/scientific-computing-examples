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
FROM ubuntu:24.04

USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Copy uv package manager for fast Python 3.12 + dependency installation
COPY --from=ghcr.io/astral-sh/uv@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /uvx /bin/

# Install OpenFOAM 14 (openfoam.org) and essential system utilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        gnupg \
        wget \
        git \
        make && \
    wget -q -O - https://dl.openfoam.org/gpg.key > /etc/apt/trusted.gpg.d/openfoam.asc && \
    echo "deb [arch=amd64] http://dl.openfoam.org/ubuntu noble main dev" > /etc/apt/sources.list.d/openfoam.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends openfoam14 && \
    rm -rf /var/lib/apt/lists/*

# Create Python 3.12 virtual environment
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python
ENV VIRTUAL_ENV=/opt/venv
RUN uv python install 3.12 && uv venv --python 3.12 $VIRTUAL_ENV
ENV WM_PROJECT=OpenFOAM
ENV WM_PROJECT_VERSION=14
ENV WM_PROJECT_DIR=/opt/openfoam14
ENV WM_THIRD_PARTY_DIR=/opt/openfoam14/thirdparty
ENV FOAM_ETC=/opt/openfoam14/etc
ENV FOAM_SIGFPE=false
ENV PATH="$VIRTUAL_ENV/bin:/opt/openfoam14/platforms/linux64GccDPInt32Opt/bin:/opt/openfoam14/bin:$PATH"
ENV LD_LIBRARY_PATH="/opt/openfoam14/platforms/linux64GccDPInt32Opt/lib/openmpi-system:/opt/openfoam14/thirdparty/platforms/linux64GccDPInt32/lib/openmpi-system:/opt/openfoam14/platforms/linux64GccDPInt32Opt/lib:/opt/openfoam14/thirdparty/platforms/linux64GccDPInt32/lib:/opt/openfoam14/platforms/linux64GccDPInt32Opt/lib/dummy"

WORKDIR /app

# Install core AlphaEvolve framework dependencies
COPY infrastructure/requirements.txt .
RUN uv pip install --require-hashes -r requirements.txt

# Copy core framework library
COPY google_framework/alpha_evolve /app/src/alpha_evolve
ENV PYTHONPATH="/app/src:/app/src/alpha_evolve:${PYTHONPATH:-}"

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

# Copy experiment files
COPY user_examples/f1_racecar_openfoam/ /app/experiment/

# Configure non-root evaluser with UID 1000 for GCS FUSE mount compatibility
RUN (userdel -r ubuntu 2>/dev/null || true) && \
    useradd -m -u 1000 evaluser && \
    chmod -R a+rx /opt/uv /opt/venv /app/src /opt/openfoam14 && \
    chown -R evaluser:evaluser /app/experiment

WORKDIR /app/src/alpha_evolve
USER evaluser

# Supports unified alpha_evolve.runner (CitC) and standalone cloud_evaluator.py (GitHub)
ENTRYPOINT ["/bin/bash", "-c", "\
    if [ -f /app/src/alpha_evolve/runner.py ]; then \
      exec python -m alpha_evolve.runner \"$@\"; \
    else \
      echo \"[BATCH DEBUG] Container started for Program ID: $_CANDIDATE_PROGRAM_ID\" && \
      mkdir -p \"${_MOUNT_PATH:-/tmp}/${_USER_EXPERIMENT_NAME:-f1-racecar-openfoam}/logs\" && \
      if [ -n \"${_CANDIDATE_DIR:-}\" ] && [ -d \"$_CANDIDATE_DIR\" ]; then \
        cp -r \"$_CANDIDATE_DIR\"/* /app/experiment/ 2>/dev/null || true; \
      fi && \
      make -C /app/experiment all && \
      exec bash /app/experiment/evaluator.sh; \
    fi", "--"]
