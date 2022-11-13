# Used to correctly (!?) form Batch Job
import google.cloud.batch_v1.types

import google.cloud.scheduler_v1
import google.cloud.scheduler_v1.types

import os


project = os.getenv("PROJECT")
number = os.getenv("NUMBER")
location = os.getenv("LOCATION")
job = os.getenv("JOB")

# Batch Job
# Create Batch Job using batch_v1.types
# Alternatively, create this from scratch
batch_job = google.cloud.batch_v1.types.Job(
    priority=0,
    task_groups=[
        google.cloud.batch_v1.types.TaskGroup(
            task_spec=google.cloud.batch_v1.types.TaskSpec(
                runnables=[
                    google.cloud.batch_v1.types.Runnable(
                        container=google.cloud.batch_v1.types.Runnable.Container(
                            image_uri="gcr.io/google-containers/busybox",
                            entrypoint="/bin/sh",
                            commands=[
                                "-c",
                                "echo \"Hello world! This is task ${BATCH_TASK_INDEX}. This job has a total of ${BATCH_TASK_COUNT} tasks.\""
                            ],
                        ),
                    ),
                ],
                compute_resource=google.cloud.batch_v1.types.ComputeResource(
                    cpu_milli=2000,
                    memory_mib=16,
                )
            ),
            task_count=1,
            parallelism=1,
        ),
    ],
    allocation_policy=google.cloud.batch_v1.types.AllocationPolicy(
        location=google.cloud.batch_v1.types.AllocationPolicy.LocationPolicy(
           allowed_locations=[
            f"regions/{location}",
           ], 
        ),
        instances=[
            google.cloud.batch_v1.types.AllocationPolicy.InstancePolicyOrTemplate(
                policy=google.cloud.batch_v1.types.AllocationPolicy.InstancePolicy(
                    machine_type="e2-standard-2",
                ),
            ),
        ],
    ),
    labels={
        "stackoverflow":"73966292",
    },
    logs_policy=google.cloud.batch_v1.types.LogsPolicy(
        destination=google.cloud.batch_v1.types.LogsPolicy.Destination.CLOUD_LOGGING,
    ),
)

# Convert the Google Batch Job into JSON
# Google uses Proto Python
# https://proto-plus-python.readthedocs.io/en/stable/messages.html?highlight=JSON#serialization
batch_json=google.cloud.batch_v1.types.Job.to_json(batch_job)
print(batch_json)

# Convert JSON to bytes as required for body by Cloud Scheduler
body=batch_json.encode("utf-8")

# Run hourly on the hour (HH:00)
schedule = "0 * * * *"

parent = f"projects/{project}/locations/{location}"
name = f"{parent}/jobs/{job}"
uri = f"https://batch.googleapis.com/v1/{parent}/jobs?job_id={job}"

service_account_email = f"{number}-compute@developer.gserviceaccount.com"

scheduler_job = google.cloud.scheduler_v1.types.Job(
    name=name,
    description="description",
    http_target=google.cloud.scheduler_v1.types.HttpTarget(
        uri=uri,
        http_method=google.cloud.scheduler_v1.types.HttpMethod(
            google.cloud.scheduler_v1.types.HttpMethod.POST,
        ),
        oauth_token=google.cloud.scheduler_v1.types.OAuthToken(
            service_account_email=service_account_email,
        ),
        body=body,
    ),
    schedule=schedule,
)

scheduler_json=google.cloud.scheduler_v1.Job.to_json(scheduler_job)
print(scheduler_job)

request = google.cloud.scheduler_v1.CreateJobRequest(
    parent=parent,
    job=scheduler_job,
)

scheduler_client = google.cloud.scheduler_v1.CloudSchedulerClient()
print(
    scheduler_client.create_job(
        request=request
    )
)``