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
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# Install core AlphaEvolve framework dependencies
COPY infrastructure/requirements.txt .
RUN uv pip install --require-hashes -r requirements.txt

# Copy core framework library
COPY google_framework/alpha_evolve ./src/alpha_evolve
ENV PYTHONPATH="/app/src:${PYTHONPATH}"

ARG CLOUD_BUCKET_NAME
ARG PROJECT_ID
ARG MOUNT_PATH="/mnt/disks/share"

# Environment variables required by the AlphaEvolve Batch Harness
ENV _CLOUD_BUCKET_NAME=${CLOUD_BUCKET_NAME}
ENV _PROJECT_ID=${PROJECT_ID}
ENV _JOB_ID=""
ENV _CANDIDATE_PROGRAM_ID=""
ENV _MOUNT_PATH=${MOUNT_PATH}
ENV _PROGRAMS_DIR=""
ENV _CLIENT_EVALUATOR_SCRIPT=""
ENV _CLIENT_EVALUATOR_METHOD=""
ENV _CANDIDATE_DIR=""

# Configure non-root evaluser with UID 1000 for GCS FUSE mount compatibility
RUN (userdel -r ubuntu 2>/dev/null || true) && \
    useradd -m -u 1000 evaluser && \
    chmod -R a+rx /opt/uv /opt/venv /app/src /opt/openfoam14

# Copy the experiment code
COPY --chown=1000:1000 user_examples/rocket_nozzle_openfoam/ /app/experiment/

WORKDIR /app/src/alpha_evolve
USER evaluser

# Universal platform runner entrypoint
ENTRYPOINT ["python", "-m", "alpha_evolve.runner"]
