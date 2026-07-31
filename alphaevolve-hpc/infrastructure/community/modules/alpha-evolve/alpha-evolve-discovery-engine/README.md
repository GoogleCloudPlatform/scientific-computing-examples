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

# AlphaEvolve Discovery Engine and Assistant Module

Provisons AlphaEvolve compatible discovery engine and assistant endpoints using Terraform `http` data stanzas to communicate with `v1alpha` Discovery Engine REST endpoints.

---

## Requirements

| Name | Version |
| ---- | ------- |
| `terraform` | >= 1.0 |
| `google` | >= 4.0.0 |
| `http` | >= 3.0.0 |

---

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| `project_id` | GCP project ID. | `string` | n/a | yes |
| `engine_id` | Unique ID for the Discovery Engine chat assistant engine. | `string` | n/a | yes |
| `assistant_id` | Unique ID for the Assistant attached to the Discovery Engine. | `string` | `"default_assistant"` | no |
| `collection` | Discovery Engine collection ID. | `string` | `"default_collection"` | no |
| `location` | Discovery Engine location (e.g. `'global'`). | `string` | `"global"` | no |
| `module_instance_id` | Unique ID of this module instance. | `string` | `"alpha-evolve-discovery-engine"` | no |
| `triggers` | Map of arbitrary strings or outputs to force re-execution. | `map(string)` | `{}` | no |

---

## Outputs

| Name | Description |
| ---- | ----------- |
| `engine_id` | The ID of the created Discovery Engine. |
| `engine_name` | The full resource name of the Discovery Engine. |
| `assistant_id` | The ID of the created Assistant. |
| `assistant_name` | The full resource name of the Assistant. |
