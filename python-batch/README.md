# GCP PyBatch 

This is a simple example of using the [Google Cloud Batch Python API](https://cloud.google.com/python/docs/reference/batch/latest)

## Usage
The goal of this setup is to simplify some of the syntax of the JSON, assuming a few more default settings. We replace the JSON with YAML, which is marginally easier to create and maintain.


This allows a simplified deployment command.
```
python3 batch.py --config_file hello_world.yaml  --create_job
```
## Install PyBatch
Use `git` to clone this repo to your home directory, then from the directory:
```
cd scientific-computing-examples/python-batch
```
Run pip3 (note: you may want to make use of virtual env: (ven)[https://docs.python.org/3/library/venv.html]:
```
python3 -m pip install  --upgrade
python3 -m pip install  -r requirements.txt
```
If you get errors around pip, make sure pip is (correctly installed)[https://pip.pypa.io/en/stable/installation/].

You should now be able test `batch.py`

### Test
The simplest command is for `--help`:
```
python3 batch.py --help
```

Which outputs:
```
Tools to run batch API

flags:

batch.py:
  --config_file: Config file in YAML
  --[no]create_job: Creates job, otherwise just prints config.
    (default: 'false')
  --[no]debug: If true, print debug info.
    (default: 'false')
  --delete_job: Job name to delete.
    (default: '')
  --[no]list_jobs: If true, list jobs for config.
    (default: 'false')
  --previous_job_id: For Pubsub restart, specifies topic to read from
  --project_id: Google Cloud Project ID, not name
  --[no]pubsub: Run Pubsub
    (default: 'false')
  --volumes: List of GCS paths to mount. Example, "bucket_name1:mountpath1 bucket_name2:mountpath2"
    (a whitespace separated list)

Try --helpfull to get a list of all flags.
```

## Before you submit a job
The following need to be run before you can submit a job.
### Enable the Cloud Batch API
Enable the Cloud Batch API:
```
gcloud services enable batch.googleapis.com
```
### IAM permissions
If you are running as the `owner` of the project you are running in, you will have sufficient scope to run the Batch API. You can review IAM permissions in the (Cloud Console)[ttps://console.cloud.google.com/iam-admin/iam].

At a minimum, the user (or service account) running a Batch job will need  (Batch Jobs Editor role)[https://cloud.google.com/iam/docs/understanding-roles#batch.jobsEditor]

You can add this role using the `gcloud` command. 
```
$ gcloud projects add-iam-policy-binding example-project-id-1 \
   --member='user:test-user@gmail.com' --role='roles/batch.jobsEditor'
```
Where `test-user`  `example-project-id-1` should be replaced with correct values for your configuration.

### Authenticate
Independent of where you are running this code, you will need to authenticate. The easiest way to authenticate is with the `gcloud auth` command, and follow the prompts. If you don't have gcloud installed, you need it. 

```
gcloud auth application-default login
```

## Run a job: Hello World
The simplest job is running a shell script to say "Hello World".

### --create_job
```
python3 batch.py --config_file hello_world.yaml  --create_job
```
>> NOTE: Please update the YAML file, `hello_world.yaml` to point to your `project_id`.

### --list_jobs
You can then check the status of the jobs
```
python3 batch.py --config_file hello_world.yaml  --list_jobs
```
### --delete_job
This will allow you to delete a jobs that is running. 
```
python3 batch.py --config_file hello_world.yaml  --delete_job job_id
```
where `job_id` would be the value you saw in the `--list_jobs` command.

### Use the console
To see what is really happening, you can go to the Google Cloud [Console for Batch](https://console.cloud.google.com/batch/jobs).

If you click on the link of any job you view there, you can view the details of the job and the logs associated to the batch job output.

## More sample jobs
There are a few more sample jobs to try:

### Run batch with GCS Fuse mount
To connect a Google Cloud Storage (GCS) bucket to you batch job environment, Batch will enable a [GCS Fuse](https://cloud.google.com/storage/docs/gcs-fuse) connection for you.

#### Create a bucket
To run this test, you need a GCS bucket. [This is explained in detail here](https://cloud.google.com/storage/docs/creating-buckets).

#### Modify the config file
In the config file call `shell_with_gcsfuse.yaml`, you will see some lines:
```
volumes: 
  - {bucket_name:  "batch-jrt-2", gcs_path:  "/mnt/disks/local"}
```
Update with your bucket name.

Also update `project_id` with your value.

#### Run it!
python3 batch.py  --config_file shell_with_gcsfuse.yaml --create_job

### Run a simple batch job with a container
This sample will just run a container as an example of how to do so.

#### Use --project_id instead of modifying the config file
For convenience, there is a command line option 
```
python3 batch.py  --config_file simple-container.yaml --create_job --project_id my_project_id
```
The job with have the Job name `container-xxxxx`. In the Console, clicking through on that, you can see the log output looking like:
```
Hello world! This is task 0. This job has a total of 4 tasks.
```

### Run a simple batch job with a CUDA container
This is a simple example of running the command `nvidia-smi` on batch using an NVIDIA CUDA container.

#### Modify the config file
In the config file call `nvidia-smi-container.yaml`,  update `project_id` with your value.

#### Run it!
The command to run is:
```
python3 batch.py  --config_file nvidia-smi-container.yaml --create_job
```
#### Look at the logs
Go to the jobs page, [Console for Batch](https://console.cloud.google.com/batch/jobs), then select the job you just ran. It will have the name `nvidia-smi-xxxxxx`.  

When the job is completed, it will have a status of `Succeeded`. Looking in the logs for that job, you can see some output for the `nvidia-smi` command.
```
2023-10-11 10:10:53.683 EDT
+---------------------------------------------------------------------------------------+
2023-10-11 10:10:53.683 EDT
| NVIDIA-SMI 535.104.05 Driver Version: 535.104.05 CUDA Version: 12.2 |
2023-10-11 10:10:53.683 EDT
|-----------------------------------------+----------------------+----------------------+
2023-10-11 10:10:53.683 EDT
| GPU Name Persistence-M | Bus-Id Disp.A | Volatile Uncorr. ECC |
2023-10-11 10:10:53.683 EDT
| Fan Temp Perf Pwr:Usage/Cap | Memory-Usage | GPU-Util Compute M. |
2023-10-11 10:10:53.683 EDT
| | | MIG M. |
2023-10-11 10:10:53.683 EDT
|=========================================+======================+======================|
2023-10-11 10:10:53.693 EDT
| 0 Tesla T4 Off | 00000000:00:04.0 Off | 0 |


2023-10-11 10:10:53.693 EDT
| N/A 73C P0 30W / 70W | 2MiB / 15360MiB | 0% Default |
2023-10-11 10:10:53.693 EDT
| | | N/A |
2023-10-11 10:10:53.693 EDT
+-----------------------------------------+----------------------+----------------------+
2023-10-11 10:10:53.693 EDT
2023-10-11 10:10:53.693 EDT
+---------------------------------------------------------------------------------------+
2023-10-11 10:10:53.693 EDT
| Processes: |
2023-10-11 10:10:53.693 EDT
| GPU GI CI PID Type Process name GPU Memory |
2023-10-11 10:10:53.693 EDT
| ID ID Usage |
2023-10-11 10:10:53.693 EDT
|=======================================================================================|
2023-10-11 10:10:53.693 EDT
| No running processes found |
2023-10-11 10:10:53.693 EDT
+---------------------------------------------------------------------------------------+
```

## More complex job types
There are subdirectories of this repository that provide more detailed types of batch jobs:

* [CUDA with PubSub queuing](./cuda_pubsub)
* [Quantum Computing](./quantum)
* [Genomics, Deepvariant](./deepvariant)