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


resource "google_artifact_registry_repository" "my-repo" {
  location      = var.region
  repository_id = var.repository_id
  description   = var.description
  format        = var.format
  docker_config {
    immutable_tags = var.immutable_tags
  }
}
data "google_project" "project" {
}

locals {
  repo_url = "${google_artifact_registry_repository.my-repo.location}-docker.pkg.dev"
  repo_path = "${local.repo_url}/${data.google_project.project.name}/${google_artifact_registry_repository.my-repo.name}"
}
