# Flux Framework Basic Example - Storage Deployment

This deployment creates a share /home directory for the cluster nodes and exports it via NFS.

TODO: support the ability to create additional shared directories for other purposes, e.g., Spack installs
TODO: support the creation of other storage models, e.g., parallel filesystems and/or object storeage

## Usage

Execute all `terraform` commands from the `storage/` directory. 

- Use the `-chdir=` flag to select the desired storage deployment 
- Use the `-state=` flag to save Terraform state in the `storage/` directory for use by other components in the system. 

This component depends on the state of the [network]() component for the correct values of its project field.

[Note: a production deployment would use a GCS bucket to manage remote state]

Choose one of the storage options below and execute the associated commands to deploy the selected storage provider

### Filestore

This version of the component creates a Cloud Filestore instance that exports a directory named /home. Each cluster node
will mount this directory over its own /home directory at boot time.

#### Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| name | The filestore instance name | string | n/a | yes |
| share_name | Name of the directory being shared | string | n/a | yes |
| tier | The Cloud Filestore TIER to configure | string | STANDARD | no |

Initialize the component with the command:

```bash
terraform -chdir=filestore init
```

Deploy the storage with the command:

```bash
terraform -chdir=filestore apply -var name=fluxstore -var share_name=home -state $PWD/terraform.tfstate
```

## Outputs

| Name | Description |
|------|-------------|
| cluster_storage | A map with keys: 'share' and 'mountpoint' whose values are the IP address/directory of the NFS export and the intended cluster node mountpoint |

| Name | Description |
|------|-------------|
