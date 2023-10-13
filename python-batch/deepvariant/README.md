# PyBatch for Deepvariant Genomics

Running Quantum Computing circuits on Cloud Batch is made easy by running the [NVIDIA cuQuantum Appliance](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/cuquantum-appliance) container.

This example will show how to run a genomics pipeline with Google's [DeepVariant](https://blog.research.google/2017/12/deepvariant-highly-accurate-genomes.html). DeepVariant uses some novel ML techniques to process genomics data.

## What you will learn?
This example demonstrates how to run the DeepVariant Docker container on Google Cloud Batch. 

## Step 0, create a bucket
Since a bucket name must be globally unique (as must a project_id), it is a reasonable practice to create your bucket with the same name as your project:
```
gcloud storage buckets create gs://$(gcloud config get-value project)
```
This assumes you have run `gcloud config set project ...`

Copy the deepvariant shell script to your bucket.
'''
gsutil cp deepvariant.sh gs://<my_bucket>/ 
'''


## Step 1, update the YAML file
The Python script [batch.py](../batch.py) takes a YAML file as input. There are two places in the YAML file that need to be updated to support your local environment.

### Update `project_id` and `region`
Find in the YAML file, [deepvariant.yaml](deepvariant.yaml):
```
project_id: "project_id"
region: "us-central1"

job_prefix: 'deepvariant-'
machine_type: "n1-standard-64"
volumes:
  - {bucket_name:  "<my_bucket>", gcs_path:  "/mnt/disks/work"}
  - {bucket_name:  "deepvariant", gcs_path:  "/mnt/disks/deepvariant"}
```
Update `project_id`, `region`, and `bucket_name:  <my_bucket>` to reflect your configuration

## Run the batch jobs
The command to run the job is:
```
python3 ../batch.py  --config_file cuquantum-noise.yaml  --create_job 
```
## View results
The easiest way to find the results is to look at the log files. You can see them in the Batch console:
> https://console.cloud.google.com/batch/jobs

From this site, you can find your job, then view the logs.