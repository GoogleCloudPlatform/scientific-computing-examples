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

locals {
  container_image_name = "${var.repo_path}/${var.image_name}"
}

resource "null_resource" "build_and_push_image" {
  provisioner "local-exec" {
    command = <<-EOT
    cd ${path.module}
    gcloud builds submit --timeout=3h  --tag ${local.container_image_name} .
    EOT
  }
  depends_on = [ local_file.dockerfile ]
}
resource "local_file" "dockerfile" {
  filename = "${path.module}/Dockerfile"
  content  = var.dockerfile_contents
}
