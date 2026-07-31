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

resource "google_compute_project_metadata_item" "experiment-metadata" {
  project = var.project_id
  key     = "${var.user_experiment_name}_USER_EXPERIMENT_NAME"
  value   = var.user_experiment_name
}

resource "google_storage_bucket_object" "experiment-env-file" {
  name   = var.object_path
  bucket = var.bucket_name
  content = join("\n", [
    for key, value in var.env_vars : "${key}=\"${value}\""
  ])
}

locals {
  local_exec_command = <<-EOT
    set -e

    printf '%b' "
    \033[1;33m====================================================================\033[0m
    \033[1;32m==== How to run your experiment in the Notebook ====\033[0m
    All configurations have been natively saved to GCS under: gs://${var.bucket_name}/${var.user_experiment_name}/

    Please open the Jupyter Notebook and follow these steps under the 'Show how change experiment run' section:

    1. Go to the section: \033[1;36m'Adjust environment variables on the Notebook'\033[0m.
    2. Run the interactive cell: \033[1;36m'Run this cell to specify the experiment...'\033[0m.
    3. Select the option corresponding to: \033[1;36m'${var.user_experiment_name}'\033[0m.
       This will dynamically load all of your GCS environment variables!
    \033[1;33m====================================================================\033[0m
    " > /dev/tty 2>&1 || true
  EOT
}

resource "terraform_data" "show_instructions" {
  provisioner "local-exec" {
    command = local.local_exec_command
  }
}