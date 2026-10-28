ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}
COPY --from=ghcr.io/astral-sh/uv@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /uvx /bin/

# Set environment variables to avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install build tools and base utilities
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    make \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

ARG CLOUD_BUCKET_NAME
ARG PROJECT_ID
ARG MOUNT_PATH="/mnt/disks/share"

# Environment variables
ENV _CLOUD_BUCKET_NAME=${CLOUD_BUCKET_NAME} \
    _PROJECT_ID=${PROJECT_ID} \
    _JOB_ID="" \
    _CANDIDATE_PROGRAM_ID="" \
    _MOUNT_PATH=${MOUNT_PATH} \
    _PROGRAMS_DIR="" \
    _CLIENT_EVALUATOR_SCRIPT="" \
    _CLIENT_EVALUATOR_METHOD="" \
    _CANDIDATE_DIR="" \
    TPU_ACCELERATION_ENABLED=true

# Set the working directory
WORKDIR /app

# Copy the core infrastructure requirements file
COPY infrastructure/requirements.txt .
RUN uv pip install --system --require-hashes -r requirements.txt

# Copy and install custom experiment dependencies (JAX, libtpu, etc.)
COPY user_examples/tpu_gemm_cloud_batch/requirements.txt /app/experiment/requirements.txt
RUN uv pip install --system --require-hashes -r /app/experiment/requirements.txt

# Copy the shared framework source code
COPY google_framework/alpha_evolve /app/src/alpha_evolve
# Copy the experiment code
COPY user_examples/tpu_gemm_cloud_batch/ /app/experiment/

WORKDIR /app/src/alpha_evolve

RUN useradd -m -u 1000 evaluser
RUN chown -R evaluser:evaluser /app/experiment
USER evaluser

# Set the entrypoint using bash
ENTRYPOINT ["/bin/bash", "-c", "\
    echo \"[BATCH DEBUG] Container started for Program ID: $_CANDIDATE_PROGRAM_ID\" && \
    mkdir -p $_MOUNT_PATH/logs && \
    if [ -f \"/app/experiment/Makefile\" ]; then \
      echo \"[BATCH DEBUG] Found Makefile under directory: /app/experiment\"; \
      echo \"[BATCH DEBUG] Copying generated code from $_CANDIDATE_DIR to /app/experiment...\" && \
      cp -r $_CANDIDATE_DIR/* /app/experiment/ 2>/dev/null || true && \
      echo \"[BATCH DEBUG] Building Makefile targets from /app/experiment...\" && \
      make -C /app/experiment all || exit 1; \
      echo \"[BATCH DEBUG] Build finished.\"; \
    else \
      echo \"[BATCH DEBUG] INFO: No Makefile found, skipping build.\"; \
      exit 0; \
    fi && \
    echo \"[BATCH DEBUG] Running evaluator...\" && \
    bash /app/experiment/evaluator.sh \
"]
