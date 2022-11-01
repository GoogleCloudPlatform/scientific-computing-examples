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

dnf install -y wget git

cd /opt
mkdir julia
cd julia

wget https://julialang-s3.julialang.org/bin/linux/x64/1.8/julia-1.8.2-linux-x86_64.tar.gz
tar xf julia-1.8.2-linux-x86_64.tar.gz
rm julia-1.8.2-linux-x86_64.tar.gz

ln -s /opt/julia/julia-1.8.2/bin/julia /usr/local/bin

cd ~

mkdir -p /usr/local/share/applications/julia/depot
export JULIA_DEPOT_PATH=/usr/local/share/applications/julia/depot:$JULIA_DEPOT_PATH

julia -e 'using Pkg; Pkg.add("CUDA")'

chmod a+rw -R /usr/local/share/applications/julia/depot
