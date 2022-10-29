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

data "google_compute_zones" "available" {
    project = data.terraform_remote_state.network.outputs.subnet.project
    region  = data.terraform_remote_state.network.outputs.subnet.region
}

resource "google_filestore_instance" "instance" {
    project     = data.terraform_remote_state.network.outputs.subnet.project
    provider    = google-beta
    location    = data.google_compute_zones.available.names[0]

    name        = var.name
    tier        = var.tier
    
    file_shares {
        name        = var.share_name
        capacity_gb = 1024
    }
    
    networks {
        network = data.terraform_remote_state.network.outputs.subnet.network_name
        modes   = ["MODE_IPV4"]
    }
}
