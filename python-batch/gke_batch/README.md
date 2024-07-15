# Running batch jobs on GKE

## Create an Autopilot cluster
Run instructions here:

https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster#create_an_autopilot_cluster

Create cluster. This takes several minutes.

```
gcloud container clusters get-credentials moon-shot \
    --location=us-central1 \
    --project=openfoam-jrt
```

Connect to cluster: https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster#connecting_to_the_cluster
```
gcloud container clusters get-credentials moon-shot \
    --location=us-central1 \
    --project=openfoam-jrt
```

## Clone repo, while you're waiting.
Clone the repo:

```
git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples.git
```
Checkout the branch
```
git checkout gke-batch-refarch
```

## Run pip install
Install required Python modules.
```
pip install -r requirements.txt
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
Getting setting job_id
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
Create a bucket with your own name.
```
gcloud storage buckets create gs:/<my_new_bucket_testing>
```

## Update the settings.toml 

Update the settings.toml file with the `project_id`, `bucketName` and other things you choose to update







