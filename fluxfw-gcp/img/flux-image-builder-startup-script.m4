#!/bin/bash 

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

ifdef(`X86_64', `include(add_gcsfuse_repo.txt)')dnl

dnf update -y
dnf clean all

dnf group install -y "Development Tools"

dnf config-manager --set-enabled powertools
dnf install -y epel-release

dnf install -y \
ifdef(`X86_64', `include(x86_64_packages.txt)', `include(arm64_packages.txt)')dnl

ifdef(`X86_64', `include(nvidia_downloads.txt)')dnl

python3.11 -m pip install cffi pyyaml jsonschema sphinx

cd /usr/share

git clone -b v0.61.2 https://github.com/flux-framework/flux-core.git
git clone -b v0.33.1 https://github.com/flux-framework/flux-sched.git
git clone -b v0.11.0 https://github.com/flux-framework/flux-security.git

cd /usr/share/flux-security

./autogen.sh
./configure --prefix=/usr/local

make
make install

cd /usr/share/flux-core

./autogen.sh
PKG_CONFIG_PATH=$(pkg-config --variable pc_path pkg-config)
PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH
PKG_CONFIG_PATH=${PKG_CONFIG_PATH} ./configure --prefix=/usr/local --with-flux-security

make -j 8
make install

cd /usr/share/flux-sched

./autogen.sh
./configure --prefix=/usr/local

make
make install
