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

variable "enable_secure_boot" {
    type    = bool
    default = true
}

variable "machine_type" {
    type    = string
}

variable "project_id" {
    type    = string
}

variable "source_image" {
    type    = string
}

variable "source_image_project_id" {
    type    = string
}

variable "subnetwork" {
    type    = string
    default = "default"
}

variable "zone" {
    type    = string
}

source "googlecompute" "flux_fw_manager_node_builder" {
    project_id              = var.project_id
    source_image            = var.source_image
    source_image_project_id = [var.source_image_project_id]
    zone                    = var.zone
    image_name              = "flux-fw-manager-v{{timestamp}}"
    image_family            = "flux-fw-manager"
    image_description       = "flux-fw-manager"
    machine_type            = var.machine_type
    disk_size               = 256
    subnetwork              = var.subnetwork
    tags                    = ["packer","flux", "manager"]
    account_file            = "image-builder.key"
    startup_script_file     = "flux-manager-builder-startup-script.sh"
    ssh_username            = "rocky"
    enable_secure_boot      = var.enable_secure_boot
}

build {
    sources = ["source.googlecompute.flux_fw_manager_node_builder"]
}
