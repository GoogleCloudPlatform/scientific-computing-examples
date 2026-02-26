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


resource "google_pubsub_topic" "main" {
  # Required arguments
  name    = var.topic_name
  project = var.project_id

  # Optional but common arguments
  labels = var.labels

  # Optional: Define a message storage policy to constrain where messages
  # are stored. For example, to keep data within the EU.
  # The allowed_persistence_regions list should not be empty.
  message_storage_policy {
    allowed_persistence_regions = var.allowed_persistence_regions
  }

  # Optional: Set up a schema for message validation.
  # Requires a separate google_pubsub_schema resource.
  # schema_settings {
  #   schema   = "projects/my-project/schemas/my-schema"
  #   encoding = "JSON"
  # }
}