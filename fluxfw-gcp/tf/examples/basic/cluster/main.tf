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
    source = "../../.."

    project_id           = data.terraform_remote_state.network.outputs.subnet.project
    region               = data.terraform_remote_state.network.outputs.subnet.region
    
    service_account_emails = {
        manager = data.terraform_remote_state.iam.outputs.management_service_account
        login   = data.terraform_remote_state.iam.outputs.login_service_account
        compute = data.terraform_remote_state.iam.outputs.compute_service_account
    }
    
    subnetwork           = data.terraform_remote_state.network.outputs.subnet.self_link
    cluster_storage      = data.terraform_remote_state.storage.outputs.cluster_storage

    manager_name_prefix  = var.manager_name_prefix
    manager_machine_type = var.manager_machine_type
    manager_scopes       = var.manager_scopes

    login_node_specs     = var.login_node_specs
    login_scopes         = var.login_scopes

    compute_node_specs   = var.compute_node_specs
    compute_scopes       = var.compute_scopes
}
