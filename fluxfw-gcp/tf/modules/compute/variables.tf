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

variable "automatic_restart" {
  type        = bool
  description = "(Optional) Specifies whether the instance should be automatically restarted if it is terminated by Compute Engine (not terminated by a user)."
  default     = true
}

variable "boot_script" {
    description = "(Optional) the name of a file containing a script to be executed on compute nodes at boot time"
    type        = string
    default     = null
}

variable "compact_placement" {
    description = "(Optional) a boolean which determines whether a set of compute nodes has a compact placement resource policy attached to them."
    type        = bool
    default     = false
}

variable "gpu" {
    description = "The type and count of GPU(s) to attach to a compute node"
    type        = object({
        type  = string
        count = number
    })
    default     = null
}

variable "machine_arch" {
    description = "The instruction set architecture, ARM64 or x86_64, used by the compute node"
    type        = string
}

variable "machine_type" {
    description = "The Compute Engine machine type to be used for the compute node"
    type        = string
}

variable "manager" {
    description = "The hostname of the Flux cluster management node"
    type        = string
}

variable "name_prefix" {
    description = "The name prefix for the compute node instances, the full instances names will be this prefix followed by a node number"
    type        = string
}

variable "nfs_mounts" {
    description = "A map with keys 'share' and 'mountpoint' describing an NFS export and its intended mount point"
    type        = map(string)
    default     = {}
}

variable "num_instances" {
    description = "The number of compute node instances to create"
    type        = number
    default     = 1
}

variable "on_host_maintenance" {
  type        = string
  description = "Instance availability Policy"
  default     = "MIGRATE"
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
    description = "The GCP service account used by the compute node"
    type        = object({
        email  = string
        scopes = set(string)
    })
}

variable "subnetwork" {
    description = "Subnetwork to deploy to"
    type        = string
}
