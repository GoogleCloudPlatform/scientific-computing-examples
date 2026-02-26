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
  description = "The GCP project ID where the logging sink will be created."
  type        = string
  # No default value - this should be provided by the user.
}

variable "topic_id" {
  description = "The fully qualified pubsub topic topic id."
  type        = string
  default     = ""
}

variable "topic_name" {
  description = "The pubsub topic to bind to."
  type        = string
  default     = ""
}

variable "subscription_name" {
  description = "The pubsub subscription to bind to."
  type        = string
  default     = ""
}

variable "sink_name" {
  description = "The name of the logging sink."
  type        = string
  default     = "gcs-error-log-export-sink"
}

variable "log_filter" {
  description = "The filter for the logs to be exported by the sink."
  type        = string
  # This default exports all logs at ERROR or higher severity, which is a common use case.
  default = "severity >= ERROR"
}