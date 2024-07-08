#!/bin/bash
#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

REGION="us-central1"
IMAGE_BUILD_DIR=mycustomimage
IMAGE_TAG="us-central1-docker.pkg.dev/mycoolprojectname/mycustomimagerepo/mycustomimage:latest"

mkdir -p ${IMAGE_BUILD_DIR}

cat << EOF > ${IMAGE_BUILD_DIR}/Dockerfile
FROM gcr.io/deeplearning-platform-release/base-gpu.py310

RUN pip install -q flask
EOF

cat << EOF > ${IMAGE_BUILD_DIR}/cloudbuild.yaml
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: [ 'build', '-t', '${IMAGE_TAG}', '.' ]
- name: 'gcr.io/cloud-builders/docker'
  args: [ 'push', '${IMAGE_TAG}' ]
images: [ '${IMAGE_TAG}' ]
EOF

# gcloud builds submit [[SOURCE] --no-source] [--async] [--no-cache]
#     [--default-buckets-behavior=DEFAULT_BUCKETS_BEHAVIOR] [--dir=DIR]
#     [--disk-size=DISK_SIZE] [--gcs-log-dir=GCS_LOG_DIR]
#     [--gcs-source-staging-dir=GCS_SOURCE_STAGING_DIR]
#     [--git-source-dir=GIT_SOURCE_DIR]
#     [--git-source-revision=GIT_SOURCE_REVISION] [--ignore-file=IGNORE_FILE]
#     [--machine-type=MACHINE_TYPE] [--region=REGION] [--revision=REVISION]
#     [--service-account=SERVICE_ACCOUNT] [--substitutions=[KEY=VALUE,...]]
#     [--suppress-logs] [--timeout=TIMEOUT] [--worker-pool=WORKER_POOL]
#     [--config=CONFIG; default="cloudbuild.yaml"
#       | --pack=[builder=BUILDER],[env=ENV],[image=IMAGE]
#       | --tag=TAG, -t TAG] [GCLOUD_WIDE_FLAG ...]
echo gcloud builds submit \
  --region=${REGION} \
  ${IMAGE_BUILD_DIR}
