# Google Cloud Batch Instance Flexibility

When deploying jobs via Google Cloud Batch, you can configure the
`instanceFlexibilityPolicy` within the job's `allocationPolicy` to specify
multiple acceptable machine types and ranks from earlier requirements stages.
Like MIGs, Cloud Batch requires grouping machine types into named
`instanceSelections`, where each selection defines an array of `machineTypes`
and an order of preference (`rank`). While this feature is in Preview, you must
use the `gcloud alpha batch jobs submit` command or the `v1alpha` REST API
endpoint (`jobs.create`).

Reference documentation and API endpoints:

-   [About Cloud Batch instance flexibility](https://docs.cloud.google.com/batch/docs/create-run-job-instance-flexibility)
-   [Configure Cloud Batch instance flexibility (REST API)](https://docs.cloud.google.com/batch/docs/create-run-job-instance-flexibility#rest)
-   [Cloud Batch v1alpha Jobs Create REST API](https://cloud.google.com/batch/docs/reference/rest/v1alpha/projects.locations.jobs/create)
-   [View Cloud Batch jobs and tasks](https://cloud.google.com/batch/docs/view-jobs-tasks)

--------------------------------------------------------------------------------

## 1. Example Payload (`jobs.create` with `instanceFlexibilityPolicy`)

Ensure that the referenced `instances[].policy.bootDisk` adheres to the **Boot
Disk Selection Rules** (e.g., configuring Gen 3+ instances with
`hyperdisk-balanced` and Gen 1 & Gen 2 with `pd-balanced`).

```json
{
  "taskGroups": [
    {
      "taskSpec": {
        "runnables": [
          {
            "script": {
              "text": "echo Running on flexible instance type... Task index: $BATCH_TASK_INDEX"
            }
          }
        ]
      },
      "taskCount": 10
    }
  ],
  "allocationPolicy": {
    "instanceFlexibilityPolicy": {
      "instanceSelections": {
        "gen3-preferred": {
          "machineTypes": [
            "c3-standard-8",
            "c3d-standard-8"
          ],
          "rank": 0
        },
        "gen2-fallback": {
          "machineTypes": [
            "n2-standard-8",
            "n2d-standard-8"
          ],
          "rank": 1
        }
      }
    },
    "instances": [
      {
        "policy": {
          "bootDisk": {
            "type": "hyperdisk-balanced",
            "sizeGb": 50,
            "image": "projects/debian-cloud/global/images/family/debian-12"
          }
        }
      }
    ]
  },
  "logsPolicy": {
    "destination": "CLOUD_LOGGING"
  }
}
```

--------------------------------------------------------------------------------

## 2. Running the Cloud Batch Deployer API

Submit the job creation request using `curl` with an authorization bearer token
from `gcloud` or via the `gcloud alpha` CLI:

### 2.1 Using REST API (`v1alpha jobs.create`)

```bash
# Set environment variables
PROJECT_ID="<PROJECT_ID>"
LOCATION="<LOCATION>"
JOB_NAME="<JOB_NAME>"

# Execute POST request to Cloud Batch v1alpha REST API
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d @batch_job_config.json \
  "https://batch.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${LOCATION}/jobs?job_id=${JOB_NAME}"
```

### 2.2 Using Google Cloud CLI (`gcloud alpha batch jobs submit`)

While instance flexibility is in Preview, use the alpha command to submit the
JSON configuration file:

```bash
gcloud alpha batch jobs submit <JOB_NAME> \
  --location="<LOCATION>" \
  --config="batch_job_config.json"
```

--------------------------------------------------------------------------------

## 3. Monitoring and Inspecting via REST API and CLI

Once the Cloud Batch job is submitted, you can monitor execution progress and
verify which flexible machine types were dynamically assigned to the tasks and
underlying Compute Engine VMs:

### 3.1 Track Job and Task Status

Retrieve job status and task execution events using `gcloud` or REST:

```bash
# Check job status via gcloud
gcloud batch jobs describe <JOB_NAME> --location="<LOCATION>" --format="json(status.state,status.statusEvents)"

# Check job status via REST API
curl -X GET \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://batch.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${LOCATION}/jobs/<JOB_NAME>"
```

### 3.2 Verify Runtime Allocated Machine Types

When Cloud Batch provisions Compute Engine VM instances for your job, it tags
each instance with the label `batch-job-uid=<JOB_UID>`. To verify which flexible
machine types from your ranked selections were dynamically allocated by Cloud
Batch, list the underlying GCE instances filtered by the Batch job ID:

```bash
# First, retrieve the unique job UID
JOB_UID=$(gcloud batch jobs describe <JOB_NAME> --location="<LOCATION>" --format="value(uid)")

# List the provisioned GCE instances and their assigned machine types
gcloud compute instances list \
  --filter="labels.batch-job-uid=${JOB_UID}" \
  --format="table(name,zone,machineType,status)"
```

Sample output showing runtime machine type allocation:

```
NAME                           ZONE           MACHINE_TYPE   STATUS
batch-job-xxxxx-pool-0-node-0  us-central1-a  c3-standard-8  RUNNING
batch-job-xxxxx-pool-0-node-1  us-central1-b  c3d-standard-8 RUNNING
```
