# Flux Framework Basic Example - IAM Deployment

This deployment creates the Cloud IAM service accounts for use by the Compute Engine cluster instances.
Accounts are created, or assigned, to the compute, login, and management nodes.

## Usage

Execute all `terraform` commands from the `iam/` directory. 

- Use the `-chdir=` flag to select the desired iam deployment 
- Use the `-state=` flag to save Terraform state in the `iam/` directory for use by other components in the system. 

This component depends on the state of the [network]() component for the correct values of its project field.

[Note: a production deployment would use a GCS bucket to manage remote state]

Choose one of the iam options below and execute the associated commands to deploy the selected service accounts

### Default

This version of the component simply uses the same service account, the default compute service account, for each of the
cluster node types.

Initialize the component with the command:

```bash
terraform -chdir=default init
```

Deploy the service accounts with the command:

```bash
terraform -chdir=default apply -state=$PWD/terraform.tfstate
```

## Outputs

| Name | Description |
|------|-------------|
| compute_service_account | The service account for use by compute nodes |
| login_service_account | The service account for use by login nodes |
| management_service_account | The service account for use by management nodes |
