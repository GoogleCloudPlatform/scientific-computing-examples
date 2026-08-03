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

# AlphaEvolve Unified Setup Module

Unified setup module for AlphaEvolve. Supports both baseline infrastructure setup (`stage: infra`) and individual experiment setup (`stage: experiment`).

---

## Features

- **Multi-Stage Execution**: Controlled via the `stage` input variable (`"infra"` or `"experiment"`).
- **Discovery Engine Provisioning (`stage: infra`)**: Provisions Generative Chat Discovery Engine chat assistants via HTTP REST API and asserts connectivity during `terraform apply`.
- **Dynamic `.env` Generation (`stage: infra` & `stage: experiment`)**: Writes baseline `config/variables-infra.env` or experiment-specific `${user_experiment_name}/variables.env` directly to Google Cloud Storage. Accepts a fully configurable `env_vars` map.
- **Project Metadata Tracking (`stage: experiment`)**: Tags active experiment names in GCP Project Metadata for notebook auto-discovery.

---

## Example Usage

### 1. Baseline Infrastructure Deployment (`stage: infra`)

```yaml
- group: alpha-evolve-infra
  modules:
  - id: ae-infra-setup
    source: ./infrastructure/community/modules/alpha-evolve/setup
    settings:
      stage: infra
      project_id: $(vars.project_id)
      region: $(vars.region)
      bucket_name: $(vars.existing_bucket_name)
      location: $(vars.location)
      engine_id: $(vars.engine)
      assistant_id: $(vars.assistant)
      env_vars:
        _PROJECT_ID: $(vars.project_id)
        _REGION: $(vars.region)
        _CLOUD_BUCKET_NAME: $(vars.existing_bucket_name)
        _DEPLOYMENT_NAME: $(vars.deployment_name)
        _PUBSUB_TOPIC: $(pubsub-topic.topic)
        _MOUNT_PATH: $(vars.mount_path)
        _SERVICE_ACCOUNT_EMAIL: $(service-account.service_account_email)
        _LOCATION: $(vars.location)
        _BASE_URL: $(vars.base_url)
        _COLLECTION: $(vars.collection)
        _ENGINE: $(vars.engine)
        _ASSISTANT: $(vars.assistant)
```

### 2. Experiment Deployment (`stage: experiment`)

```yaml
- group: experiment-setup
  modules:
  - id: experiment-setup
    source: ./infrastructure/community/modules/alpha-evolve/setup
    settings:
      stage: experiment
      project_id: $(vars.project_id)
      bucket_name: $(vars.existing_bucket_name)
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
| `stage` | Execution stage (`"infra"` or `"experiment"`). | `string` | n/a | yes |
| `project_id` | GCP project ID. | `string` | n/a | yes |
| `bucket_name` | Name of pre-existing GCS bucket. | `string` | n/a | yes |
| `env_vars` | Map of key-value pairs written to the GCS `.env` file. | `map(string)` | `{}` | no |
| `user_experiment_name` | Name of experiment (required when `stage = "experiment"`). | `string` | `null` | no |
| `create_discovery_engine` | Enable Discovery Engine provisioning during `infra` stage. | `bool` | `true` | no |
| `engine_id` | Discovery Engine engine identifier. | `string` | `null` | no |
| `assistant_id` | Discovery Engine assistant identifier. | `string` | `"default_assistant"` | no |

---

## Outputs

| Name | Description |
| ---- | ----------- |
| `project_number` | Numeric GCP Project Number. |
| `object_path` | GCS object path of the written environment file. |
| `engine_id` | Discovery Engine ID (if created). |
| `assistant_id` | Discovery Engine Assistant ID (if created). |
