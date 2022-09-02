#!/usr/bin/env bash

# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

if [ ! -d "cloud-builders-community" ]; then
    git clone https://github.com/GoogleCloudPlatform/cloud-builders-community.git
    pushd cloud-builders-community/packer
else
    pushd cloud-builders-community
    git pull
    cd packer
fi

export PACKER_VERSION=$(curl -Ls https://releases.hashicorp.com/packer | grep packer | sed 's/.*>packer\(.*\)<.*/packer\1/g' | sort -r | uniq | head -n1 | cut -d'_' -f2)
export PACKER_VERSION_SHA256SUM=$(curl -Ls https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_SHA256SUMS | grep linux_amd64 | cut -d' ' -f1)

gcloud builds submit --substitutions=_PACKER_VERSION=${PACKER_VERSION},_PACKER_VERSION_SHA256SUM=${PACKER_VERSION_SHA256SUM} .

popd
