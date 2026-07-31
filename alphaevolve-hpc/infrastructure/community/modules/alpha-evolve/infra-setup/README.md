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

# AlphaEvolve Infrastructure Setup Module

Provisions baseline configuration artifacts for AlphaEvolve by validating GCP project and GCS bucket existence, and natively formatting and uploading `config/variables-infra.env` to Google Cloud Storage.

---

## Features

- **Native GCS Upload**: Writes system baseline variables directly to GCS via `google_storage_bucket_object`.
- **Environment Formatting**: Formats variables with standard leading underscores (`_PROJECT_ID`, `_CLOUD_BUCKET_NAME`, `_PUBSUB_TOPIC`, etc.) for `python-dotenv` compatibility.

---

## Example Usage

```yaml
- group: alpha-evolve-infra
  modules:
  - id: ae-infra-setup
    source: ./infrastructure/community/modules/alpha-evolve/infra-setup
    settings:
      project_id: $(vars.project_id)
      region: $(vars.region)
      existing_bucket_name: $(vars.existing_bucket_name)
      deployment_name: $(vars.deployment_name)
      pubsub_topic: $(pubsub-topic.topic)
      mount_path: $(vars.mount_path)
      service_account_email: $(service-account.service_account_email)
      location: $(vars.location)
      base_url: $(vars.base_url)
      collection: $(vars.collection)
      engine_id: $(vars.engine)
      assistant_id: $(vars.assistant)
```

---

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| `project_id` | GCP project ID. | `string` | n/a | yes |
| `region` | GCP region for baseline deployment. | `string` | n/a | yes |
| `existing_bucket_name` | Name of pre-existing GCS bucket. | `string` | n/a | yes |
| `deployment_name` | Infrastructure deployment name. | `string` | n/a | yes |
| `pubsub_topic` | Pub/Sub topic name for Batch notification alerts. | `string` | n/a | yes |
| `mount_path` | Target mount directory path for GCS Fuse inside VM runtimes. | `string` | `"/mnt/disks/share"` | no |
| `service_account_email` | Service account email used for execution. | `string` | n/a | yes |
| `location` | Location for AlphaEvolve API engine. | `string` | `"global"` | no |
| `base_url` | Base endpoint URL for AlphaEvolve Discovery Engine API. | `string` | `"discoveryengine.googleapis.com"` | no |
| `collection` | Discovery Engine collection identifier. | `string` | `"default_collection"` | no |
| `engine_id` | Engine ID for Discovery Engine. | `string` | n/a | yes |
| `assistant_id` | Assistant ID for Discovery Engine. | `string` | `"default_assistant"` | no |

---

## Outputs

| Name | Description |
| ---- | ----------- |
| `project_number` | The numeric GCP Project Number. |
