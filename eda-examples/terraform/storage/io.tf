#
# Copyright 2020 Google LLC
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

variable "zone" {
  default = "us-central1-f"
}

variable "network" {
  default = "default"
}

output "tools-volume-id" {
  value = google_filestore_instance.tools.id
}
output "tools-volume-ip-addresses" {
  value = google_filestore_instance.tools.networks[0].ip_addresses
}

output "home-volume-id" {
  value = google_filestore_instance.home.id
}
output "home-volume-ip-addresses" {
  value = google_filestore_instance.home.networks[0].ip_addresses
}
