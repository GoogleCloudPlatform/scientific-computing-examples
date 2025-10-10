# Terraform Google Cloud Logging Sink Module

This Terraform module creates a Google Cloud Logging sink.

The sink is configured to export logs to a Pub/Sub topic and grants the necessary IAM permissions for the sink's service account to publish to the topic. It also grants subscriber permissions to the default compute service account.

## Usage

```hcl
module "logging_sink" {
  source            = "./modules/logging_sink"
  project_id        = "your-gcp-project-id"
  topic_id          = "projects/your-gcp-project-id/topics/your-topic-name"
  topic_name        = "your-topic-name"
  subscription_name = "your-subscription-name"
  sink_name         = "my-logging-sink"
  log_filter        = "severity >= ERROR"
}
```

## Inputs

| Name              | Description                                                 | Type   | Default                         | Required |
| ----------------- | ----------------------------------------------------------- | ------ | ------------------------------- | :------: |
| `project_id`      | The GCP project ID where the logging sink will be created.  | `string` | n/a                             |   yes    |
| `topic_id`        | The fully qualified pubsub topic topic id.                  | `string` | `""`                            |    no    |
| `topic_name`      | The pubsub topic to bind to.                                | `string` | `""`                            |    no    |
| `subscription_name` | The pubsub subscription to bind to.                         | `string` | `""`                            |    no    |
| `sink_name`       | The name of the logging sink.                               | `string` | `"gcs-error-log-export-sink"`   |    no    |
| `log_filter`      | The filter for the logs to be exported by the sink.         | `string` | `"severity >= ERROR"`           |    no    |

## Outputs

| Name                   | Description                                                                                             |
| ---------------------- | ------------------------------------------------------------------------------------------------------- |
| `sink_id`              | The fully qualified ID of the logging sink.                                                             |
| `sink_writer_identity` | The service account identity created for this sink. This identity has been granted permission to write to the destination. |
