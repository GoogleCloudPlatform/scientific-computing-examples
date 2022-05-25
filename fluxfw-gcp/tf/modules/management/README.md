# Flux Framework Management Node Module

This submodule is part of the `fluxfw-gcp` module. It creates an instance template for a Flux management node and uses
it to deploy a management node instance.

Some of the information required to configure the management node at run time is passed to it via metadata. That
information includes:

- `nfs-mounts` the NFS exported filesystems to be mounted by the management node
- `compute-node-specs` the JSON encoded specification of the cluster's compute nodes
- `login-node-specs` the JSON encoded specification of the cluster's login nodes

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| compute_node_specs | A JSON encoded list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the compute node instances to create | string | n/a | yes |
| login_node_specs | A JSON encoded list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the login node instances to create | string | n/a | yes |
| machine_type | The Compute Engine machine type to be used for the management node | string | n/a | yes |
| name_prefix | The name prefix for the management node instance, the full management node name will be this prefix followed by a node number | string | n/a | yes |
| nfs_mounts | A map with keys 'share' and 'mountpoint' describing an NFS export and its intended mount point | map(string) | n/a | yes |
| project_id | The GCP project ID | string | n/a | yes |
| region | The GCP region where the cluster resides | string | n/a | yes |
| service_account | The GCP service account used by the management node | object({ email = string, scopes = set(string) }) | n/a | yes |
| subnetwork | Subnetwork to deploy to | string | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| name | The hostname of the managment node |

## Requirements
