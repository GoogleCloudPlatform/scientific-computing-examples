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

data "google_compute_image" "fluxfw_manager_image" {
    project = var.project_id
    family  = "flux-fw-manager"
}

module "flux_manager_instance_template" {
    source               = "github.com/terraform-google-modules/terraform-google-vm/modules/instance_template"
    region               = var.region
    project_id           = var.project_id
    name_prefix          = "${var.name_prefix}-manager"
    subnetwork           = var.subnetwork
    service_account      = var.service_account
    tags                 = ["ssh", "flux", "manager"]
    machine_type         = var.machine_type
    disk_size_gb         = 1024
    source_image         = data.google_compute_image.fluxfw_manager_image.self_link
    source_image_project = data.google_compute_image.fluxfw_manager_image.project
    metadata             = {
        "enable-oslogin"     : "TRUE",
        "VmDnsSetting"       : "GlobalDefault"
        "nfs-mounts"         : jsonencode(var.nfs_mounts)
        "compute-node-specs" : var.compute_node_specs
        "login-node-specs"   : var.login_node_specs
    }
}

module "flux_manager_instance" {
    source              = "github.com/terraform-google-modules/terraform-google-vm/modules/compute_instance"
    region              = var.region
    hostname            = "${var.name_prefix}-manager"
    num_instances       = 1
    instance_template   = module.flux_manager_instance_template.self_link
    subnetwork          = var.subnetwork
}
