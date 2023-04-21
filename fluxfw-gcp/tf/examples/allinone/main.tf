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

module "cluster" {
    source = "github.com/GoogleCloudPlatform/scientific-computing-examples.git//fluxfw-gcp/tf?ref=openmpi"

    project_id           = var.project_id
    region               = var.region
    
    service_account_emails = {
        manager = data.google_compute_default_service_account.default.email
        login   = data.google_compute_default_service_account.default.email
        compute = data.google_compute_default_service_account.default.email
    }
    
    subnetwork           = module.network.subnets_self_links[0]
    cluster_storage      = {
        mountpoint = "/home"
        share      = "${module.nfs_server_instance.instances_details.0.network_interface.0.network_ip}:/var/nfs/home"
    }

    manager_name_prefix  = var.manager_name_prefix
    manager_machine_type = var.manager_machine_type
    manager_scopes       = var.manager_scopes

    login_node_specs     = var.login_node_specs
    login_scopes         = var.login_scopes

    compute_node_specs   = var.compute_node_specs
    compute_scopes       = var.compute_scopes
}
