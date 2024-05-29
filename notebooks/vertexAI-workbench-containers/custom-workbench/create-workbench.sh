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

LOCATION="us-central1-c"
REPOSITORY="us-central1-docker.pkg.dev/mycoolprojectname/mycustomimagerepo"
IMAGE="mycustomimage:latest"

# upstream
#REPOSITORY="gcr.io/deeplearning-platform-release"
#IMAGE="base-gpu.py310"

# Usage: gcloud notebooks instances create (INSTANCE : --location=LOCATION) [optional flags]
# optional flags may be  --accelerator-core-count | --accelerator-type |
#                        --async | --boot-disk-size | --boot-disk-type |
#                        --container-repository | --container-tag |
#                        --custom-gpu-driver-path | --data-disk-size |
#                        --data-disk-type | --disk-encryption | --environment |
#                        --environment-location | --help |
#                        --install-gpu-driver | --instance-owners | --kms-key |
#                        --kms-keyring | --kms-location | --kms-project |
#                        --labels | --location | --machine-type | --metadata |
#                        --network | --post-startup-script | --no-proxy-access |
#                        --no-public-ip | --no-remove-data-disk |
#                        --reservation | --reservation-affinity |
#                        --service-account | --shielded-integrity-monitoring |
#                        --shielded-secure-boot | --shielded-vtpm | --subnet |
#                        --subnet-region | --tags | --vm-image-family |
#                        --vm-image-name | --vm-image-project

    #--network="tutorial" \
    #--subnet="tutorial" \

gcloud notebooks instances create \
  --location="${LOCATION}" \
  --container-repository="${REPOSITORY}" \
  --container-tag="${IMAGE}" \
  --no-public-ip \
  "mycustomworkbench-0"
