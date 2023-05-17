# GCP PyBatch 

This is a simple example of using the [Google Cloud Batch Python API](https://cloud.google.com/python/docs/reference/batch/latest)

## Usage
The goal of this setup is to simplify some of the syntax of the JSON, assuming a few more default settings. We replace the JSON with YAML, which is marginally easier to create and maintain.

This allows a 
```
python3 batch.py --config_file hello_world.yaml  --create_job
```

## Install PyBatch
Use `git` to clone this repo, then from the directory:
```
cd scientific-computing-examples/cloud-batch-python/python-batch
```
Run pip3:
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

### Authenticate
Independent of where you are running this code, you will need to authenticate. The easiest way to authenticate is with the `gcloud auth` command, and follow the prompts. If you don't have gcloud installed, you need it. 

```
gcloud auth application-default login
```

## Run a job: Hello World
The simplest job is running a shell script to say "Hello World".

```
python3 batch.py --config_file hello_world.yaml  --create_job
```
>> NOTE: Please update the YAML file, `hello_world.yaml` to point to your `project_id`.

You can then check the status of the jobs
```
python3 batch.py --config_file hello_world.yaml  --list_jobs
```
To see what is really happening, you can go to the Google Cloud [Console for Batch](https://console.cloud.google.com/batch/jobs).

