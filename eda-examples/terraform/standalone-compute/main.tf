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
  master_os_image = "centos-cloud/centos-7"
}

data "terraform_remote_state" "storage" {
  backend = "local"

  config = {
    path = "../storage/terraform.tfstate"
  }
}

resource "google_compute_instance" "eda-n2" {
  count        = 1
  name         = "eda-n2-${count.index}"
  machine_type = "n2-standard-2"
  zone         = var.zone

  tags = var.tags

  boot_disk {
    initialize_params {
      image = local.master_os_image

    }
  }
  scratch_disk {
    interface = "NVME" # Note: check if your OS image requires additional drivers or config to optimize NVME performance
  }
  metadata = {
    enable-oslogin = "TRUE"
  }

  network_interface {
    network = var.network
    access_config {} # Ephemeral IP
  }

  metadata_startup_script = templatefile("provision.sh.tmpl", {
    home_ip = data.terraform_remote_state.storage.outputs.home-volume-ip-addresses[0],
    tools_ip = data.terraform_remote_state.storage.outputs.tools-volume-ip-addresses[0],
  })

  service_account {
    #scopes = ["userinfo-email", "compute-ro", "storage-full"]
    scopes = ["cloud-platform"]  # too permissive for production
  }

}

resource "google_compute_instance" "eda-n2d" {
  count        = 1
  name         = "eda-n2d-${count.index}"
  machine_type = "n2d-highmem-2"
  zone         = var.zone

  tags = var.tags

  boot_disk {
    initialize_params {
      image = local.master_os_image

    }
  }
  scratch_disk {
    interface = "NVME" # Note: check if your OS image requires additional drivers or config to optimize NVME performance
  }
  metadata = {
    enable-oslogin = "TRUE"
  }

  network_interface {
    network = var.network
    access_config {} # Ephemeral IP
  }

  metadata_startup_script = templatefile("provision.sh.tmpl", {
    home_ip = data.terraform_remote_state.storage.outputs.home-volume-ip-addresses[0],
    tools_ip = data.terraform_remote_state.storage.outputs.tools-volume-ip-addresses[0],
  })

  service_account {
    #scopes = ["userinfo-email", "compute-ro", "storage-full"]
    scopes = ["cloud-platform"]  # too permissive for production
  }

}

resource "google_compute_instance" "eda-c2" {
  count        = 1
  name         = "eda-c2-${count.index}"
  machine_type = "c2-standard-4"
  zone         = var.zone

  tags = var.tags

  boot_disk {
    initialize_params {
      image = local.master_os_image

    }
  }
  scratch_disk {
    interface = "NVME" # Note: check if your OS image requires additional drivers or config to optimize NVME performance
  }
  metadata = {
    enable-oslogin = "TRUE"
  }

  network_interface {
    network = var.network
    access_config {} # Ephemeral IP
  }

  metadata_startup_script = templatefile("provision.sh.tmpl", {
    home_ip = data.terraform_remote_state.storage.outputs.home-volume-ip-addresses[0],
    tools_ip = data.terraform_remote_state.storage.outputs.tools-volume-ip-addresses[0],
  })

  service_account {
    #scopes = ["userinfo-email", "compute-ro", "storage-full"]
    scopes = ["cloud-platform"]  # too permissive for production
  }

}
