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
}

variable "compute_scopes" {
    type = set(string)
}

variable "login_node_specs" {
    type = list(object({
       name_prefix  = string
       machine_arch = string
       machine_type = string
       instances    = number
       properties   = set(string)
       boot_script  = string
    }))
}

variable "login_scopes" {
    type = set(string)
}

variable "manager_machine_type" {
    type = string
}

variable "manager_name_prefix" {
    type = string
}

variable "manager_scopes" {
    type = set(string)
}
