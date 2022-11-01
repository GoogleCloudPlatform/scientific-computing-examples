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

output "subnet" {
    value = { 
        project = module.network.subnets["${var.region}/${module.network.subnets_names[0]}"].project,
        region  = var.region,
        network_name = module.network.network_name
        self_link = module.network.subnets_self_links[0]
    }
}
