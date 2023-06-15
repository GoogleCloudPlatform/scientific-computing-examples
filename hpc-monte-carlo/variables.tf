#  Copyright 2023 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

variable "project" {
  description = "Cloud zone for resources"
  type        = string
  default = "your-project-id"
}
variable "zone" {
  description = "Cloud zone for resources"
  type        = string
  default = "us-central1-c"
}
variable "region" {
  description = "Cloud region for resources"
  type        = string
  default = "us-central1"
}
variable "name_suffix" {
  description = "String appended to most resources created"
  type        = string
  default = "montecarlo"
}
variable "name_prefix" {
  description = "String prepended to most resources created"
  type        = string
  default = "fsi"
}
