# NVIDIA CUDA Samples -- MonteCarloMultiGPU - Financial Services Industry


This guide provides instructions on how to build and run NVIDIA CUDA Samples. In particular,
the [MonteCarloMultiGPU](https://github.com/NVIDIA/cuda-samples/tree/master/Samples/5_Domain_Specific/MonteCarloMultiGPU)
example.  This sample evaluates fair call price for a given set of European options using Monte Carlo approach.

This example is NVIDIA GPU accelerated, running an Apptainer container,
derived from the NVIDIA NGC container 
[(nvidia/gpu)](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/cuda)


# Getting Started
## Explore costs

In this tutorial, you use several billable components of Google Cloud. 

* Compute Engine
* Filestore
* Cloud Storage

You can evaluate the costs associated to these resources using the [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)

## Review basic requirements

Some basic items are required to get started.

* A Google Cloud Project with billing enabled.
* Basic familiarity with Linux and command-line tools.

For installed software, you need a few tools.

* [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and configured.
* [Terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli) installed.
* [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) installed.

These tools are already installed within the [Google Cloud Shell](https://shell.cloud.google.com/) and Cloud Shell Editor.

# Run CUDA Sample on Google Cloud

Running the CUDA Samples on Google Cloud using the Cluster Toolkit requires a few steps.

1. Install the Cluster Toolkit.
1. Build the infrastructure using the Cluster Toolkit. This will create an HPC cluster managed buy Slurm.
1. Build an Apptainer container.
2. Run the job on the cluster using Slurm.

## Install the Google Cloud Cluster toolkit
To install the Cluster Toolkit:

* Set up [Cloud Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/setup/configure-environment). During the setup ensure you enable all the required APIs, and permissions, and grant credentials to Terraform. Also ensure you clone and build the Cloud Cluster Toolkit repository in your local environment.
* Review the [best practices](https://cloud.google.com/cluster-toolkit/docs/tutorials/best-practices).

## Clone the Scientific Computing Example github repo
To get the sample blueprints clone the tutorial repository.
> These instructions assume you located the 
_Scientific Computing Examples_ repo in the \$HOME directory.
```
    cd ~
    git clone https://github.com/mmm/scientific-computing-examples
    cd ~/scientific-computing-examples/fsi/MonteCarloMultiGPU
```
## Run the Cluster Toolkit blueprint
Execute the `gcluster` command. If the Toolkit is installed in the \$HOME directory, the command is:
```
~/cluster-toolkit/gcluster deploy montecarlo_toolkit.yaml \
--skip-validators="test_apis_enabled"  --auto-approve \
  --vars project_id=$(gcloud config get project)
```
> You can move on to the next steps while the Toolkit is deploying the infrastructure.

## Build the Apptainer container containing the MonteCarloMultiGPU executable.
There are two steps to building our Apptainer containers. We use Cloud Build to build these containers.

1. Build a Apptainer "builder" Docker container
2. Build the Apptainer container with the MonteCarloMultiGPU executable

### Create the Apptainer builder container
We take a deeper look at the Apptainer container platform in the _Scientific Computing Examples_ repo. As part
of that, there are instructions on how to build the helper container. 
> These instructions assume you located the 
_Scientific Computing Examples_ repo in the \$HOME directory.
```
cd ~/scientific-computing-examples/apptainer/builders/cloud
gcloud builds submit . --config=cloudbuild.yaml 
```
This will take several minutes.

### Create the executable Apptainer container
With the "builder" container prepared, you can build the Apptainer 

```
cd ~/scientific-computing-examples/fsi/MonteCarloMultiGPU
gcloud builds submit . --config=montecarlo_cloudbuild.yaml
```
This will again take a few minutes.

> When complete, the container and the Slurm infrastructure should be in place.

## Connect to Slurm
The remaining steps in this tutorial will all be run on the Slurm cluster login node. 
SSH is used to connect to the login node, and `gcloud` offers an option for SSH connections.
```
gcloud compute ssh --zone "asia-northeast3-a" "mcslurm-login-001" --project $(gcloud config get project)
```
An alternative to SSH connection to the login node is to connect from the 
[Cloud Console](https://console.cloud.google.com/compute/instances). Click on the `SSH` link.

## Slurm batch file
To submit a job on Slurm, a Slurm Batch script must be created.

>> For convenience, the deployment created a Slurm batch job file to run the container.
```
cp /tmp/*.job .
ls *.job
```
## Create the Slurm batch file
Alternatively, you can create the batch file manually.  Use the `heredoc` below. Cut and paste
the follwing into your Slurm login terminal. 
```
tee montecarlo_slurm.job << JOB
#!/bin/bash
#SBATCH --job-name=MonteCarloMultiGPU
#SBATCH --partition=a2
#SBATCH --output=%3A/out.txt
#SBATCH --error=%3A/err.txt

export PROJECT_ID=$(gcloud config get-value project)
# Build SIF, if it doesn't exist
if [[ ! -f montecarlo.sif ]]; then
  export REPOSITORY_URL=oras://us-docker.pkg.dev
  apptainer remote login --username=oauth2accesstoken --password=$(gcloud auth print-access-token) \${REPOSITORY_URL}
  apptainer pull montecarlo.sif oras://us-docker.pkg.dev/${PROJECT_ID}/sifs/montecarlo:latest
fi
apptainer run --nv montecarlo.sif /bin/MonteCarloMultiGPU

JOB
```
This creates a Slurm batch file named montecarlo_slurm.job

## Submit the job
The command to submit a job with Slurm is [sbatch](https://slurm.schedmd.com/sbatch.html). 

Submit the job.
```
sbatch montecarlo_slurm.job
```
The command to see the jobs in the Slurm batch queue is [squeue](https://slurm.schedmd.com/squeue.html)
```
squeue
```
The output lists running and pending jobs.
```
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
                 6        a2 MonteCar drj_gcp_ CF       0:02      1 mcslurm-a2nodeset-0
```
## Review the output
As configured in the `montecarlo_slurm.job` file, the standard output of the Slurm job is directed to
`###/out.txt`, where `###` is the JOBID. When the job is complete, it will not be visible
in the  `squeue` output and the output files will be present.


You can use `head` to see the start of the output.
```
head 001/out.txt 
```
Shows:
```
==========
== CUDA ==
==========

CUDA Version 12.3.0

Container image Copyright (c) 2016-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.

This container image and its contents are governed by the NVIDIA Deep Learning Container License.

```

You can use `tail` to see the end of the output.
```
tail 001/out.txt 
```
Shows:
```
Options per sec.: 3646967.306854
main(): comparing Monte Carlo and Black-Scholes results...
Shutting down...
Test Summary...
L1 norm        : 4.780728E-04
Average reserve: 14.081840

NOTE: The CUDA Samples are not meant for performance measurements. Results may vary when GPU Boost is enabled.

Test passed
```
## Discussion

The tutorial demonstrated how to run a Monte Carlo pricing option simulation
using NVIDIA GPUs on Google Cloud. The infrastructure was deploye3d by the Cluster Toolkit,
and the NVIDIA container was deployed by Apptainer. 

Slurm was used as a workload manager. Simulation output was viewed in a text file.

# Clean up

To avoid incurring charges to your Google Cloud account for the resources used in this tutorial, either delete the project containing the resources, or keep the project and delete the individual resources.

## Destroy the HPC cluster

To delete the HPC cluster, run the following command:
```
~/cluster-toolkit/gcluster destroy namd-slurm --auto-approve
```
When complete you will see output similar to:

Destroy complete! Resources: xx destroyed.

**CAUTION**: This approach will destroy all content including the fine tuned model.

## Delete the project

The easiest way to eliminate billing is to delete the project you created for the tutorial.

To delete the project:

1. **Caution**: Deleting a project has the following effects:
    * **Everything in the project is deleted.** If you used an existing project for the tasks in this document, when you delete it, you also delete any other work you've done in the project.
    * **Custom project IDs are lost.** When you created this project, you might have created a custom project ID that you want to use in the future. To preserve the URLs that use the project ID, such as an **<code>appspot.com</code></strong> URL, delete selected resources inside the project instead of deleting the whole project.
2. If you plan to explore multiple architectures, tutorials, or quickstarts, reusing projects can help you avoid exceeding project quota limits.In the Google Cloud console, go to the <strong>Manage resources</strong> page. \
[Go to Manage resources](https://console.cloud.google.com/iam-admin/projects)
3. In the project list, select the project that you want to delete, and then click <strong>Delete</strong>.
4. In the dialog, type the project ID, and then click <strong>Shut down</strong> to delete the project.

