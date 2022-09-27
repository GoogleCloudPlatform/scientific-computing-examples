# Flux Framework Basic Example - Cluster Deployment

This deployment uses the [Flux Framework Cluster Module]() to bring together the remote state from the other deployments
in this example with the Flux Framework images built with Cloud Build to instantiate a cluster of Compute Engine instances
with attached NVIDIA GPUs managed by the Flux Framework resource job management software.

# Usage

Initialize the deployment with the command:

```bash
terraform init
```

Make a copy of the `gpu.tfvars.example` file:

```bash
cp gpu.tfvars.example gpu.tfvars
```

Modify the gpu.tfvars to specify the desired configuration. For this example only one instance with 
a single GPU attached is required. Feel free, however, to add additional nodes and/or additional GPUs
up to your available quota.

Note that many of the module variables receive their values from the remote state of other components.

Deploy the cluster with the command:

```bash
terraform apply -var-file gpu.tfvars
```

### Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| cluster_storage | A map with keys 'share' and 'mountpoint' describing an NFS export and its desired mount point | map(string) | n/a | yes |
| compute_node_specs | A list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the compute node instances to create | list(maps(string)) | n/a | yes |
| compute_scopes | The set of access scopes for compute node instances | set(string) | [ "cloud-platform" ] | yes |
| login_node_specs | A list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', `gpu_count`, `gpu_type` and 'instances' which describe the login node instances to create | list(map(string)) | n/a | yes |
| login_scopes | The set of access scopes for login node instances | set(string) | [ "cloud-platform" ] | yes |
| manager_machine_type | The Compute Engine machine type to be used for the management node, not must be an x86_64 or AMD machine type | string | n/a | yes |
| manager_name_prefix | The name prefix for the management node instance, the full instance name will be this prefix followed by node number | string | n/a | yes |
| manager_scopes | The set of access scopes for management node instance | set(string) | [ "cloud-platform" ] | yes |
| project_id | The GCP project ID | string | n/a | yes |
| region | The GCP region where the cluster resides | string | n/a | yes |
| service_account_emails | A map with keys: 'compute', 'login', 'manager' that map to the service account to be used by the respective nodes | map(string) | n/a | yes |
| subnetwork | Subnetwork to deploy to | string | n/a | yes |

# Example Code

Once the `terraform apply` command completes you can log into your cluster using the command:

```bash
gcloud compute ssh gpuex-login-001
```

While the cluster `manager` and `login` nodes are up the GPU compute node may take up to ten minutes to finish installing the NVIDIA drivers
and runtime. Check the state of the compute node with the command:

```bash
flux resource list
```

When the compute node is ready you will see output that looks like:

```bash
     STATE PROPERTIES NNODES   NCORES    NGPUS NODELIST
      free x86-64,e2       1        2        0 gpuex-login-001
      free n1,x86-64       1        4        1 gpuex-compute-a-001
 allocated                 0        0        0
      down                 0        0        0
```

Once the compute node is ready you can allocate it with the command:

```bash
flux mini alloc -N1 -c4 -g1
```

Flux will allocate the node and give you a new shell on it. Now you can start working with the GPU attached to it. This 
example will use the [Julia](http://julialang.org) programming language.
