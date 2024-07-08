#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#locals {
#  builder_service_account_roles = [
#    "roles/compute.admin",
#    "roles/compute.instanceAdmin",
#    #"roles/compute.instanceAdmin.v1",
#    "roles/iam.serviceAccountAdmin",
#    "roles/iam.serviceAccountTokenCreator",
#    "roles/iam.serviceAccountUser",
#    "roles/compute.storageAdmin",
#    "roles/logging.logWriter",
#    "roles/monitoring.metricWriter",
#    "roles/iap.tunnelResourceAccessor",
#  ]
#}

#resource "google_service_account" "builder_service_account" {
#  #
#  # Instead of creating a new builder SA, I found a solutions script that used
#  # the following to find the "default" builder SA... is there another way
#  # using data?
#  #
#  # CLOUD_BUILD_ACCOUNT=$(gcloud projects get-iam-policy \
#  #   $PROJECT \
#  #   --filter="(bindings.role:roles/cloudbuild.builds.builder)" \
#  #   --flatten="bindings[].members" \
#  #   --format="value(bindings.members[])")
#  #   
#  account_id   = "builder-service-account"
#  display_name = "builder-service-account"
#}

#resource "google_project_iam_member" "builder_service_account_roles" {
#  for_each = toset(local.builder_service_account_roles)

#  project = data.google_project.project.name
#  member  = "serviceAccount:${google_service_account.builder_service_account.email}"
#  role   = each.value
#}
