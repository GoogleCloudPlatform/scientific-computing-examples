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

variable "compute_node_specs" {
    description = "A JSON encoded list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the compute node instances to create"
    type        = string
}

variable "family" {
    description = "The source image family prefix to use"
    type        = string
    default     = "flux-fw-manager"
}

variable "login_node_specs" {
    description = "A JSON encoded list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the login node instances to create"
    type        = string
}

variable "machine_type" {
    description = "The Compute Engine machine type to be used for the management node"
    type        = string
}

variable "name_prefix" {
    description = "The name prefix for the management node instance, the full management node name will be this prefix followed by a node number"
    type        = string
}

variable "nfs_mounts" {
    description = "A map with keys 'share' and 'mountpoint' describing an NFS export and its intended mount point"
    type        = map(string)
    default     = null
}

variable "project_id" {
    description = "The GCP project ID"
    type        = string
}

variable "region" {
    description = "The GCP region where the cluster resides"
    type        = string
}

variable "service_account" {
    description = "The GCP service account used by the management node"
    type        = object({
        email  = string
        scopes = set(string)
    })
}

variable "subnetwork" {
    description = "Subnetwork to deploy to"
    type        = string
}
