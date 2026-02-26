# Terraform Google Cloud Pub/Sub Topic Module

This Terraform module creates a Google Cloud Pub/Sub topic.

## Usage

```hcl
module "pubsub_topic" {
  source                      = "./modules/pubsub_topic"
  project_id                  = "your-gcp-project-id"
  topic_name                  = "my-new-topic"
  labels = {
    "environment" = "production"
  }
  allowed_persistence_regions = ["us-central1"]
}
```

## Inputs

| Name                        | Description                                                              | Type          | Default                                               | Required |
| --------------------------- | ------------------------------------------------------------------------ | ------------- | ----------------------------------------------------- | :------: |
| `project_id`                | The GCP project ID where the Pub/Sub topic will be created.              | `string`      | n/a                                                   |   yes    |
| `topic_name`                | The name of the Pub/Sub topic.                                           | `string`      | `"my-example-topic"`                                  |    no    |
| `labels`                    | A map of labels to apply to the Pub/Sub topic.                           | `map(string)` | `{"environment" = "development", "managed-by" = "terraform"}` |    no    |
| `allowed_persistence_regions` | A list of GCP regions where messages are allowed to be stored.           | `list(string)`| `[]`                                                  |    no    |

## Outputs

| Name         | Description                                                                        |
| ------------ | ---------------------------------------------------------------------------------- |
| `topic_id`   | The fully qualified ID of the Pub/Sub topic (projects/PROJECT_ID/topics/TOPIC_NAME). |
| `topic_name` | The short name of the Pub/Sub topic.                                               |
