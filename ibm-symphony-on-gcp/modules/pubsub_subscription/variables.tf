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
  description = "The GCP project ID to deploy the resources to."
  type        = string
  # No default value - this should be provided by the user.
}

variable "topic_name" {
  description = "The name of the Pub/Sub topic."
  type        = string
  default     = "example-topic"
}

variable "subscription_name" {
  description = "The name of the Pub/Sub subscription."
  type        = string
  default     = "hf-gce-vm-events-sub"
}

variable "ack_deadline_seconds" {
  description = "The acknowledgment deadline for messages pulled from this subscription."
  type        = number
  default     = 20
}

variable "message_retention_duration" {
  description = "How long to retain unacknowledged messages in the subscription's backlog."
  type        = string
  default     = "604800s" # 7 days
}

variable "subscription_filter" {
  description = "A filter expression for the subscription (e.g., 'attributes.type = \"important\"'). Leave empty for no filter."
  type        = string
  default     = ""
}

variable "labels" {
  description = "A map of labels to apply to the Pub/Sub resources."
  type        = map(string)
  default     = {
    "environment" = "dev"
    "terraform"   = "true"
  }
}