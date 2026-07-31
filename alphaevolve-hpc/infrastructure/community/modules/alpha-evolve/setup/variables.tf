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

variable "stage" {
  description = "Execution stage: 'infra' (baseline setup & Discovery Engine) or 'experiment' (experiment metadata & env file)."
  type        = string
  validation {
    condition     = contains(["infra", "experiment"], var.stage)
    error_message = "stage must be one of: 'infra', 'experiment'."
  }
}

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "bucket_name" {
  description = "GCS bucket name for configuration storage."
  type        = string
}

variable "env_vars" {
  description = "Map of environment variables written into the GCS .env configuration file."
  type        = map(string)
  default     = {}
}

variable "region" {
  description = "Optional GCP region."
  type        = string
  default     = null
}

variable "deployment_name" {
  description = "Optional infrastructure deployment name."
  type        = string
  default     = null
}

variable "object_path" {
  description = "Optional custom GCS object path for the .env file. Defaults based on stage if null."
  type        = string
  default     = null
}

variable "user_experiment_name" {
  description = "Optional name of the user experiment (required when stage is 'experiment')."
  type        = string
  default     = null
}

variable "create_discovery_engine" {
  description = "Enable Discovery Engine Assistant API calls during infra stage."
  type        = bool
  default     = true
}

variable "location" {
  description = "Discovery Engine location."
  type        = string
  default     = "global"
}

variable "base_url" {
  description = "Base URL for Discovery Engine REST API."
  type        = string
  default     = "discoveryengine.googleapis.com"
}

variable "collection" {
  description = "Discovery Engine collection identifier."
  type        = string
  default     = "default_collection"
}

variable "engine_id" {
  description = "Discovery Engine engine ID."
  type        = string
  default     = null
}

variable "assistant_id" {
  description = "Discovery Engine assistant ID."
  type        = string
  default     = "default_assistant"
}

variable "module_instance_id" {
  description = "Unique ID of this module instance."
  type        = string
  default     = "alpha-evolve-setup"
}

variable "triggers" {
  description = "Map of arbitrary strings to force re-execution."
  type        = map(string)
  default     = {}
}
