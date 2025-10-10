#!/bin/bash

# Copyright 2025 Google LLC
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
set -o pipefail # more output
set -x # verbose

export EGO_TOP=$1
export PROJECT_ID=$2

git clone https://github.com/google/symphony-gcp.git
cd symphony-gcp/hf-provider
curl -LsSf https://astral.sh/uv/install.sh | sh
source /root/.local/bin/env
uv venv
source .venv/bin/activate
uv pip install .
uv pip install pyinstaller
PYTHONPATH=src pyinstaller --onefile src/gce_provider/__main__.py --name hf-gce --paths .venv/lib/python3.9/site-packages

cp dist/hf-gce resources/gce_cli/1.2/providerplugins/gcpgce/bin/
cd resources/gce_cli

# Create deployment tar
tar czf hf-gce.tgz *

# Get Symphony Environment
source ${EGO_TOP}/profile.platform

# Untar in Hostfactory
tar -xzf hf-gce.tgz  -C $HF_TOP

# Update Config

cp /tmp/Symphony/hostProviderPlugins.json $HF_TOP/conf/providerplugins/hostProviderPlugins.json
cp /tmp/Symphony/hostProviders.json $HF_TOP/conf/providers/hostProviders.json
cp /tmp/Symphony/hostRequestors.json $HF_TOP/conf/requestors/hostRequestors.json

sed -i -e "s|MANUAL|AUTOMATIC|g" $EGO_ESRVDIR/esc/conf/services/hostfactory.xml