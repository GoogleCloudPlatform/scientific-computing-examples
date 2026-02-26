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


resource "google_logging_project_sink" "main" {
  name = var.sink_name

  # For GCS: storage.googleapis.com/[BUCKET_NAME]
  # For Pub/Sub: pubsub.googleapis.com/projects/[PROJECT_ID]/topics/[TOPIC_NAME]
  # For BigQuery: bigquery.googleapis.com/projects/[PROJECT_ID]/datasets/[DATASET_ID]
  destination = "pubsub.googleapis.com/${var.topic_id}"

  # A filter is critical for selecting which logs to export.
  # This example exports all logs with a severity of ERROR or higher.
  filter = var.log_filter

  # Using a unique writer identity is a security best practice.
  # It creates a unique service account for this sink.
  unique_writer_identity = true
}

data "google_project" "project" {}

resource "google_pubsub_topic_iam_member" "publisher_binding" {
  project = var.project_id
  topic   = var.topic_name
  
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-logging.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "subscriber_binding" {
  project      = var.project_id
  subscription = var.subscription_name
  
  role   = "roles/pubsub.subscriber"
  member = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}