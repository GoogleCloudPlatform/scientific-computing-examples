# Flux Framework Login Node Module

This submodule is part of the `fluxfw-gcp` module. It creates an instance template for Flux
login nodes and one or more login node instances based on that template. 

Some of the information required to configure the login node at run time is passed to it via metatdata.
That information includes:

- `flux-manager` the hostname of the flux management node
- `nfs-mounts` the NFS exported filesystems to be mounted by the login node

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| machine_arch | The instruction set architecture, ARM64 or x86_64, used by the login node | string | n/a | yes |
| machine_type | The Compute Engine machine type to be used for the login node | string | n/a | yes |
| manager | The hostname of the Flux cluster management node | string | n/a | yes |
| name_prefix | The name prefix for the login node instances, the full instances names will be this prefix followed by a node number | string | n/a | yes |
| nfs_mounts | A map with keys 'share' and 'mountpoint' describing an NFS export and its intended mount point | map(string) | {} | no |
| num_instances | The number of login node instances to create | number | 1 | no |
| project_id | The GCP project ID | string | n/a | yes |
| region | The GCP region where the cluster resides | string | n/a | yes |
| service_account | The GCP service account used by the login node | object({email = string, scopes = set(string)}) | n/a | yes |
| subnetwork | Subnetwork to deploy to  | string | n/a | yes |

## Requirements
