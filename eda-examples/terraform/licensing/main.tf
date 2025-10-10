#
# Copyright 2020 Google LLC
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

locals {
  license_server_os_image = "centos-cloud/centos-7"
  license_server_machine_type = "n2d-standard-2"
}

resource "google_compute_instance" "license-server" {
  name         = "license-server"
  machine_type = local.license_server_machine_type
  zone         = var.zone

  tags = var.tags

  boot_disk {
    initialize_params {
      image = local.license_server_os_image

    }
  }
  metadata = {
    enable-oslogin = "TRUE"
  }

  network_interface {
    network = var.network

    access_config {} # ephemeral public IP... comment this out for private-only networking
  }

  metadata_startup_script = file("provision.sh")

  service_account {
    scopes = ["userinfo-email", "compute-ro", "storage-full"]
    #scopes = ["cloud-platform"]  # too permissive for production
  }

}
