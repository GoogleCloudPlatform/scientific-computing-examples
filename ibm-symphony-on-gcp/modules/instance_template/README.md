# Terraform Google Compute Engine Instance Template Module

This module creates a Google Compute Engine instance template.

## Usage

```hcl
module "instance_template" {
  source                  = "./modules/instance_template"
  project_id              = "your-gcp-project-id"
  name_prefix             = "my-instance-template"
  machine_type            = "n2-standard-2"
  region                  = "us-central1"
  service_account_email = "your-service-account@your-project.iam.gserviceaccount.com"
  subnetwork_self_link    = "projects/your-project/regions/us-central1/subnetworks/your-subnetwork"
}
```

## Inputs

| Name                        | Description                                                              | Type          | Default                                               | Required |
| --------------------------- | ------------------------------------------------------------------------ | ------------- | ----------------------------------------------------- | :------: |
| `project_id`                | The GCP project ID.                                                      | `string`      | `null`                                                |   yes    |
| `name_prefix`               | Name prefix for the instance template.                                   | `string`      | n/a                                                   |   yes    |
| `machine_type`              | Machine type to create, e.g. n1-standard-1.                              | `string`      | `"n1-standard-1"`                                     |    no    |
| `min_cpu_platform`          | Specifies a minimum CPU platform.                                        | `string`      | `null`                                                |    no    |
| `can_ip_forward`            | Enable IP forwarding.                                                    | `string`      | `"false"`                                             |    no    |
| `tags`                      | Network tags, provided as a list.                                        | `list(string)`| `[]`                                                  |    no    |
| `labels`                    | Labels, provided as a map.                                               | `map(string)` | `{}`                                                  |    no    |
| `preemptible`               | Allow the instance to be preempted.                                      | `bool`        | `false`                                               |    no    |
| `spot`                      | Provision as a SPOT preemptible instance.                                | `bool`        | `false`                                               |    no    |
| `instance_termination_action`| Action to take when Compute Engine preempts the VM (`STOP` or `DELETE`). | `string`      | `null`                                                |    no    |
| `automatic_restart`         | Specifies whether the instance should be automatically restarted.        | `bool`        | `true`                                                |    no    |
| `on_host_maintenance`       | Instance availability Policy.                                            | `string`      | `"MIGRATE"`                                           |    no    |
| `region`                    | Region where the instance template should be created.                    | `string`      | n/a                                                   |   yes    |
| `advanced_machine_features` | Advanced machine features.                                               | `object`      | n/a                                                   |   yes    |
| `resource_manager_tags`     | A set of key/value resource manager tag pairs to bind to the instances.  | `map(string)` | `{}`                                                  |    no    |
| `source_image`              | Source disk image.                                                       | `string`      | `""`                                                  |    no    |
| `source_image_family`       | Source image family.                                                     | `string`      | `"centos-7"`                                          |    no    |
| `source_image_project`      | Project where the source image comes from.                               | `string`      | `"centos-cloud"`                                      |    no    |
| `disk_size_gb`              | Boot disk size in GB.                                                    | `string`      | `"100"`                                               |    no    |
| `disk_type`                 | Boot disk type.                                                          | `string`      | `"pd-standard"`                                       |    no    |
| `disk_labels`               | Labels to be assigned to boot disk.                                      | `map(string)` | `{}`                                                  |    no    |
| `disk_encryption_key`       | The id of the encryption key to use to encrypt all the disks.            | `string`      | `null`                                                |    no    |
| `auto_delete`               | Whether or not the boot disk should be auto-deleted.                     | `string`      | `"true"`                                              |    no    |
| `disk_resource_manager_tags`| Key/value resource manager tag pairs to bind to the instance disks.      | `map(string)` | `{}`                                                  |    no    |
| `additional_disks`          | List of maps of additional disks.                                        | `list(object)`| `[]`                                                  |    no    |
| `network`                   | The name or self_link of the network to attach this interface to.        | `string`      | `""`                                                  |    no    |
| `nic_type`                  | The type of vNIC to be used on this interface (GVNIC, VIRTIO_NET).       | `string`      | `null`                                                |    no    |
| `subnetwork_self_link`      | The self link of the subnetwork to attach the VM.                        | `string`      | `null`                                                |    no    |
| `network_ip`                | Private IP address to assign to the instance.                            | `string`      | `""`                                                  |    no    |
| `stack_type`                | The stack type for this network interface (IPV4_IPV6 or IPV4_ONLY).      | `string`      | `null`                                                |    no    |
| `additional_networks`       | Additional network interface details.                                    | `list(object)`| `[]`                                                  |    no    |
| `total_egress_bandwidth_tier`| Network bandwidth tier (TIER_1 or DEFAULT).                              | `string`      | `"DEFAULT"`                                           |    no    |
| `startup_script`            | User startup script to run when instances spin up.                       | `string`      | `""`                                                  |    no    |
| `metadata`                  | Metadata, provided as a map.                                             | `map(string)` | `{}`                                                  |    no    |
| `enable_shielded_vm`        | Whether to enable the Shielded VM configuration.                         | `bool`        | `false`                                               |    no    |
| `shielded_instance_config`  | Shielded VM configuration for the instance.                              | `object`      | `{...}`                                               |    no    |
| `enable_confidential_vm`    | Whether to enable the Confidential VM configuration.                     | `bool`        | `false`                                               |    no    |
| `service_account_email`     | Service account to run VMs.                                              | `string`      | n/a                                                   |   yes    |
| `access_config`             | Access configurations for public IPs.                                    | `list(object)`| `[]`                                                  |    no    |
| `ipv6_access_config`        | IPv6 access configurations.                                              | `list(object)`| `[]`                                                  |    no    |
| `gpu`                       | GPU information (type and count).                                        | `object`      | `null`                                                |    no    |
| `alias_ip_range`            | An array of alias IP ranges for this network interface.                  | `object`      | `null`                                                |    no    |
| `max_run_duration`          | The duration in seconds of the instance.                                 | `number`      | `null`                                                |    no    |
| `provisioning_model`        | The provisioning model of the instance.                                  | `string`      | `null`                                                |    no    |
| `reservation_affinity`      | Specifies the reservations that this instance can consume from.          | `object`      | `null`                                                |    no    |

## Outputs

| Name       | Description                               |
| ---------- | ----------------------------------------- |
| `self_link`| Self-link of instance template.           |
| `name`     | Name of instance template.                |
| `tags`     | Tags that will be associated with instance(s). |