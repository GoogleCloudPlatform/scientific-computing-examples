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

#packer {
#  required_plugins {
#    googlecompute = {
#      version = ">= 1.1.4"
#      source  = "github.com/hashicorp/googlecompute"
#    }
#  }
#}

variable "project_id" {
  type    = string
  default = ""
}

variable "zone" {
  type    = string
  default = "us-central1-c"
}

variable "network" {
  type    = string
  default = "tutorial"
}

variable "subnet" {
  type    = string
  default = "tutorial"
}

variable "image" {
  type    = string
  default = "custom-image-default"
}

locals {
  timestamp = regex_replace(timestamp(), "[- TZ:]", "")
  region = join("-", slice(split("-", var.zone), 0, 2))
}

source "googlecompute" "gcp_ubuntu" {
  project_id          = var.project_id
  source_image            = "ubuntu-2004-focal-v20220204"
  ssh_username       = "packer-sa"
  instance_name      = "ubuntu-image-build"
  zone               = var.zone
  network            = "projects/${var.project_id}/global/networks/${var.network}"
  subnetwork         = "projects/${var.project_id}/regions/${local.region}/subnetworks/${var.subnet}"
  network_project_id = var.project_id
  use_internal_ip    = true
  omit_external_ip   = true
  use_iap            = true
  use_os_login       = true
  metadata = {
    block-project-ssh-keys = "true"
  }
  tags = ["customworkbench", "ubuntu-focal", "packer"]
}

source "googlecompute" "deeplearning_platform_debian" {
  project_id          = var.project_id
  zone               = var.zone
  #source_image_project_id = [ "deeplearning-platform-release" ]
  #source_image_family     = "common-cpu-debian-11"
  source_image_project_id = [ "cloud-notebooks-managed" ]
  #source_image_family     = "workbench-instances"
  source_image     = "workbench-instances-v20240708"
  instance_name      = "debian-image-build"
  ssh_username       = "packer-sa"
  disk_size           = "100"
  network_project_id = var.project_id
  network            = "projects/${var.project_id}/global/networks/${var.network}"
  subnetwork         = "projects/${var.project_id}/regions/${local.region}/subnetworks/${var.subnet}"
  enable_nested_virtualization = true
  use_internal_ip    = true
  omit_external_ip   = true
  use_iap            = true
  use_os_login       = true
  metadata = {
    block-project-ssh-keys = "true"
  }
  tags = ["customworkbench", "debian-11", "packer"]
}

build {
  name                = "custom-cpu"

  # source "source.googlecompute.gcp_ubuntu" {
  #   image_family        = "ubuntu-2004-gnome-crd"
  #   image_name          = "ubuntu-2004-gnome-crd-${local.timestamp}"
  #   image_description   = "gnome crd workstation image"
  # }
  source "source.googlecompute.deeplearning_platform_debian" {
    image_family        = "custom-cpu-build"
    #image_name          = "custom-cpu-${local.timestamp}"
    image_name          = var.image
    image_description   = "custom image based on the deeplearning-platform-release/common-cpu-debian image family"
    image_storage_locations = ["us"]
  }

  provisioner "shell" {
    execute_command = "chmod +x {{ .Path }}; sudo bash -c 'DESKTOP=gnome {{ .Vars }} {{ .Path }}'"
    scripts         = fileset(".", "custom-image-scripts/*")
  }

  #
  # The image export process spins up an instance. this `post-processor`
  # interface does not allow that to only use a private IP so instead of this
  # post-processor, we'll run `gcloud compute images export...` from
  # `cloudbuild.yaml` after the image is built.
  #
  # post-processor "googlecompute-export" {
  #   paths = [
  #     "gs://${var.project_id}/images/custom-cpu-${local.timestamp}.tar.gz"
  #   ]
  #   keep_input_artifact = true
  # }
  #
}

