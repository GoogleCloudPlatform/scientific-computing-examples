# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "project_id" {
  description = "The GCP project ID where the Pub/Sub topic will be created."
  type        = string
  # No default value is set, ensuring this is provided by the user.
}

variable "topic_name" {
  description = "The name of the Pub/Sub topic."
  type        = string
  # A default name is provided for ease of use in testing.
  default = "my-example-topic"
}

variable "labels" {
  description = "A map of labels to apply to the Pub/Sub topic."
  type        = map(string)
  default     = {
    "environment" = "development"
    "managed-by"  = "terraform"
  }
}

variable "allowed_persistence_regions" {
  description = "A list of GCP regions where messages are allowed to be stored. e.g., ['europe-west1', 'europe-west4']."
  type        = list(string)
  # Default is an empty list, which means the policy is not applied by default.
  # Google's default behavior (global storage) will be used.
  default = []
}