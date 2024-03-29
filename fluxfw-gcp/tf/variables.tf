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

variable "cluster_storage" { 
    description = "A map with keys 'share' and 'mountpoint' describing an NFS export and its intended mount point"
    type        = map(string)
}

variable "compute_arm_family" {
    description = "The source arm image family prefix to be used by the compute node(s)"
    type        = string
    default     = "flux-fw-compute-arm64"
}

variable "compute_family" {
    description = "The source image x86 prefix to be used by the compute node(s)"
    type        = string
    default     = "flux-fw-compute-x86-64"
}

variable "compute_node_specs" {
    description = "A list of compute node specifications"
    type = list(object({
       name_prefix  = string
       machine_arch = string
       machine_type = string
       gpu_type     = string
       gpu_count    = number
       compact      = bool
       instances    = number
       properties   = set(string)
       boot_script  = string
    }))
    default = []
}

variable "compute_scopes" {
    description = "The set of access scopes for compute node instances"
    default     = [ "cloud-platform" ]
    type        = set(string)
}


variable "login_family" {
    description = "The source image prefix to be used by the login node"
    type        = string
    default     = "flux-fw-login-x86-64"
}


variable "login_node_specs" {
    description = "A list of login node specifications"
    type = list(object({
       name_prefix  = string
       machine_arch = string
       machine_type = string
       instances    = number
       properties   = set(string)
       boot_script  = string
    }))
    default = []
}

variable "login_scopes" {
    description = "The set of access scopes for login node instances"
    default     = [ "cloud-platform" ]
    type = set(string)
}

variable "manager_family" {
    description = "The source image prefix to be used by the manager"
    type        = string
    default     = "flux-fw-manager"
}

variable "manager_machine_type" {
    description = "The Compute Engine machine type to be used for the management node [note: must be an x86_64 or AMD machine type]"
    type        = string
}

variable "manager_name_prefix" {
    description = "The name prefix for the management node instance, the full instance name will be this prefix followed by node number"
    type        = string
}

variable "manager_scopes" {
    description = "The set of access scopes for management node instance"
    default     = [ "cloud-platform" ]
    type = set(string)
}

variable "project_id" {
    description = "The GCP project ID"
    type        = string
}

variable "region" {
    description = "The GCP region where the cluster resides"
    type = string
}

variable "service_account_emails" {
    description = "A map with keys: 'compute', 'login', 'manager' that map to the service account to be used by the respective nodes"
    type        = map(string)
}

variable "subnetwork" {
    description = "Subnetwork to deploy to"
    type        = string
}
