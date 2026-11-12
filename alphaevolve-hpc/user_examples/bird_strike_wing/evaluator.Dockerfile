ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    make \
    git \
    && rm -rf /var/lib/apt/lists/*

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

# Copy and install core AlphaEvolve dependencies with security hashes enabled
COPY infrastructure/requirements.txt .
RUN python3 -m pip install --no-cache-dir --require-hashes -r requirements.txt --break-system-packages

# Copy shared AlphaEvolve framework source code
COPY google_framework/alpha_evolve /app/src/alpha_evolve

# Copy experiment files
COPY user_examples/bird_strike_wing/ /app/experiment/

# Install experiment-specific Python requirements (without --require-hashes)
RUN if [ -f /app/experiment/requirements.txt ]; then \
      python3 -m pip install --no-cache-dir -r /app/experiment/requirements.txt --break-system-packages; \
    fi

# Execute setup.sh at build time to install OpenRADIOSS and Linux runtime libraries
RUN if [ -f /app/experiment/setup.sh ]; then \
      chmod +x /app/experiment/setup.sh && \
      /app/experiment/setup.sh; \
    fi

ENV OPENRADIOSS_PATH="/opt/OpenRadioss"
ENV RAD_CFG_PATH="/opt/OpenRadioss/hm_cfg_files"
ENV LD_LIBRARY_PATH="/opt/OpenRadioss/extlib/hm_reader/linux64:/opt/OpenRadioss/extlib/h3d/lib/linux64"
ENV OMP_STACKSIZE="400m"

WORKDIR /app/src/alpha_evolve

RUN useradd -m -u 1000 evaluser
RUN chown -R evaluser:evaluser /app/experiment
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
