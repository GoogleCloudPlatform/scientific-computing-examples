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

module "management_node" {
    source             = "./modules/management"
    name_prefix        = var.manager_name_prefix
    enable_os_login    = var.enable_os_login
    family             = var.manager_family  
    
    project_id         = var.project_id
    region             = var.region
    
    subnetwork         = var.subnetwork
    machine_type       = var.manager_machine_type

    service_account    = {
        email  = var.service_account_emails["manager"]
        scopes = var.manager_scopes
    }

    compute_node_specs = jsonencode(var.compute_node_specs)
    login_node_specs   = jsonencode(var.login_node_specs)

    nfs_mounts         = var.cluster_storage
}

module "login_nodes" {
    source          = "./modules/login"

    for_each = {
        for index, node in var.login_node_specs:
        node.name_prefix => node
    }
    project_id      = var.project_id
    region          = var.region

    name_prefix     = each.value.name_prefix
    enable_os_login = var.enable_os_login
    family          = var.login_family

    subnetwork      = var.subnetwork
    machine_arch    = each.value.machine_arch
    machine_type    = each.value.machine_type
    num_instances   = each.value.instances
    manager         = module.management_node.name

    boot_script       = lookup(each.value, "boot_script", null) == null ? null : file("${each.value.boot_script}")
    service_account = {
        email  = var.service_account_emails["login"]
        scopes = var.login_scopes
    }

    nfs_mounts      = var.cluster_storage
}

module "compute_nodes" {
    source          = "./modules/compute"

    for_each = {
        for index, node in var.compute_node_specs:
        node.name_prefix => node
    }
    project_id        = var.project_id
    region            = var.region

    family            = var.compute_family
    enable_os_login   = var.enable_os_login
    arm_family        = var.compute_arm_family
    
    name_prefix       = each.value.name_prefix
    subnetwork        = var.subnetwork
    machine_arch      = each.value.machine_arch
    machine_type      = each.value.machine_type
    num_instances     = each.value.instances
    manager           = module.management_node.name

    boot_script       = lookup(each.value, "boot_script", null) == null ? null : file("${each.value.boot_script}")
    compact_placement = lookup(each.value, "compact", false)
    gpu               = lookup(each.value, "gpu_type", null) == null || lookup(each.value, "gpu_count", 0) <= 0 ? null : {
        type  = each.value.gpu_type
        count = each.value.gpu_count
    }
    service_account   = {
        email  = var.service_account_emails["compute"]
        scopes = var.compute_scopes
    }

    login_node_specs  = jsonencode(var.login_node_specs)
    nfs_mounts        = var.cluster_storage
}
