# Running batch jobs on GKE

## Getting started
For ease of use, we set some environment variables.
```
export CLUSTER_NAME=<Choose Your Cluster Name>
export MY_REGION=<Choose Your Region>
export MY_PROJECT_ID=<Choose Your Project ID>
export MY_NEW_BUCKET_TESTING=<Choose Your Bucket Name>
```
To define `PROJECT_NUMBER` use:
```
gcloud config set project $MY_PROJECT_ID
export PROJECT_NUMBER=`gcloud projects list \
--filter="$(gcloud config get-value project)" \
--format="value(PROJECT_NUMBER)"`
```

## Create an Autopilot cluster
Run instructions here:

https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster#create_an_autopilot_cluster

Create cluster. This takes several minutes.

```
gcloud container clusters create-auto $CLUSTER_NAME \
    --location=$MY_REGION \
    --project=$MY_PROJECT_ID
```

When this completes, connect to the cluster

## Connecting to the cluster

Connect to cluster: https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster#connecting_to_the_cluster
```
gcloud container clusters get-credentials $CLUSTER_NAME \
    --location=$MY_REGION \
    --project=$MY_PROJECT_ID
```
## Clone repo, while you're waiting for the cluster to build
Clone the repo:

```
git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples.git
```
```
cd scientific-computing-examples/python-batch/gke_batch
```

## Run pip install
Install required Python modules.
```
python -m pip install -r requirements.txt
```

## Run dry run
```
python batch.py
```
Lots of output like:
```
python batch.py 
Getting setting job_prefix
Getting setting platform
Getting setting JOB_NAME
Getting setting project_id
Getting setting container
Getting setting image_uri
Getting setting command
Getting setting limits
Getting setting volume
Getting setting volume_mount
Getting setting service_account_name
Getting setting node_selector
Getting setting pod_annotations
Getting setting parallelism
Getting setting suspend
Getting setting completion_mode
Getting setting completions
{'api_version': 'batch/v1',
 'kind': 'Job',
 'metadata': {'annotations': None,
              'creation_timestamp': None,
              'deletion_grace_period_seconds': None,
              'deletion_timestamp': None,
              'finalizers': None,
              'generate_name': None,
              'generation': None,
              'labels': {'app': 'args-job-cb829014'},
              'managed_fields': None,
              'name': 'args-job-cb829014',
              'namespace': None,
              'owner_references': None,
              'resource_version': None,
              'self_link': None,
              'uid': None},
 'spec': {'active_deadline_seconds': None,
          'backoff_limit': None,
          'backoff_limit_per_index': None,
```

## Create a GCS Bucket 
```
gcloud storage buckets create gs://${MY_NEW_BUCKET_TESTING}  --uniform-bucket-level-access
```

### Copy python script to bucket
```
gsutil cp python_write.py gs://${MY_NEW_BUCKET_TESTING}/python_write.py

```

## Update the settings.toml 

Update the settings.toml file with the `project_id`, `bucketName` and 
other things you choose to update. 

At this point, you only need to update these two.

The two lines to edit are this:
```
project_id = "MY_PROJECT_ID"
```
and this:
```
volume = {bucketName="MY_NEW_BUCKET_TESTING", driver="gcsfuse.csi.storage.gke.io"}
```
## Update IAM settings for Google Cloud Storage

To allow the GKE cluster access to the GCS bucket, a policy binding must be established.

```
gcloud projects add-iam-policy-binding $MY_PROJECT_ID \
    --member "principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${MY_PROJECT_ID}.svc.id.goog/subject/ns/default/sa/default" \
        --role "roles/storage.objectUser"
```

## Run a job
The `batch.py` looks for the info in `settings.toml`. The settings as 
in this repo do the following:

* Submit a Kubernetes Job
* With `Indexed` for `completion_mode`.
* Runs `parallelism` of 10 tasks.
* Expects 100 `completions`

## Run it
To run the job on the cluster:
```
python batch.py --create_job
```

To see if it was created (that may take few seconds),
you can list jobs:
```
python batch.py --list_jobs
```
This will output a list of jobs:
```
Listing jobs
Name: args-job-0dcc3de5 Succeeded?: True
```

The logic of determining success is WIP. Trying to get it looking better.


## Create job with "args.txt" as input

To submit multiple jobs, with the same container and all other settings 
unchanged, you can run with an `--args_file` option.

The args_file (`args.toml`) looks like:
```
[default]
args = [
   ["/bin/sh", "-c", "python /data/python_write.py > /data/python_01write${JOB_COMPLETION_INDEX}-${JOB_NAME}.txt"],
   ["/bin/sh", "-c", "python /data/python_write.py > /data/python_02write${JOB_COMPLETION_INDEX}-${JOB_NAME}.txt"],
   ["/bin/sh", "-c", "python /data/python_write.py > /data/python_03write${JOB_COMPLETION_INDEX}-${JOB_NAME}.txt"],
   ["/bin/sh", "-c", "python /data/python_write.py > /data/python_04write${JOB_COMPLETION_INDEX}-${JOB_NAME}.txt"],
   ["/bin/sh", "-c", "python /data/python_write.py > /data/python_05write${JOB_COMPLETION_INDEX}-${JOB_NAME}.txt"],
   ["/bin/sh", "-c", "python /data/python_write.py > /data/python_06write${JOB_COMPLETION_INDEX}-${JOB_NAME}.txt"],
...
```
### Run the job
```
python batch.py --args_file args.toml
```
This will start 48 jobs, each as an indexed job. There will be output on GCS. To view this:
```
gsutil ls gs://${MY_NEW_BUCKET_TESTING}/
```

These are the files created by the job.


