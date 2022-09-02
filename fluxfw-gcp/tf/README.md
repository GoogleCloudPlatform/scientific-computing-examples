# Flux Framework Cluster Module

This module handles the deployment of Flux as the native resource manager on a cluster of GCP compute instances.

It creates:

- a single `management node`
- one or more `login nodes`
- one or more `compute nodes`

submodules are provided for creating the components. See the [modules]() directory for the individual submodules 
usage.

## Usage

You can go the the examples directory, however the usage of this module could be like this in your own main.tf file

```hcl
module "cluster" {
    source = "PATH TO FLUXFW-GCP REPO"

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
```

where Terraform _remote state_ references are used to supply the project/region, IAM, network, and storage values.

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| cluster_storage | A map with keys 'share' and 'mountpoint' describing an NFS export and its desired mount point | map(string) | n/a | yes |
| compute_node_specs | A list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the compute node instances to create | list(maps(string)) | n/a | yes |
| compute_scopes | The set of access scopes for compute node instances | set(string) | [ "cloud-platform" ] | yes |
| login_node_specs | A list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the login node instances to create | list(map(string)) | n/a | yes |
| login_scopes | The set of access scopes for login node instances | set(string) | [ "cloud-platform" ] | yes |
| manager_machine_type | The Compute Engine machine type to be used for the management node, not must be an x86_64 or AMD machine type | string | n/a | yes |
| manager_name_prefix | The name prefix for the management node instance, the full instance name will be this prefix followed by node number | string | n/a | yes |
| manager_scopes | The set of access scopes for management node instance | set(string) | [ "cloud-platform" ] | yes |
| project_id | The GCP project ID | string | n/a | yes |
| region | The GCP region where the cluster resides | string | n/a | yes |
| service_account_emails | A map with keys: 'compute', 'login', 'manager' that map to the service account to be used by the respective nodes | map(string) | n/a | yes |
| subnetwork | Subnetwork to deploy to | string | n/a | yes |

## Outputs

## Requirements
