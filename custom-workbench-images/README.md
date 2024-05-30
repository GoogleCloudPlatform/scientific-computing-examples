# Using Google Cloud Workstations for SciML


## Workstations Usage - rough notes

Clone this repo into somewhere like Cloudshell.  Need:
- `gcloud` to be already authenticated
- `GOOGLE_CLOUD_PROJECT` to be set to the (preferably new) project you wanna
  use for this
- a bucket to keep terraform state

Then
```
cp envrc.example .envrc
```
edit to taste... then
```
source .envrc
cd terraform
cp backend.conf.example backend.conf
```
edit to taste.


### Create network stuff

Change to `terraform/network` and
```
terraform init -backend-config ../backend.conf
terraform plan
terraform apply
```

### Create a workstations cluster and some example workstations

Enable the workstations service
```
gcloud services enable workstations.googleapis.com
```

Change to `terraform/workstations` and
```
terraform init -backend-config ../backend.conf
terraform plan
terraform apply
```

This takes forever... creating a Cloud Workstations Cluster takes
just at 20 minutes.  This makes it not really useful for tutorials.

We'll have to find some workarounds.  Having the managed control plane
(cluster) helps enterprise customers, but gets in the way of a one-off
tutorial.  For now, this is what we're doing.

### Launch and use workstations

TODO



## Workbenches Usage - rough notes

Much of this is same as above... you can use the same project.
Setup and create the network stuff, then jump down to here:

### Create a Vertex AI Workbench instance

Enable the notebooks service
```
gcloud services enable notebooks.googleapis.com
```

Change to `terraform/workbenches` and
```
terraform init -backend-config ../backend.conf
terraform plan
terraform apply
```

### Launch and use a workbench instance

TODO



## Worker Usage - rough notes

Much of this is same as above... you can use the same project.
Setup and create the network stuff, then jump down to here:

### Create a worker instance

Change to `terraform/workers` and
```
terraform init -backend-config ../backend.conf
terraform plan
terraform apply
```

### Launch and use a worker

TODO



## Clean up after yourself

This stuff costs money.

TODO

