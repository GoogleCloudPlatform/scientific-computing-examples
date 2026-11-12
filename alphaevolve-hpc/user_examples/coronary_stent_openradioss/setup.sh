#!/bin/bash
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

set -euo pipefail

OPENRADIOSS_VERSION="20230915"
INSTALL_DIR="${OPENRADIOSS_PATH:-/opt/OpenRadioss}"

if [ ! -f "${INSTALL_DIR}/exec/starter_linux64_gf_sp" ]; then
  echo "OpenRADIOSS not found at ${INSTALL_DIR}; checking /tmp/openradioss_test..."
  if [ -f "/tmp/openradioss_test/OpenRadioss_linux64_${OPENRADIOSS_VERSION}/OpenRadioss/exec/starter_linux64_gf_sp" ]; then
    export OPENRADIOSS_PATH="/tmp/openradioss_test/OpenRadioss_linux64_${OPENRADIOSS_VERSION}/OpenRadioss"
    echo "Using existing OpenRADIOSS at ${OPENRADIOSS_PATH}"
  else
    echo "Downloading OpenRADIOSS ${OPENRADIOSS_VERSION} release binary..."
    mkdir -p /opt
    curl -sSL "https://github.com/OpenRadioss/OpenRadioss/releases/download/v${OPENRADIOSS_VERSION}/OpenRadioss_linux64_${OPENRADIOSS_VERSION}.tar.gz" \
      | tar -xz -C /opt
    ln -sf "/opt/OpenRadioss_linux64_${OPENRADIOSS_VERSION}/OpenRadioss" /opt/OpenRadioss
    export OPENRADIOSS_PATH="/opt/OpenRadioss"
  fi
fi

echo "Verified OpenRADIOSS installation at ${OPENRADIOSS_PATH:-${INSTALL_DIR}}"
