# Click to Deploy! A3mega Slurm cluster using Cluster Toolkit

This tutorial guides you through setting up a A3Mega Slurm cluster with the high-performance computing (HPC) environments. We'll use the **Google Cloud Cluster Toolkit** (`gcluster`) to define the infrastructure in YAML files.

Here are material related to this solution:
* **A3mega deployment instruction**
  https://cloud.google.com/cluster-toolkit/docs/deploy/deploy-a3-mega-cluster
* **Google Cloud Cluster Toolkit**
  https://github.com/GoogleCloudPlatform/cluster-toolkit


## Files in this repository

- tutorial.MD - This file offers step-by-step guide to walk through the whole deployment. 

- a3mega-slurm-deployment.yaml- This file has all the variables necessary as blueprint input.

- a3mega-lustre-slurm-blueprint.yaml - This blueprint creates the following:
  - Slurm cluster with A3mega GPU machines
  - Manged Lustre
  - GCSFuse
  - DWS Flex Partition

- a3mega-lustre-slurm-blueprint-dws-2-partitions.yaml - This blueprint creates the following:
  - Slurm cluster with A3mega GPU machines
  - Manged Lustre
  - GCSFuse
  - DWS Partitions - one for DWS Flex and one for DWS Calendar

## Let's get started  

To kick off the demo / tutorial, please click the link below. This will open a new Cloud Shell session for you. 
https://ssh.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/GoogleCloudPlatform/cluster-toolkit

Downloading the files from this repository. You can run the following command at the cloud shell session 
```bash
wget https://github.com/GooggleCloudPlatform/cluster-toolkit/deployment-set-a3mega/archive/refs/heads/main.zip
unzip main.zip
```

Get the tutorial up in the Cloud Shell session:
```bash
teachme deployment-set-a3mega-main/tutorial.md
```

Now you can follow the tutorial at the Cloud Shell session. Happy Computing! 



## **Note and Troubleshooting** 

* Creating the DWS Calendar reservation:
  Please update the time, dws name, project id and run the gcloud command. You may need to run **gcloud components install alpha** prior. 
```bash
gcloud alpha compute future-reservations create <dws name> --project=<customer project id>  --auto-delete-auto-created-reservations --machine-type=a3-megagpu-8g --planning-status=SUBMITTED --require-specific-reservation --start-time=2025-08-15T19:00:00Z --end-time=2025-08-16T19:00:00Z --total-count=2 
--zone=us-central1-a
```

* if deployment sees the issue with Private Connection Access. Please run the following command:
Please replace the ranges name (eg: global-psconnect-ip-a799d0f7 which is created on the fly and you can find the name from the message) , and project id and run the command. Then you can rerun the **SAME** deployment command.  
```bash
gcloud services vpc-peerings update --service=servicenetworking.googleapis.com --ranges=<PSA range name> --network=a3mega-sys-net --project=<customer project id> --force
```

* Limitation of Cloud Shell
Cloud Shell has 5GB limit and 40 hours usage per week.
If you need to get back to the same cloud shell session without downloading the git repo again. Please use this command:
https://ssh.cloud.google.com/cloudshell/editor
