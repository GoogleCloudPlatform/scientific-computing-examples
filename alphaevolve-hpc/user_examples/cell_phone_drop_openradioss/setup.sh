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

apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    xz-utils \
    libgomp1 \
    libquadmath0 \
    libgfortran5 \
    libuuid1 \
    libcrypt1 \
    && rm -rf /var/lib/apt/lists/*

echo "[setup.sh] Downloading and installing OpenRADIOSS x86_64 binaries to /opt/OpenRadioss..."
mkdir -p /tmp/openradioss_dl
wget -q -O /tmp/openradioss_dl/OpenRadioss_linux64.tar.xz \
    "http://www.phoronix-test-suite.com/benchmark-files/OpenRadioss_linux64_20230915.tar.xz"
tar -xf /tmp/openradioss_dl/OpenRadioss_linux64.tar.xz -C /tmp/openradioss_dl
mv /tmp/openradioss_dl/OpenRadioss_linux64_20230915/OpenRadioss /opt/OpenRadioss
rm -rf /tmp/openradioss_dl

# Remove unused MPI / double-precision engine variants to keep image layer compact
rm -f /opt/OpenRadioss/exec/*_ompi* /opt/OpenRadioss/exec/*_impi* /opt/OpenRadioss/exec/engine_linux64_gf
chmod -R a+rX /opt/OpenRadioss
echo "[setup.sh] OpenRADIOSS installed successfully at /opt/OpenRadioss."
