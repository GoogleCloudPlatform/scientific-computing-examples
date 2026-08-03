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

# Cloud Build Module

Executes Cloud Build jobs using custom `cloudbuild.yaml` template files (`.tfpl`), raw YAML strings, or external build configs via `gcloud builds submit`. It supports dynamic Terraform apply-time template rendering (`template_vars`), Cloud Build runtime substitutions (`substitutions`), custom service accounts, and GCS staging buckets.

---

## Features

- **Flexible Configuration**: Supply a template file path (`cloud_build_template_path`) or inline YAML content (`cloud_build_content`).
- **Dynamic Templating**: Pass arbitrary key-value pairs (`template_vars`) into `templatefile()` for plan/apply-time variable resolution (useful when you need to pass variables from other Terraform modules/resources).
- **Runtime Substitutions**: Pass `--substitutions=_KEY=VALUE` to Cloud Build for dynamic build execution variables.
- **Service Account & Staging Support**: Easily configure `--service-account` and `--gcs-source-staging-dir`.

---

## Usage Examples

### Example 1: Template File (`.tfpl`) with `template_vars`

Use `cloud_build_template_path` to render a `.tfpl` template file using Terraform variables:

```hcl
module "build_containers" {
  source = "./modules/cloud-build"

  project_id                = "my-gcp-project"
  region                    = "us-central1"
  cloud_build_dir           = "./src"
  cloud_build_template_path = "./cloudbuild.yaml.tfpl"

  template_vars = {
    repo_name  = "my-artifact-repo"
    image_name = "my-app"
    image_tag  = "v1.0.0"
    base_image = "python:3.12-slim"
  }

  service_account = "sa-build@my-gcp-project.iam.gserviceaccount.com"
}
```

*Inside `cloudbuild.yaml.tfpl`:*
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '--build-arg'
      - 'BASE_IMAGE=${base_image}'
      - '-t'
      - '${region}-docker.pkg.dev/${project_id}/${repo_name}/${image_name}:${image_tag}'
      - '.'
```

---

### Example 2: Inline YAML Content (`cloud_build_content`)

Use `cloud_build_content` to supply raw YAML content directly in HCL:

```hcl
module "inline_build" {
  source = "./infrastructure/modules/cloud-build"

  project_id          = "my-gcp-project"
  cloud_build_dir     = "./src"
  cloud_build_content = <<-YAML
    steps:
      - name: 'gcr.io/cloud-builders/docker'
        args: ['build', '-t', 'gcr.io/my-gcp-project/my-service:latest', '.']
  YAML
}
```

---

### Example 3: Using Cloud Build Substitutions (`substitutions`)

Use `substitutions` to pass runtime variables (`_KEY=VALUE`) directly to Cloud Build (`--substitutions`):

```hcl
module "build_with_substitutions" {
  source = "./infrastructure/modules/cloud-build"

  project_id                = "my-gcp-project"
  cloud_build_dir           = "."
  cloud_build_template_path = "./cloudbuild.yaml.tfpl"

  template_vars = {
    repo_name = "my-repo"
  }

  substitutions = {
    _BRANCH_NAME = "main"
    _COMMIT_SHA  = "a1b2c3d4"
    _ENV         = "production"
  }
}
```

> **Tip**: When referencing Cloud Build runtime substitution variables (e.g. `$BUILD_ID` or `$_BRANCH_NAME`) inside a `.tfpl` template file, escape the `$` with double dollar signs (`$$`) to prevent Terraform's `templatefile()` parser from evaluating them:
> ```yaml
> # Inside .tfpl file:
> images:
>   - '${region}-docker.pkg.dev/${project_id}/${repo_name}/app:$${_COMMIT_SHA}'
> ```

---

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| `project_id` | GCP project ID. | `string` | n/a | yes |
| `region` | GCP region where Artifact Registry and Cloud Build execute. | `string` | `"us-central1"` | no |
| `cloud_build_template_path` | Path to the `cloudbuild.yaml` template file. | `string` | `null` | no |
| `cloud_build_content` | Raw YAML content for Cloud Build config (alternative to `cloud_build_template_path`). | `string` | `null` | no |
| `cloud_build_dir` | Root directory of the workspace where Dockerfiles and application source code reside. | `string` | `"."` | no |
| `template_vars` | Map of variables to pass into `templatefile()` when rendering `cloud_build_template_path`. | `map(any)` | `{}` | no |
| `substitutions` | Map of Cloud Build substitution variables (`_KEY=VALUE`). All keys must start with `_`. | `map(string)` | `{}` | no |
| `gcs_staging_dir` | Optional GCS bucket path for Cloud Build source staging (e.g., `gs://bucket/staging`). | `string` | `null` | no |
| `service_account` | Optional service account email to execute Cloud Build. | `string` | `null` | no |
| `module_instance_id` | Unique ID of this module instance (automatically populated by gcluster). | `string` | `"cloud-build"` | no |
| `triggers` | Map of arbitrary strings or outputs that force this module to re-run. | `map(string)` | `{}` | no |

---

## Outputs

| Name | Description |
| ---- | ----------- |
| `id` | The unique execution ID of the container build. |
| `config_filename` | Path to the rendered local Cloud Build YAML config file. |
