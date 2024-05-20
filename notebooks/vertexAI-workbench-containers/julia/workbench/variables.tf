/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


variable "workbench_instance_name" {
  description = "Instance name for Vertex AI Workbench Instance"
  type = string
  default = "workbench-instance"
}
variable "workbench_instance_location" {
  description = "Location for Vertex AI Workbench Instance"
  default = "us-central1-a"
  type = string
}

variable "workbench_instance_machine_type" {
  description = "Machine Type for Vertex AI Workbench Instance"
  default = "n1-standard-16" 
  type = string
}

variable "my_container_image_xyz"{
  description = "Container Image Name"
  type = string
}