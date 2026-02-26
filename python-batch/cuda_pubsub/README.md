# PyBatch for CUDA and Queuing

This job type is to support users with two goals:
1. To run queued jobs in a predictable sequence
1. To run jobs on a GPU using a CUDA based container

These goals are obtains as follows:

## Background: using PubSub to ensure queuing order and restart
[PubSub](https://cloud.google.com/pubsub) is a streaming even management tool used in many event driven applications. It is a fully managed scalable, orderable and easy to use platform.

### How is queueing order managed?
For this, the [`batch.py`](../batch.py) Python script has a command line option (--pubsub) to automatically create a PubSub topic and PubSub subscription following that topic. The name of the PubSub topic and subscription are based on the job_id submitted.  The script then publishes a sequence of messages of numerically ordered integers, from 0 to the number to tasks. The subscription will then pull the messages in sequence. 

### Using the subscription
The ordered subscription allows the Batch job to pull messages in a sequence of ordered IDs. There is a python script provided to obtain the IDs, [pull_fifo_id.py](pull_fifo_id.py). 

An example of how this script is called is as follows:
```
python3 pull_fifo_id.py --project_id=$PID --job_id=$TOPIC_ID
```
In the example YAML file provided here, you can see that the script is used to prepare an ENVIRONMENT variable used futher down the bash script:
```
       export TOPIC_ID=$BATCH_JOB_ID;
       export PID=$(gcloud config get-value project);
       export FIFO_ID=$(python3 /tmp/pull_fifo_id.py --project_id=$PID --job_id=$TOPIC_ID);
       if [ \"$FIFO_ID\" -gt \"30\" ]; then   echo FIFO gt 3;   exit 0; fi;
       echo FIFO_ID:  $FIFO_ID;
       /tmp/simpleCUFFT_2d_MGPU
```

## Getting started
There are a few steps to go through to run this demo. We'll take you through.

### Step 0, build a CUDA binary

To make a simple example, you can use the NVIDA cuda-samples library.
```
git clone https://github.com/NVIDIA/cuda-samples.git
```
Then `cd` to an FFT sample code.
```
cd cuda-samples/Samples/4_CUDA_Libraries/simpleCUFFT_2d_MGPU
```
Now instead of trying to configure a complete CUDA build environment from scratch, you can use a CUDA
Docker container to build:
```
docker run --mount type=bind,source="$(pwd)",target=/build -it nvidia/cuda:12.2.0-devel-ubuntu20.04 /bin/bash
```
You will then be in the CUDA container. `cd` to the `/build` directory and run `make`.
```
cd /build
make
exit
```
There should be a file `simpleCUFFT_2d_MGPU` in the local directory.  Copy this to the `cuda_pubsub` directory
```
cp simpleCUFFT_2d_MGPU ~/scientific-computing-examples/python-batch/cuda_pubsub
```

### Step 1, build the docker image
Return to the `cuda_pubsub` directory.
```
cd  ~/scientific-computing-examples/python-batch/cuda_pubsub
```

The first step is to create a CUDA based Docker image with the correct Python configuration to run the PubSub and other Cloud service. This is made easy with the included [Dockerfile](Dockerfile).  

To create the docker image run the following command (modified for your project).
```
sudo docker build -t <my_region>-docker.pkg.dev/i<my_project>/cuda/pybatch .
```
where `<my_region>` is something like `us-central1` and `<my_project>`  is the project_id you are running from.

If successful, you will see output like:
```
Successfully tagged us-central1-docker.pkg.dev/my_project/cuda/pybatch:latest
```

### Step 2, create a Google Cloud Artifact Registry
To create a project-wide (but private to you) Docker repository, you can use [Artifact Registery](https://cloud.google.com/artifact-registry). 

First you need to [enable the Artifact Registry API](https://cloud.google.com/artifact-registry/docs/enable-service)
```
gcloud services enable artifactregistry.googleapis.com
gcloud projects add-iam-policy-binding <my_project> \
   --member=user:<my_email> \
   --role=roles/artifactregistry.admin
```
> You may need to update your `gcloud` configuration, for example: `gcloud config set project <my_project>`

> You may also need to run a `docker login` command like:
```
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://<my_region>-docker.pkg.dev
```

It is a simple `gcloud` command to create the repository.
```
gcloud artifacts repositories create cuda --location=<my_region> --repository-format=DOCKER
```
where again, `<my_region>` needs to be updated.

#### Publish the Docker image to the repo
To be able to access the Docker image from within the Batch system, the image must be published to the repo. Another docker command.
```
docker push <my_region>.pkg.dev/<my_project>/cuda/pybatch 
```
You will have success when you see something like this:
```
latest: digest: sha256:48d85ac65cba4599ab3e2df5ddeabe2521dbc6ab2c2c90eac22e4d1896680513 size: 3895
```
## Run the batch job
A little more work and the job will be ready to run. 

Update the `nvidia-python.yaml` config file.

### Create a Cloud Storage Bucket
It is easiest to get a cloud bucket with the same name as the project you running in:
```
gcloud storage buckets create gs://$(gcloud config get-value project)
```
### Create a Cloud Storage Bucket
Update the config file volume with the name of the bucket, also the same as your project:
```
volumes:
  - {bucket_name: "<my_project>", gcs_path:  "/mnt/disks/work"}
```

### Update your project_id and region
Add correct values to the config file:
```
project_id: "project_id"
region: "us-central1"

```
### Update Image URI.

First, update the YAML file to have the correct URI to your docker image:
```
  image_uri: "<my_region>-docker.pkg.dev/<my_project>/cuda/pybatch:latest" 
```
where `<my-region>` `<my_project>` need to be updated.

### Finally Run the job
The command to run the job is here:
```
python3 ../batch.py  --config_file nvidia-python.yaml --create_job --pubsub
```

### List the jobs
You can view the jobs status 
'''
python3 ../batch.py  --config_file nvidia-python.yaml --create_job --pubsub
'''

### View jobs in the console

Go to the jobs page, [Console for Batch](https://console.cloud.google.com/batch/jobs), then select the job you just ran. It will have the name `nvidia-python-xxxxxx`.  


### View outputs in your Storage bucket
In this script, output is written to the mounted GCS bucket, which you can [see in the Console], or using the `gsutil` command.
```
gcloud storage ls gs://<my_bucket_name>
```
Exploring the bucket you can find your output.


