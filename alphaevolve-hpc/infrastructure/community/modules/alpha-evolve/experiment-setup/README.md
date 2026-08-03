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

# AlphaEvolve Experiment Setup Module

Provisions experiment-level configuration artifacts for AlphaEvolve. It writes an experiment metadata item to GCP Project Metadata (enabling dynamic experiment discovery in the Colab notebook), natively uploads the experiment's `variables.env` map to Cloud Storage, and prints interactive launch instructions.

---

## Features

- **Project Metadata Registration**: Writes `${user_experiment_name}_USER_EXPERIMENT_NAME` to GCP project metadata via `google_compute_project_metadata_item`.
- **Native GCS Env Upload**: Uploads `variables.env` to GCS using `google_storage_bucket_object`.
- **Console Launch Instructions**: Prints step-by-step launch guidance to the deployer console via `terraform_data`.

---

## Example Usage

```yaml
- group: experiment-setup
  modules:
  - id: experiment-setup
    source: ./infrastructure/community/modules/alpha-evolve/experiment-setup
    settings:
      bucket_name: $(vars.existing_bucket_name)
      object_path: $(vars.user_experiment_name)/variables.env
      user_experiment_name: $(vars.user_experiment_name)
      env_vars:
        _PROJECT_ID: $(vars.project_id)
        _PUBSUB_SUBSCRIPTION: $(vars.deployment_name)-subscription
        _REPO_NAME: $(artifact-repository.artifact_name)
        _CONTROLLER_IMAGE_URI: us-central1-docker.pkg.dev/my-project/my-repo/my-exp-controller:latest
        _EVALUATOR_IMAGE_URI: us-central1-docker.pkg.dev/my-project/my-repo/my-exp-evaluator:latest
```

---

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| `project_id` | GCP project ID. | `string` | n/a | yes |
| `bucket_name` | Name of target GCS bucket for experiment config storage. | `string` | n/a | yes |
| `object_path` | Target GCS object path (e.g. `exp-1/variables.env`). | `string` | n/a | yes |
| `user_experiment_name` | Name of the user experiment. | `string` | n/a | yes |
| `env_vars` | Map of key-value pairs written into `variables.env`. | `map(string)` | `{}` | no |
| `module_instance_id` | Unique ID of this module instance. | `string` | `"experiment-setup"` | no |
| `triggers` | Map of arbitrary strings to force re-execution. | `map(string)` | `{}` | no |

---

## Outputs

| Name | Description |
| ---- | ----------- |
| `object_path` | The GCS object path of the written environment file. |
