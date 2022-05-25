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

data "google_compute_image" "fluxfw_compute_arm64_image" {
    project = var.project_id
    family  = "flux-fw-compute-arm64"
}

data "google_compute_image" "fluxfw_compute_x86_64_image" {
    project = var.project_id
    family  = "flux-fw-compute-x86-64"
}

data "google_compute_zones" "available" {
    project = var.project_id
    region  = var.region
}

locals {
    automatic_restart = var.compact_placement ? false : var.automatic_restart
    compute_images = {
        "arm64" = {
            image   = data.google_compute_image.fluxfw_compute_arm64_image.self_link
            project = data.google_compute_image.fluxfw_compute_arm64_image.project
        },
        "x86-64" = {
            image   = data.google_compute_image.fluxfw_compute_x86_64_image.self_link
            project = data.google_compute_image.fluxfw_compute_x86_64_image.project
        }
    }
    on_host_maintenance = var.compact_placement ? "TERMINATE" : var.on_host_maintenance
}

resource "google_compute_resource_policy" "collocated" {
    count   = var.compact_placement ? 1 : 0
    name    = "${var.name_prefix}-collocated-policy"
    project = var.project_id
    region  = var.region
    group_placement_policy {
      vm_count = var.num_instances
      collocation = "COLLOCATED"
    }
}

module "flux_compute_instance_template" {
    source               = "github.com/terraform-google-modules/terraform-google-vm/modules/instance_template"
    region               = var.region
    project_id           = var.project_id
    name_prefix          = var.name_prefix
    subnetwork           = var.subnetwork
    gpu                  = var.gpu
    service_account      = var.service_account
    tags                 = ["ssh", "flux", "compute"]
    machine_type         = var.machine_type
    disk_size_gb         = 256
    source_image         = local.compute_images["${var.machine_arch}"].image
    source_image_project = local.compute_images["${var.machine_arch}"].project
    automatic_restart    = local.automatic_restart
    on_host_maintenance  = local.on_host_maintenance

    metadata             = { 
        "boot-script"      : var.boot_script
        "login-node-specs" : var.login_node_specs
        "enable-oslogin"   : "TRUE",
        "flux-manager"     : "${var.manager}",
        "VmDnsSetting"     : "GlobalDefault",
        "nfs-mounts"       : jsonencode(var.nfs_mounts),
        "gpus-attached"    : var.gpu != null ? "TRUE" : "FALSE"
    }
}

module "flux_compute_instances" {
    source              = "github.com/terraform-google-modules/terraform-google-vm/modules/compute_instance"
    region              = var.region
    zone                = data.google_compute_zones.available.names[0]
    hostname            = var.name_prefix
    add_hostname_suffix = true
    num_instances       = var.num_instances
    resource_policies   = var.compact_placement ? [ google_compute_resource_policy.collocated[0].self_link ] : []
    instance_template   = module.flux_compute_instance_template.self_link
    subnetwork          = var.subnetwork
}
