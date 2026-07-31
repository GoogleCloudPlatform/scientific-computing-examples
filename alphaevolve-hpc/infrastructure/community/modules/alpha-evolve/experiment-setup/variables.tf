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


variable "project_id" {
  description = "The GCP project ID."
  type        = string
}

variable "user_experiment_name" {
  description = "The name of the user experiment."
  type        = string
}

variable "bucket_name" {
  description = "Target GCS bucket name where the .env file will be stored."
  type        = string
}

variable "object_path" {
  description = "GCS object path (e.g., 'config/variables-infra.env' or 'experiment-1/variables.env')."
  type        = string
}



variable "env_vars" {
  description = "Key-value map of environment variables to dynamically write into the .env file. Also used for validation of experiment settings."
  type        = map(string)
  default     = {}

  validation {
    condition = lookup(var.env_vars, "_USER_EXPERIMENT_NAME", "") == "" || (
      !can(regex("_", lookup(var.env_vars, "_USER_EXPERIMENT_NAME", ""))) &&
      length(lookup(var.env_vars, "_USER_EXPERIMENT_NAME", "")) <= 25
    )
    error_message = "user_experiment_name cannot contain underscores and its length cannot exceed 25 characters."
  }

  validation {
    condition     = lookup(var.env_vars, "_EVALUATION_MODE", "") == "" || lookup(var.env_vars, "_EVALUATION_MODE", "") == "batch"
    error_message = "Invalid evaluation_mode. Only 'batch' mode is supported."
  }

  validation {
    condition     = lookup(var.env_vars, "_EVALUATION_PROVISIONING_MODEL", "") == "" || contains(["STANDARD", "SPOT", "FLEX_START"], lookup(var.env_vars, "_EVALUATION_PROVISIONING_MODEL", ""))
    error_message = "Invalid evaluation_provisioning_model. Valid values are 'STANDARD', 'SPOT', 'FLEX_START'."
  }

  validation {
    condition     = lookup(var.env_vars, "_EVALUATION_PROVISIONING_MODEL", "") != "FLEX_START" || can(regex("^(g2|g4|a2|a3|a4|a4x|n1|h4d)-", lookup(var.env_vars, "_EVALUATION_MACHINE_TYPE", "")))
    error_message = "DWS FLEX_START requires GPU accelerator-enabled VM or H4D instances (supported: G2, G4, A2, A3, A4, A4x, N1, H4D)."
  }

  validation {
    condition = !can(regex("^n1-", lookup(var.env_vars, "_EVALUATION_MACHINE_TYPE", ""))) || (
      lookup(var.env_vars, "_ACCELERATOR_COUNT", "") != "" && can(regex("^[1-9][0-9]*$", lookup(var.env_vars, "_ACCELERATOR_COUNT", ""))) &&
      contains(["nvidia-tesla-t4", "nvidia-tesla-p4", "nvidia-tesla-v100", "nvidia-tesla-p100"], lookup(var.env_vars, "_ACCELERATOR_TYPE", ""))
    )
    error_message = "N1 machine types require a positive accelerator_count and valid accelerator_type (t4, p4, v100, p100)."
  }

  validation {
    condition = lookup(var.env_vars, "_MAX_DURATION", "") == "" || (
      can(regex("^[1-9][0-9]*$", lookup(var.env_vars, "_MAX_DURATION", ""))) &&
      tonumber(lookup(var.env_vars, "_MAX_DURATION", "")) >= 1 &&
      tonumber(lookup(var.env_vars, "_MAX_DURATION", "")) <= 24
    )
    error_message = "max_duration must be an integer hour between 1 and 24 inclusive."
  }

  validation {
    condition = lookup(var.env_vars, "_IDLE_TIMEOUT", "") == "" || (
      can(regex("^[1-9][0-9]*$", lookup(var.env_vars, "_IDLE_TIMEOUT", ""))) &&
      tonumber(lookup(var.env_vars, "_IDLE_TIMEOUT", "")) >= 1
    )
    error_message = "idle_timeout must be an integer hour greater than or equal to 1."
  }

  validation {
    condition = lookup(var.env_vars, "_IDLE_TIMEOUT", "") == "" || (
      tonumber(lookup(var.env_vars, "_IDLE_TIMEOUT", "")) < tonumber(coalesce(lookup(var.env_vars, "_MAX_DURATION", ""), "6"))
    )
    error_message = "idle_timeout must be strictly less than max_duration."
  }

  validation {
    condition = lookup(var.env_vars, "_MODEL", "") == "" || (
      length(split(",", lookup(var.env_vars, "_MODEL", ""))) <= 2 &&
      length(split(",", lookup(var.env_vars, "_MODEL", ""))) > 0 &&
      alltrue([
        for item in split(",", lookup(var.env_vars, "_MODEL", "")) :
        contains(["GEMINI_V2P5_FLASH", "GEMINI_V2P5_PRO", "GEMINI_V3P0_FLASH_PREVIEW", "GEMINI_V3P1_PRO_PREVIEW", "GEMINI_V3P5_FLASH"], trimspace(split(":", item)[0])) &&
        (length(split(":", item)) == 1 || (can(regex("^(0(\\.[0-9]+)?|1(\\.0+)?|\\.[0-9]+)$", trimspace(split(":", item)[1])))))
      ])
    )
    error_message = "Model parameter is invalid. At most two models can be specified with weight 0..1, and must be in allowed GEMINI list."
  }
}
