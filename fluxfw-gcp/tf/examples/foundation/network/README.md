# Flux Framework Basic Example - Network Deployment

This deployment creates a GCP network for use by one or more clusters of Compute Engine instances
composed into an HPC system using the Flux Framework resource job management software.

## Usage

Execute all `terraform` commands from the `network/` directory. 

- Use the `-chdir=` flag to select the desired network deployment 
- Use the `-state=` flag to save Terraform state in the `network/` directory for use by other components in the system. 

[Note: a production deployment would use a GCS bucket to manage remote state]

Choose one of the network options below and execute the associated commands to deploy the selected network

### Default

This option uses your project's `default` network. It is the simplest option since it uses existing resources and
therefore is quick to deploy. However, because the cluster nodes deploy without external IP addresses, they will not
be able to access external resources using this network option.

#### Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| project_id | The GCP project ID | string | n/a | yes |
| region | The GCP region where the network resides | string | n/a | yes |
| subnet_name | Name of the subnetwork to deploy | string | default | no |

Initialize the component with the command:

```bash
terraform -chdir=default init
```

Deploy the network with the command:

```bash
terraform -chdir=default apply -var project_id=<project_id> -var region=<region> -state=$PWD/terraform.tfstate
```

### Zonal

This option creates a new VPC Network for your cluster. The network includes a NAT so that cluster nodes can access
external resources and the firewall rules necessary to enable inter-node communication.

#### Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| network_name | Name of the VPC network | string | n/a | yes |
| project_id | The GCP project ID | string | n/a | yes |
| region | The GCP region where the network resides | string | n/a | yes |
| ssh_source_ranges | List of CIDR ranges from which SSH connections are accepted | list(string) | ["0.0.0.0/0"] | no |
| subnet_ip | CIDR for the network subnet | string | "10.10.0.0./18" | no |

Initialize the component with the command:

```bash
terraform -chdir=zonal init
```

Deploy the network with the command:

```bash
terraform -chdir=zonal apply -var project_id=<project_id> -var region=<region> -var network_name=<network_name> -state=$PWD/terraform.tfstate
```

## Outputs

| Name | Description |
|------|-------------|
| subnet | A map structure with keys: project, region, network, and self_link |
