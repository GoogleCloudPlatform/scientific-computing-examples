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

locals {
  rendered_config = var.cloud_build_content != null ? var.cloud_build_content : (
    var.cloud_build_template_path != null ? templatefile(
      var.cloud_build_template_path,
      var.template_vars
    ) : ""
  )

  gcs_staging_flag   = var.gcs_staging_dir != null && var.gcs_staging_dir != "" ? "--gcs-source-staging-dir=\"${var.gcs_staging_dir}\"" : ""
  service_acct_flag  = var.service_account != null && var.service_account != "" ? "--service-account=\"projects/${var.project_id}/serviceAccounts/${var.service_account}\"" : ""
  substitutions_str  = length(var.substitutions) > 0 ? join(",", [for k, v in var.substitutions : "${k}=${v}"]) : ""
  substitutions_flag = local.substitutions_str != "" ? "--substitutions=\"${local.substitutions_str}\"" : ""

  create_script = <<-EOT
    #!/bin/bash
    set -e -o pipefail

    echo "[INFO] Running Cloud Build task..."

    gcloud builds submit "${var.cloud_build_dir}" \
      --config "${local_file.cloud_build_config.filename}" \
      --project="${var.project_id}" \
      ${local.gcs_staging_flag} \
      ${local.service_acct_flag} \
      ${local.substitutions_flag}

    echo "[INFO] Build completed successfully."
  EOT
}

resource "local_file" "cloud_build_config" {
  filename = "${path.module}/cloud-build-local-${var.module_instance_id}.yaml"
  content  = local.rendered_config
}

resource "terraform_data" "build" {
  triggers_replace = {
    config_hash     = local_file.cloud_build_config.content_sha256
    cloud_build_dir = var.cloud_build_dir
    project_id      = var.project_id
    custom_triggers = sha256(jsonencode(var.triggers))
  }

  provisioner "local-exec" {
    command = local.create_script
  }
}
