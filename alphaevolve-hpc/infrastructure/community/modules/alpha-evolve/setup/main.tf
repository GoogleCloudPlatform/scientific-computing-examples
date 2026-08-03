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

data "google_client_config" "default" {}

data "google_project" "this" {
  project_id = var.project_id
}

# --- Stage 1: Discovery Engine Provisioning (Infra Stage) ---
data "http" "create_engine" {
  count  = var.stage == "infra" && var.create_discovery_engine ? 1 : 0
  url    = "https://${var.base_url}/v1alpha/projects/${var.project_id}/locations/${var.location}/collections/${var.collection}/engines?engineId=${var.engine_id}"
  method = "POST"

  request_timeout_ms = 60000

  retry {
    attempts     = 5
    min_delay_ms = 2000
    max_delay_ms = 10000
  }

  request_headers = {
    "Content-Type"        = "application/json"
    "Authorization"       = "Bearer ${data.google_client_config.default.access_token}"
    "x-goog-user-project" = var.project_id
  }

  request_body = jsonencode({
    display_name   = var.engine_id
    data_store_ids = []
    solution_type  = "SOLUTION_TYPE_GENERATIVE_CHAT"
  })
}

data "http" "create_assistant" {
  count      = var.stage == "infra" && var.create_discovery_engine ? 1 : 0
  depends_on = [data.http.create_engine]
  url        = "https://${var.base_url}/v1alpha/projects/${var.project_id}/locations/${var.location}/collections/${var.collection}/engines/${var.engine_id}/assistants?assistantId=${var.assistant_id}"
  method     = "POST"

  request_timeout_ms = 60000

  retry {
    attempts     = 5
    min_delay_ms = 2000
    max_delay_ms = 10000
  }

  request_headers = {
    "Content-Type"        = "application/json"
    "Authorization"       = "Bearer ${data.google_client_config.default.access_token}"
    "x-goog-user-project" = var.project_id
  }

  request_body = jsonencode({
    display_name       = var.assistant_id
    description        = null
    generation_config  = null
    web_grounding_type = "WEB_GROUNDING_TYPE_UNSPECIFIED"
    enabled_actions    = null
    customer_policy    = null
  })
}

data "http" "test_assistant" {
  count      = var.stage == "infra" && var.create_discovery_engine ? 1 : 0
  depends_on = [data.http.create_assistant]
  url        = "https://${var.base_url}/v1alpha/projects/${var.project_id}/locations/${var.location}/collections/${var.collection}/engines/${var.engine_id}/assistants/${var.assistant_id}:streamAssist"
  method     = "POST"

  request_timeout_ms = 60000

  retry {
    attempts     = 5
    min_delay_ms = 2000
    max_delay_ms = 10000
  }

  request_headers = {
    "Content-Type"        = "application/json"
    "Authorization"       = "Bearer ${data.google_client_config.default.access_token}"
    "x-goog-user-project" = var.project_id
  }

  request_body = jsonencode({
    query              = { text = "starting alpha evolve query" }
    assistSkippingMode = "REQUEST_ASSIST"
  })

  lifecycle {
    postcondition {
      condition     = self.status_code == 200
      error_message = "AlphaEvolve API validation failed. Please check permissions. Status code: ${self.status_code}"
    }
  }
}

# --- Stage 2: Generic Environment File Creation (Infra & Experiment Stages) ---
locals {
  default_object_path   = var.stage == "infra" ? "config/variables-infra.env" : "${var.user_experiment_name}/variables.env"
  effective_object_path = var.object_path != null && var.object_path != "" ? var.object_path : local.default_object_path
}

resource "google_storage_bucket_object" "env-file" {
  name   = local.effective_object_path
  bucket = var.bucket_name
  content = join("\n", [
    for key, value in var.env_vars : "${key}=\"${value}\""
  ])
}

# --- Stage 3: Experiment Project Metadata & Instructions (Experiment Stage) ---
resource "google_compute_project_metadata_item" "experiment-metadata" {
  count   = var.stage == "experiment" && var.user_experiment_name != null && var.user_experiment_name != "" ? 1 : 0
  project = var.project_id
  key     = "${var.user_experiment_name}_USER_EXPERIMENT_NAME"
  value   = var.user_experiment_name
}

locals {
  exp_name = var.user_experiment_name != null ? var.user_experiment_name : ""

  instructions_text = <<-EOT
    set -e

    printf '%b' "
    \033[1;33m====================================================================\033[0m
    \033[1;32m==== How to run your experiment in the Notebook ====\033[0m
    All configurations have been natively saved to GCS under: gs://${var.bucket_name}/${local.exp_name}/

    Please open the Jupyter Notebook and follow these steps under the 'Show how change experiment run' section:

    1. Go to the section: \033[1;36m'Adjust environment variables on the Notebook'\033[0m.
    2. Run the interactive cell: \033[1;36m'Run this cell to specify the experiment...'\033[0m.
    3. Select the option corresponding to: \033[1;36m'${local.exp_name}'\033[0m.
       This will dynamically load all of your GCS environment variables!
    \033[1;33m====================================================================\033[0m
    " > /dev/tty 2>&1 || true
  EOT
}

resource "terraform_data" "show_instructions" {
  count = var.stage == "experiment" && var.user_experiment_name != null && var.user_experiment_name != "" ? 1 : 0
  provisioner "local-exec" {
    command = local.instructions_text
  }
}
