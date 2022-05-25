# Flux Framework Basic Example - Cluster Deployment

This deployment uses the [Flux Framework Cluster Module]() to bring together the remote state from the foundation deployment
with the Flux Framework images built with Cloud Build to instantiate a cluster node Compute Engine instances managed by the
Flux Framework resource job management software.

# Usage

Initialize the deployment with the command:

```bash
terraform init
```

Make a copy of the `basic.tfvars.example` file:

```bash
cp basic.tfvars.example basic.tfvars
```

Modify the basic.tfvars to specify the desired configuration. For example you may want more than
one login node, you probably want more than one compute node, you may want a different machine_type, 
and/or you may want to add another node pool, e.g., with name_prefix "gffw-compute-b" for nodes
with the ARM64 architecture.

Note that many of the module variables receive their values from the remote state of other components.

Deploy the cluster with the command:

```bash
terraform apply -var-file basic.tfvars
```

### Inputs

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
