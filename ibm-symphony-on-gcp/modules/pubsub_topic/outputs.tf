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

output "topic_id" {
  description = "The fully qualified ID of the Pub/Sub topic (projects/PROJECT_ID/topics/TOPIC_NAME)."
  value       = google_pubsub_topic.main.id
}

output "topic_name" {
  description = "The short name of the Pub/Sub topic."
  value       = google_pubsub_topic.main.name
}