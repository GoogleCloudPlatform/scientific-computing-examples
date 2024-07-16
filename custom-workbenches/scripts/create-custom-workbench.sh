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

ZONE="us-central1-c"

#IMAGE_URI="<region>-docker.pkg.dev/<mycoolprojectname>/<mycustomimagerepo>/<mycustomimagename>"
IMAGE_URI="us-central1-docker.pkg.dev/<mycoolprojectname>/<mycustomimagerepo>/<mycustomimagename>"
IMAGE_TAG="latest"
# For non-customized "vanilla" workbenches:
#IMAGE_URI="gcr.io/deeplearning-platform-release/workbench-container"
#IMAGE_TAG="latest"

#
# Usage: gcloud workbench instances create (INSTANCE : --location=LOCATION) [optional flags]
#   optional flags may be  --accelerator-core-count | --accelerator-type |
#                          --async | --boot-disk-encryption |
#                          --boot-disk-encryption-key-keyring |
#                          --boot-disk-encryption-key-location |
#                          --boot-disk-encryption-key-project |
#                          --boot-disk-kms-key | --boot-disk-size |
#                          --boot-disk-type | --container-repository |
#                          --container-tag | --custom-gpu-driver-path |
#                          --data-disk-encryption |
#                          --data-disk-encryption-key-keyring |
#                          --data-disk-encryption-key-location |
#                          --data-disk-encryption-key-project |
#                          --data-disk-kms-key | --data-disk-size |
#                          --data-disk-type | --disable-proxy-access |
#                          --disable-public-ip | --enable-ip-forwarding | --help |
#                          --install-gpu-driver | --instance-owners | --labels |
#                          --location | --machine-type | --metadata | --network |
#                          --nic-type | --service-account-email |
#                          --shielded-integrity-monitoring |
#                          --shielded-secure-boot | --shielded-vtpm | --subnet |
#                          --subnet-region | --tags | --vm-image-family |
#                          --vm-image-name | --vm-image-project
#
gcloud workbench instances create \
  --location="${ZONE}" \
  --container-repository="${IMAGE_URI}" \
  --container-tag="${IMAGE_TAG}" \
  --metadata="notebook-disable-root=TRUE" \
  --disable-public-ip \
  "mycustomworkbench-0-0"


# Even though this only has internal IP addresses, you can still open the
# notebook interface from `Vertex AI -> Workbenches` in the Google Cloud Console
# web page. It transparently uses Identity Aware Proxy (IAP) to connect.  Note
# this might be blocked via org-level policies.
#
# You can also ssh directly to the instance:
#   gcloud compute ssh mycustomworkbench-0 --zone us-central1-c
# Note this access can also be limited using org-level policies.
#
# Delete this workbench instance using the Cloud Console or `gcloud` commands similar to:
#   gcloud workbench instances list --location us-central1-c
# and
#   gcloud workbench instances delete mycustomworkbench-0 --location us-central1-c
#
