/**
 * Copyright 2026 Google LLC
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

data "google_project" "this" {
  project_id = var.project_id
}

data "google_storage_bucket" "existing_bucket" {
  name = var.existing_bucket_name
}

resource "google_storage_bucket_object" "infra-env-file" {
  name   = "config/variables-infra.env"
  bucket = var.existing_bucket_name
  content = join("\n", [
    "_PROJECT_ID=${var.project_id}",
    "_REGION=${var.region}",
    "_CLOUD_BUCKET_NAME=${var.existing_bucket_name}",
    "_DEPLOYMENT_NAME=${var.deployment_name}",
    "_PUBSUB_TOPIC=${var.pubsub_topic}",
    "_MOUNT_PATH=${var.mount_path}",
    "_SERVICE_ACCOUNT_EMAIL=${var.service_account_email}",
    "_LOCATION=${var.location}",
    "_BASE_URL=${var.base_url}",
    "_COLLECTION=${var.collection}",
    "_ENGINE=${var.engine_id}",
    "_ASSISTANT=${var.assistant_id}",
  ])
}

