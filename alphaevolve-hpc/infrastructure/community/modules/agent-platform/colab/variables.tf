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
  description = "GCP project ID."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be 6 to 30 characters long, start with a lowercase letter, end with a letter or digit, and contain only lowercase letters, digits, and hyphens."
  }
}

variable "region" {
  description = "GCP region where the Colab runtime and template will be provisioned."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.region))
    error_message = "Region must be a valid GCP region identifier (e.g. 'us-central1', 'europe-west1')."
  }
}

variable "deployment_name" {
  description = "Deployment name used as prefix for runtime template and runtime IDs."
  type        = string
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+$", var.deployment_name))
    error_message = "deployment_name must be a non-empty string containing only alphanumeric characters, hyphens, or underscores."
  }
}

variable "mount_gcs_bucket" {
  description = "Optional GCS bucket name to automatically mount to the VM via gcsfuse on startup."
  type        = string
  default     = null
  validation {
    condition     = var.mount_gcs_bucket == null || var.mount_gcs_bucket == "" || can(regex("^[a-z0-9_.-]{3,63}$", var.mount_gcs_bucket))
    error_message = "GCS bucket name must be 3 to 63 characters long and contain only lowercase letters, numbers, hyphens, underscores, or dots."
  }
}

variable "mount_path" {
  description = "Local VM directory path where mount_gcs_bucket will be mounted."
  type        = string
  default     = "/home/jupyter/gcs"
}

variable "environment_variables" {
  description = "Map of environment variables to inject into the Colab runtime environment."
  type        = map(string)
  default     = {}
}


variable "post_startup_script_behavior" {
  description = "Execution behavior for post_startup_script ('RUN_ONCE', 'RUN_EVERY_START', 'DOWNLOAD_AND_RUN_EVERY_START')."
  type        = string
  default     = "DOWNLOAD_AND_RUN_EVERY_START"

  validation {
    condition     = contains(["RUN_ONCE", "RUN_EVERY_START", "DOWNLOAD_AND_RUN_EVERY_START"], var.post_startup_script_behavior)
    error_message = "post_startup_script_behavior must be one of: RUN_ONCE, RUN_EVERY_START, DOWNLOAD_AND_RUN_EVERY_START."
  }
}

variable "colab_machine_type" {
  description = "Machine type for the Colab runtime VM (e.g., 'n2-standard-4')."
  type        = string
  default     = "n2-standard-4"
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.colab_machine_type))
    error_message = "colab_machine_type must be a valid GCP machine type string (e.g. 'n2-standard-4')."
  }
}

variable "accelerator_type" {
  description = "Optional GPU accelerator type (e.g. 'NVIDIA_TESLA_T4', 'NVIDIA_L4')."
  type        = string
  default     = null
}

variable "accelerator_count" {
  description = "Optional number of GPU accelerators to attach to the VM."
  type        = number
  default     = null
}

variable "disk_type" {
  description = "Persistent disk type for the Colab runtime VM ('pd-standard', 'pd-ssd', 'pd-balanced')."
  type        = string
  default     = "pd-balanced"
}

variable "disk_size_gb" {
  description = "Size of the user persistent disk in GB."
  type        = number
  default     = 20
}

variable "enable_internet_access" {
  description = "Enable internet access for the Colab runtime VM."
  type        = bool
  default     = true
}

variable "network" {
  description = "Optional VPC network resource name or ID for private networking."
  type        = string
  default     = null
}

variable "subnetwork" {
  description = "Optional VPC subnet resource name or ID for private networking."
  type        = string
  default     = null
}

variable "idle_timeout" {
  description = "Optional idle timeout duration for automatic shutdown (e.g. '14400s' for 4 hours)."
  type        = string
  default     = null
}

variable "runtime_user" {
  description = "The user email for the Colab runtime. Defaults to active gcloud/Terraform user if not set."
  type        = string
  default     = null
}

variable "module_instance_id" {
  description = "Unique ID of this module instance (automatically populated by gcluster)."
  type        = string
  default     = "agent-platform-colab"
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+$", var.module_instance_id))
    error_message = "module_instance_id must be a non-empty string containing only alphanumeric characters, hyphens, or underscores."
  }
}

variable "triggers" {
  description = "A map of arbitrary strings or outputs that, when changed, force this module to re-run."
  type        = map(string)
  default     = {}
}

variable "staged_files" {
  description = "List of arbitrary files or objects to stage on the attached GCS bucket (or specified bucket_name)."
  type = list(object({
    object_path = string
    source_path = optional(string)
    content     = optional(string)
    bucket_name = optional(string)
  }))
  default = []

  validation {
    condition = alltrue([
      for f in var.staged_files : (
        f.object_path != null && f.object_path != "" &&
        ((f.source_path != null) != (f.content != null))
      )
    ])
    error_message = "Each staged file entry must specify a non-empty object_path and exactly one of source_path or content."
  }
}

