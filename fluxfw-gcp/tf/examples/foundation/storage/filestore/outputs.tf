# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

output "cluster_storage" {
    value = {
        share_ip   = resource.google_filestore_instance.instance.networks[0].ip_addresses[0],
        share_name = format("/%s", resource.google_filestore_instance.instance.file_shares[0].name),
        mountpoint = format("/%s", var.share_name)
    }
}
