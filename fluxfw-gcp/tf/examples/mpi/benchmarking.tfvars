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

manager_machine_type = "e2-standard-8"
manager_name_prefix  = "benchmark"
manager_scopes       = [ "cloud-platform" ]

login_node_specs = [
    {
        name_prefix  = "benchmark-login"
        machine_arch = "x86-64"
        machine_type = "e2-standard-4"
        instances    = 1
    },
]
login_scopes = [ "cloud-platform" ]

compute_node_specs = [
    {
        name_prefix  = "intel-benchmark-compute"
        machine_arch = "x86-64"
        machine_type = "c2-standard-8"
        gpu_type     = null
        gpu_count    = 0
        compact      = true
        instances    = 2
        properties   = [ "Intel" ]
        boot_script  = "install-mpitests.sh"
    },
    {
        name_prefix  = "amd-benchmark-compute"
        machine_arch = "x86-64"
        machine_type = "c2d-standard-8"
        gpu_type     = null
        gpu_count    = 0
        compact      = true
        instances    = 2
        properties   = [ "AMD" ]
        boot_script  = "install-mpitests.sh"
    },
]
compute_scopes = [ "cloud-platform" ]
