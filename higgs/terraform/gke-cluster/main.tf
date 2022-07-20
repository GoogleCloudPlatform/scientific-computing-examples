#
# Copyright 2019 Google LLC
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

resource "google_container_cluster" "higgs-tutorial" {
  name               = "${var.k8s-cluster-name}"
  location           = "${var.gcp-region}"
  initial_node_count = "${var.k8s-cluster-node-count}"
  logging_service = "none"
  monitoring_service = "none"

  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  node_config {
    disk_size_gb = 90
    disk_type = "pd-ssd"
    image_type = "cos"
    local_ssd_count = 1
    machine_type = "${var.k8s-cluster-node-type}"

    metadata = {
      disable-legacy-endpoints = "true"
    }

    oauth_scopes = [
      #"https://www.googleapis.com/auth/compute",
      "https://www.googleapis.com/auth/devstorage.read_only",
      #"https://www.googleapis.com/auth/logging.write",
      #"https://www.googleapis.com/auth/monitoring",
    ]


    labels = {
      foo = "higgs-demo"
    }

    #tags = ["foo", "bar"]
  }

  timeouts {
    create = "30m"
    update = "40m"
  }
}
