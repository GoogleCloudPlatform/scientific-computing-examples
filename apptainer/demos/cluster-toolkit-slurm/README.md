# Use Cloud Build to deploy Cluster Toolkit blueprints

This repository demonstrates how to use the `cluster_toolkit` Python library within a SLURM environment, leveraging Apptainer for containerization.

## Prerequisites

*   A configured project
*   Previously created builder for gcluster 
    [gcluster-builder](../../builders/cluster-toolkit-builder)
*   Google Cloud SDK (gcloud)
* A created bucket for saving Terraform state.

## Create a bucket
Use the  `gcloud` command to create a bucket.
```
gcloud storage buckets create gs://mybucket_unique_name
```
Bucket names must be globally unique.

## Deployment

To deploy the blueprint, run the `gcloud builds` command with the "deploy.yaml" config file.
This is an example.
```
 gcloud builds submit --config deploy.yaml --no-source\
   --substitutions=_DEPLOYMENT_NAME="apptainer",_BLUEPRINT_PATH="cluster-toolkit/community/examples/hpc-slurm6-apptainer.yaml",_BUCKET="mybucket_unique_name"
 ```
## Destroy the deployment

To destroy the resources deployed by the blueprint, run the `gcloud builds` command with the "destroy.yaml" config file.
This is an example. It is the same command with a different YAML file.
```
 gcloud builds submit --config destroy.yaml --no-source\
   --substitutions=_DEPLOYMENT_NAME="apptainer",_BLUEPRINT_PATH="cluster-toolkit/community/examples/hpc-slurm6-apptainer.yaml",_BUCKET="mybucket_unique_name"
 ```