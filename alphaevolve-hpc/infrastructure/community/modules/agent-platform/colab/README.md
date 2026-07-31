<!--
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Agent Platform Colab Module

Provisions a Vertex AI Colab Enterprise runtime template (`google_colab_runtime_template`) and attached runtime instance (`google_colab_runtime`) using official Google Cloud Terraform provider resources.

---

## Features

- **Automatic GCS Bucket Mounting**: Pass `mount_gcs_bucket = "my-bucket"` to automatically generate and upload a clean `gcsfuse` mounting script to GCS and attach it to the VM startup sequence. Mounted locally at `/home/jupyter/gcs` (or custom `mount_path`).
- **Staged Files**: The module can optionally upload local files or config directories to a GCS bucket, making them available to the runtime VM. Pass `mount_gcs_bucket = "my-bucket"`.
- **Arbitrary File Staging**: Pass `staged_files` to upload local files or inline content strings to the attached GCS bucket (or custom target bucket) prior to launching the Colab runtime template.

---

## Example Usage

### Automated GCS Bucket Mounting & File Staging

```yaml
- group: colab
  modules:
### Automated File Staging

```yaml
- group: colab
  modules:
  - id: agent-platform-colab
    source: ./infrastructure/community/modules/agent-platform/colab
    settings:
      project_id: my-project-id
      region: us-central1
      deployment_name: alpha-evolve-infra
      mount_gcs_bucket: my-data-bucket
      mount_path: /home/jupyter/gcs
      colab_machine_type: n2-standard-4
      staged_files:
        - object_path: config/requirements.txt
          source_path: ./infrastructure/requirements.txt
        - object_path: config/controller-batch.yaml
          source_path: ./infrastructure/batch_configs/controller-batch.yaml
        - object_path: notebook/run_notebook.ipynb
          source_path: ./google_framework/notebook/run_notebook.ipynb
```

### Advanced Usage with GPUs & Custom Environment Variables

```yaml
- group: colab
  modules:
  - id: agent-platform-colab
    source: ./infrastructure/community/modules/agent-platform/colab
    settings:
      project_id: my-project-id
      region: us-central1
      deployment_name: alpha-evolve-infra
      mount_gcs_bucket: my-data-bucket
      colab_machine_type: g2-standard-4
      accelerator_type: NVIDIA_L4
      accelerator_count: 1
      disk_type: pd-balanced
      disk_size_gb: 20
      idle_timeout: 14400s
      environment_variables:
        _CLOUD_BUCKET_NAME: my-data-bucket
        _PROJECT_ID: my-project-id
```

---

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| `project_id` | GCP project ID. | `string` | n/a | yes |
| `region` | GCP region where the Colab runtime and template will be provisioned. | `string` | n/a | yes |
| `deployment_name` | Deployment name used as prefix for runtime template and runtime IDs. | `string` | n/a | yes |
| `mount_gcs_bucket` | Optional GCS bucket name to automatically mount to the VM via `gcsfuse` on startup. | `string` | `null` | no |
| `mount_path` | Local VM directory path where `mount_gcs_bucket` will be mounted. | `string` | `"/home/jupyter/gcs"` | no |
| `staged_files` | List of files/objects to stage on GCS. Each item supports `object_path`, `source_path` or `content`, and optional `bucket_name`. | `list(object)` | `[]` | no |
| `environment_variables` | Map of environment variables to inject into the Colab runtime environment. | `map(string)` | `{}` | no |
| `post_startup_script_behavior` | Execution behavior for post_startup_script ('RUN_ONCE', 'RUN_EVERY_START', 'DOWNLOAD_AND_RUN_EVERY_START'). | `string` | `"DOWNLOAD_AND_RUN_EVERY_START"` | no |
| `colab_machine_type` | Machine type for the Colab runtime VM (e.g., `'n2-standard-4'`). | `string` | `"n2-standard-4"` | no |
| `accelerator_type` | Optional GPU accelerator type (e.g., `'NVIDIA_TESLA_T4'`, `'NVIDIA_L4'`). | `string` | `null` | no |
| `accelerator_count` | Optional number of GPU accelerators. | `number` | `null` | no |
| `disk_type` | Persistent disk type (`'pd-standard'`, `'pd-ssd'`, `'pd-balanced'`). | `string` | `"pd-balanced"` | no |
| `disk_size_gb` | Size of user persistent disk in GB. | `number` | `20` | no |
| `enable_internet_access` | Enable internet access for the Colab runtime VM. | `bool` | `true` | no |
| `network` | Optional VPC network resource name or ID. | `string` | `null` | no |
| `subnetwork` | Optional VPC subnet resource name or ID. | `string` | `null` | no |
| `idle_timeout` | Optional idle timeout duration for automatic shutdown (e.g. `'14400s'` for 4 hours). | `string` | `null` | no |
| `runtime_user` | User email for the Colab runtime. Defaults to active gcloud/Terraform user. | `string` | `null` | no |
| `module_instance_id` | Unique ID of this module instance (automatically populated by gcluster). | `string` | `"agent-platform-colab"` | no |
| `triggers` | Map of arbitrary strings or outputs that force this module to re-run. | `map(string)` | `{}` | no |

---

## Outputs

| Name | Description |
| ---- | ----------- |
| `id` | The unique resource name of the Colab runtime template. |
| `template_id` | The generated ID of the Colab runtime template. |
| `runtime_id` | The generated ID of the Colab runtime. |
| `staged_files` | Map of staged file object paths to their `google_storage_bucket_object` resource attributes. |
