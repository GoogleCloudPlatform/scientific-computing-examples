# PyBatch for Quantum Computing 
Running Quantum Computing circuits on Cloud Batch is made easy by running the [NVIDIA cuQuantum Appliance](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/cuquantum-appliance) container.

This example will show how to run a noisy circuit example, from the [Google Quantum AI team](https://quantumai.google/cirq/noise/representing_noise). One of the key elements of quantum computing is the stability of circuits under noisy conditions. Like electrical circuits, designers of quantum computing circuits will need to calibrate their circuits under noisy conditions. This may require many runs, like a Monte Carlo type simulation. Cloud Batch makes this easy.

## What you will learn?
This example demonstrates how to run a single circuit many times. The output is written to a Google Cloud Storage bucket.

## Step 0, create a bucket
Since a bucket name must be globally unique (as must a project_id), it is a reasonable practice to create your bucket with the same name as your project:
```
gcloud storage buckets create gs://$(gcloud config get-value project)
```
This assumes you have run `gcloud config set project ...`
### Copy cuQuantum Python ciruit simulation file to bucket
The easiest way to get you python script to the container is to copy it to your bucket. Then the batch script can run it:
```
gcloud storage cp cuquantum-noise.py gs://<my_bucket>
```

## Step 1, update the YAML file
The Python script [batch.py](../batch.py) takes a YAML file as input. There are two places in the YAML file that need to be updated to support your local environment.

### Update `project_id` and `region`
Find in the YAML file, [cuquantum-noise.yaml](cuquantum-noise.yaml):
```
project_id: "project_id"
region: "us-central1"

volumes:
  - {bucket_name: "<my_bucket>", gcs_path:  "/mnt/disks/work"}
```
Update `project_id`, `region`, and `bucket_name` to reflect your configuration

## Step 2, Run the batch jobs
The command to run the job is:
```
python3 ../batch.py  --config_file cuquantum-noise.yaml  --create_job 
```

## Look at results
The easiest way to see the results is with `gcloud storage`.  But first you need the job name:
```
python3 ../batch.py  --config_file cuquantum-noise.yaml  --list_jobs 
```
Your job should will be in the list. Something like:
```
Listing jobs
projects/<my_project>/locations/us-central1/jobs/cuquantum-noise-xxxxxxxx       4
```
Then you can use this info to run a gcloud storage command:
```
gcloud storage cat gs://<my_bucket>/dir_cuquantum-noise-xxxxxxxx/*.out
```