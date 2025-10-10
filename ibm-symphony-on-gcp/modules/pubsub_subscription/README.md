# Terraform Google Cloud Pub/Sub Subscription Module

This Terraform module creates a Google Cloud Pub/Sub subscription to a specified topic.

## Usage

```hcl
module "pubsub_subscription" {
  source                     = "./modules/pubsub_subscription"
  project_id                 = "your-gcp-project-id"
  topic_name                 = "name-of-your-topic"
  subscription_name          = "my-new-subscription"
  ack_deadline_seconds       = 30
  subscription_filter        = "attributes.status = \"processed\""
}
```

## Inputs

| Name                         | Description                                                              | Type          | Default                  | Required |
| ---------------------------- | ------------------------------------------------------------------------ | ------------- | ------------------------ | :------: |
| `project_id`                 | The GCP project ID to deploy the resources to.                           | `string`      | n/a                      |   yes    |
| `topic_name`                 | The name of the Pub/Sub topic.                                           | `string`      | `"example-topic"`        |    no    |
| `subscription_name`          | The name of the Pub/Sub subscription.                                    | `string`      | `"hf-gce-vm-events-sub"` |    no    |
| `ack_deadline_seconds`       | The acknowledgment deadline for messages pulled from this subscription.  | `number`      | `20`                     |    no    |
| `message_retention_duration` | How long to retain unacknowledged messages in the subscription's backlog.| `string`      | `"604800s"`              |    no    |
| `subscription_filter`        | A filter expression for the subscription. Leave empty for no filter.     | `string`      | `""`                     |    no    |
| `labels`                     | A map of labels to apply to the Pub/Sub resources.                       | `map(string)` | `{"environment" = "dev", "terraform" = "true"}` |    no    |

## Outputs

| Name                | Description                                          |
| ------------------- | ---------------------------------------------------- |
| `subscription_id`   | The fully qualified ID of the Pub/Sub subscription.  |
| `subscription_name` | The name of the Pub/Sub subscription.                |

