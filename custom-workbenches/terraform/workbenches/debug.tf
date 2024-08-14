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

resource "google_workbench_instance" "debug-workbench" {
  count    = 0
  name     = "debug-workbench-${count.index}"
  location = var.zone

  gce_setup {
    #machine_type = "n1-standard-4"
    machine_type = "e2-standard-4"

    # accelerator_configs {
    #   type         = "NVIDIA_TESLA_T4"
    #   core_count   = 1
    # }

    # container_image {
    #   repository = "gcr.io/mmm-as-workbenches/tutorial/myjuliaimage"
    #   tag  = "latest"
    # }
    vm_image {
      project = data.google_project.project.name
      #family = "custom-cpu-build"
      name = "my-workbench-from-instance-0"
    }
    # vm_image {
    #   project = "cloud-notebooks-managed"
    #   family  = "workbench-instances"
    # }

    boot_disk {
      disk_size_gb = 310
      disk_type    = "PD_BALANCED"
    }

    data_disks {
      disk_size_gb = 100
      disk_type    = "PD_BALANCED"
    }

    network_interfaces {
      network  = data.google_compute_network.tutorial.id
      subnet   = data.google_compute_subnetwork.tutorial.id
      #nic_type = "GVNIC"
    }
    disable_public_ip = true
    # enable_ip_forwarding = true

    metadata = {
        serial-port-logging-enable = true
        report-event-health        = true
        terraform                  = true
        report-dns-resolution      = true
        disable-mixer              = true
        idle-timeout-seconds       = 10800
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
  instance_owners = []

  labels = {
    k = "val"
  }

  desired_state = "ACTIVE"

}

# resource "google_notebooks_instance" "instance" {
#   count    = 1
#   name     = "notebooks-instance-${count.index}"
#   location = var.zone
#   machine_type = "e2-medium"
#   # metadata = {
#   #   proxy-mode = "service_account"
#   #   terraform  = "true"
#   # }
#   container_image {
#     repository = "gcr.io/deeplearning-platform-release/workbench-container"
#     tag = "latest"
#   }
#   network  = data.google_compute_network.tutorial.id
#   subnet   = data.google_compute_subnetwork.tutorial.id
#   no_public_ip = true
# }
