# Use a lightweight base image
ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}
COPY --from=ghcr.io/astral-sh/uv@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /uvx /bin/

# Arguments for the experiment configuration
ARG CLOUD_BUCKET_NAME
ARG PUBSUB_TOPIC
ARG PUBSUB_SUBSCRIPTION
ARG PROJECT_ID
ARG LOCATION=global
ARG COLLECTION=default_collection
ARG ENGINE=alpha-evolve-infra-experiment-engine
ARG ASSISTANT=default_assistant
ARG BASE_URL=discoveryengine.googleapis.com
ARG MODEL=MODEL_UNSPECIFIED
ARG REGION_CODE=global
ARG MAX_PROGRAMS_GENERATED=10
ARG CONCURRENCY=4
ARG MAX_PROGRAMS_EVALUATED=20
ARG EVALUATION_MODE=batch
ARG NUM_SAMPLERS=4
ARG POLL_INTERVAL=4
ARG PROGRAMS_DIR="programs_candidate"
ARG DELETE_SUCCEEDED_JOBS="true"
ARG MAX_DURATION=6
ARG IDLE_TIMEOUT=5
ARG MAX_DURATION_SECONDS=3600
ARG MOUNT_PATH="/mnt/disks/share"
ARG REGION
ARG REPO_NAME
ARG EVALUATION_MACHINE_TYPE
ARG EVALUATION_PROVISIONING_MODEL # STANDARD or SPOT
ARG BOOT_DISK_IMAGE
ARG SERVICE_ACCOUNT_EMAIL
ARG EXAMPLE_DIR
ARG USER_EXPERIMENT_NAME
# Only used for N1 machine types
ARG ACCELERATOR_COUNT
ARG ACCELERATOR_TYPE

# Environment variables for the experiment configuration (Single layer)
ENV _CLOUD_BUCKET_NAME=${CLOUD_BUCKET_NAME} \
    _PUBSUB_TOPIC=${PUBSUB_TOPIC} \
    _PUBSUB_SUBSCRIPTION=${PUBSUB_SUBSCRIPTION} \
    _PROJECT_ID=${PROJECT_ID} \
    _LOCATION=${LOCATION} \
    _COLLECTION=${COLLECTION} \
    _ENGINE=${ENGINE} \
    _ASSISTANT=${ASSISTANT} \
    _BASE_URL=${BASE_URL} \
    _MODEL=${MODEL} \
    _REGION_CODE=${REGION_CODE} \
    _MAX_PROGRAMS_GENERATED=${MAX_PROGRAMS_GENERATED} \
    _CONCURRENCY=${CONCURRENCY} \
    _MAX_PROGRAMS_EVALUATED=${MAX_PROGRAMS_EVALUATED} \
    _EVALUATION_MODE=${EVALUATION_MODE} \
    _NUM_SAMPLERS=${NUM_SAMPLERS} \
    _POLL_INTERVAL=${POLL_INTERVAL} \
    _PROGRAMS_DIR=${PROGRAMS_DIR} \
    _DELETE_SUCCEEDED_JOBS=${DELETE_SUCCEEDED_JOBS} \
    _MAX_DURATION=${MAX_DURATION} \
    _IDLE_TIMEOUT=${IDLE_TIMEOUT} \
    _MAX_DURATION_SECONDS=${MAX_DURATION_SECONDS} \
    _MOUNT_PATH=${MOUNT_PATH} \
    _REGION=${REGION} \
    _REPO_NAME=${REPO_NAME} \
    _EVALUATION_MACHINE_TYPE=${EVALUATION_MACHINE_TYPE} \
    _EVALUATION_PROVISIONING_MODEL=${EVALUATION_PROVISIONING_MODEL} \
    _BOOT_DISK_IMAGE=${BOOT_DISK_IMAGE} \
    _SERVICE_ACCOUNT_EMAIL=${SERVICE_ACCOUNT_EMAIL} \
    _USER_EXPERIMENT_NAME=${USER_EXPERIMENT_NAME} \
    _ACCELERATOR_COUNT=${ACCELERATOR_COUNT} \
    _ACCELERATOR_TYPE=${ACCELERATOR_TYPE}

# Install build tools and python3-venv
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        make \
        g++ && \
    rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN uv venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Set the working directory
WORKDIR /app

# Copy ONLY requirements first to leverage Docker layer caching
COPY infrastructure/requirements.txt .

# Install dependencies using uv
# --require-hashes is kept as requested; --no-cache-dir is not needed with uv
RUN uv pip install --require-hashes -r requirements.txt

# Copy the rest of the source code
COPY google_framework/alpha_evolve ./src/alpha_evolve
COPY ${EXAMPLE_DIR} ./experiment/
COPY infrastructure/batch_configs/eval-batch.yaml ./eval-batch.yaml

# Set the working directory to the experiment folder
WORKDIR /app/experiment

# Add execution permissions to the entrypoint script
RUN chmod +x run_experiment.py

RUN useradd -m -u 1000 controller
RUN chown -R controller:controller /app
USER controller

# Set the entrypoint
ENTRYPOINT ["python", "run_experiment.py"]

