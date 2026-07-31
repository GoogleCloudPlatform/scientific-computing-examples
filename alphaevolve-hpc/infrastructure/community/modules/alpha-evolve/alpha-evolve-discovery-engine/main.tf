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

data "http" "create_engine" {
  url    = "https://discoveryengine.googleapis.com/v1alpha/projects/${var.project_id}/locations/${var.location}/collections/${var.collection}/engines?engineId=${var.engine_id}"
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
  depends_on = [data.http.create_engine]
  url        = "https://discoveryengine.googleapis.com/v1alpha/projects/${var.project_id}/locations/${var.location}/collections/${var.collection}/engines/${var.engine_id}/assistants?assistantId=${var.assistant_id}"
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
  depends_on = [data.http.create_assistant]
  url        = "https://discoveryengine.googleapis.com/v1alpha/projects/${var.project_id}/locations/${var.location}/collections/${var.collection}/engines/${var.engine_id}/assistants/${var.assistant_id}:streamAssist"
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
