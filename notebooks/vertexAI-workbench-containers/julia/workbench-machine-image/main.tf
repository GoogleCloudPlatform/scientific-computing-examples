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

resource "google_workbench_instance" "instance" {
  name = var.workbench_instance_name
  location = var.workbench_instance_location
  gce_setup {
    machine_type = var.workbench_instance_machine_type
    vm_image {
      project      = var.image_project
      family       = var.image_family
    }
  }
}
