#
# Copyright 2024 Google LLC
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
  workbench_count       = 1
  default_instance_type = "n2-standard-4"
}

data "google_compute_default_service_account" "default" {}
data "google_compute_network" "tutorial" { name = var.network }
data "google_compute_subnetwork" "tutorial" {
  name = var.subnet
  region = join("-", slice(split("-", var.zone), 0, 2))
}

resource "google_workbench_instance" "workbench" {
  count    = local.workbench_count
  name     = "workbench-${count.index}"
  location = var.zone

  gce_setup {
    machine_type = local.default_instance_type

    # accelerator_configs {
    #   type         = "NVIDIA_TESLA_T4"
    #   core_count   = 1
    # }

    # vm_image {
    #   project = "deeplearning-platform-release"
    #   family  = "tf-latest-cpu"
    #   # family = "tf-latest-gpu"
    # }
    container_image {
      repository = "gcr.io/deeplearning-platform-release/base-gpu.py310"
      tag  = "latest"
    }

    boot_disk {
      disk_size_gb = 310
      disk_type    = "PD_SSD"
    }

    data_disks {
      disk_size_gb = 330
      disk_type    = "PD_SSD"
    }

    network_interfaces {
      network  = data.google_compute_network.tutorial.id
      subnet   = data.google_compute_subnetwork.tutorial.id
      nic_type = "GVNIC"
    }
    disable_public_ip = true
    # enable_ip_forwarding = true

    metadata = {
      terraform = "true"
      #enable-oslogin = "TRUE"
    }

    tags = ["abc", "def"]

    #post_startup_script = "gs://bucket/path/script"
    # so maybe
    #post_startup_script = google_storage_bucket_object.startup_script.media_link
    # or
    #post_startup_script = google_storage_bucket_object.startup_script.output_name
    # or
    #post_startup_script = "gs://${var.state_bucket}/${google_storage_bucket_object.startup_script.output_name}"

    service_accounts {
      email = data.google_compute_default_service_account.default.email
    }
  }

  disable_proxy_access = false

  # instance_owners  = [ "my@service-account.com"]

  labels = {
    k = "val"
  }

  desired_state = "ACTIVE"

}
