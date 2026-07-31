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

output "project_number" {
  description = "Numeric GCP Project Number."
  value       = data.google_project.this.number
}

output "object_path" {
  description = "GCS object path of the written environment file."
  value       = google_storage_bucket_object.env-file.name
}

output "engine_id" {
  description = "Discovery Engine ID (if created)."
  value       = var.create_discovery_engine && var.stage == "infra" ? var.engine_id : null
}

output "assistant_id" {
  description = "Discovery Engine Assistant ID (if created)."
  value       = var.create_discovery_engine && var.stage == "infra" ? var.assistant_id : null
}
