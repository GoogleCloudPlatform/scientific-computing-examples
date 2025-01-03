# Running LAMMPS Benchmark using GPUs with Google Cloud Cluster Toolkit

![](images/lammps.png)

This guide provides instructions on how to run [LAMMPS](https://www.lammps.org/), a molecular dynamics simulation program, on GPUs using the [Google Cloud Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/setup/configure-environment), running the [NVIDIA LAMMPS Container](https://catalog.ngc.nvidia.com/orgs/hpc/containers/lammps) on [Slurm](https://slurm.schedmd.com/overview.html).


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

## Install the Google Cloud Cluster toolkit

To run the remainder of this tutorial, you must:

* Set up [Cloud Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/setup/configure-environment). During the setup ensure you enable all the required APIs, and permissions, and grant credentials to Terraform. Also ensure you clone and build the Cloud Cluster Toolkit repository in your local environment.
* Review the [best practices](https://cloud.google.com/cluster-toolkit/docs/tutorials/best-practices).

# Run  on Google Cloud

Running the  platform on Google Cloud using the Cluster Toolkit requires a few steps.

## Clone the Scientific Computing Example repo
Clone the tutorial repository.
```
    git clone https://github.com/mmm/scientific-computing-examples
    cd hcls/lammps-on-slurm
```
## Run the Cluster Toolkit blueprint
Execute the `gcluster` command. If the Toolkit is installed in the \$HOME directory, the command is:

```
~/cluster-toolkit/gcluster deploy lammps-slurm.yaml \
--skip-validators="test_apis_enabled"  --auto-approve \
  --vars project_id=$(gcloud config get project)
```
## Connect to Slurm
The remaining steps in this tutorial will all be run on the Slurm cluster login node. SSH is used to connect to the login node, and `gcloud` offers an option for SSH connections.
```
gcloud compute ssh --zone "asia-northeast3-a" "slurm-slurm-login-001" --project $(gcloud config get project)
```
An alternative to SSH connection to the login node is to connect from the 
[Cloud Console](https://console.cloud.google.com/compute/instances). Click on the `SSH` link.
## Download sample configuration
To run , configuration files are required. NVIDIA shares information for the APOA1 benchmark. Download the benchmark configuration.
```
wget -O - https://gitlab.com/NVHPC/ngc-examples/raw/master//3.0/get_apoa1.sh | bash
```
## Convert Docker to Apptainer
[Apptainer](https://apptainer.org/) is recommended for HPC applications. The published 
[NVIDIA Docker Container](https://catalog.ngc.nvidia.com/orgs/hpc/containers/)
is easily convereted to Apptainer compatible formats.

`apptainer` has been previously installed on the cluster.

The `apptainer build` command will convert a docker container into apptainer format.
```
export _TAG=3.0-beta5
apptainer build / docker://nvcr.io/hpc/:$_TAG 
```
This may take 5 minutes.

## Create the Slurm batch file
To submit a job on Slurm, a Slurm Batch script can be created.  Use the `heredoc` below. Cut and paste the follwing into your Slurm login terminal. 

```
tee lammps.job << JOB
#!/bin/bash

#SBATCH --nodes=2
#SBATCH --ntasks=8
#SBATCH --partition=a2
#SBATCH --ntasks-per-socket=4
#SBATCH --time 00:10:00
#SBATCH --output=%3A/out.txt
#SBATCH --error=%3A/err.txt
set -e; set -o pipefail

# Download input file, if not found
if [[ ! -f in.lj.txt ]]; then
  wget https://www.lammps.org/inputs/in.lj.txt
fi

# Build SIF, if it doesn't exist
export LAMMPS_TAG=patch_15Jun2023
if [[ ! -f lammps.sif ]]; then
  apptainer build lammps.sif docker://nvcr.io/hpc/lammps:\$LAMMPS_TAG
fi

readonly gpus_per_node=\$((\$SLURM_NTASKS / \$SLURM_JOB_NUM_NODES  ))

echo "Running Lennard Jones 8x4x8 example on \${SLURM_NTASKS} GPUS..."
srun --mpi=pmi2 \
apptainer run --nv lammps.sif \
lmp -k on g \${gpus_per_node} -sf kk -pk kokkos cuda/aware on neigh full comm device binsize 2.8 -var x 8 -var y 8 -var z 8 -in in.lj.txt

JOB
```
This creates a Slurm batch file named lammps.job

```
tee in.lj.txt << INLJ
# 3d Lennard-Jones melt

variable  x index 1
variable  y index 1
variable  z index 1

variable  xx equal 20*\$x
variable  yy equal 20*\$y
variable  zz equal 20*\$z

units    lj
atom_style  atomic

lattice    fcc 0.8442
region    box block 0 \${xx} 0 \${yy} 0 \${zz}
create_box  1 box
create_atoms  1 box
mass    1 1.0

velocity  all create 1.44 87287 loop geom

pair_style  lj/cut 2.5
pair_coeff  1 1 1.0 1.0 2.5

neighbor  0.3 bin
neigh_modify  delay 0 every 20 check no

fix    1 all nve

run    100
INLJ

## Submit the job
The command to submit a job with Slurm is [sbatch](https://slurm.schedmd.com/sbatch.html). 

Submit the job.
```
sbatch lammps.job
```
The command to see the jobs in the Slurm batch queue is [squeue](https://slurm.schedmd.com/squeue.html)
```
squeue
```
The output lists running and pending jobs.
```
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
                 6        a2 lammps drj_gcp_ CF       0:02      1 lammpsslurm-a2nodeset-0
```
## Review the output
As configured in the `lammps.job` file, the standard output of the Slurm job is directed to
`###_out.txt`, where `###` is the JOBID. When the job is complete, it will not be visible
in the  `squeue` output and the output files will be present.


You can use `head` to see the start of the output.
```
head out_001.txt 
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
tail out_001.txt 
```
Shows:
```
WRITING EXTENDED SYSTEM TO OUTPUT FILE AT STEP 10000
WRITING COORDINATES TO OUTPUT FILE AT STEP 10000
The last position output (seq=-2) takes 0.030 seconds, 0.000 MB of memory in use
WRITING VELOCITIES TO OUTPUT FILE AT STEP 10000
The last velocity output (seq=-2) takes 0.026 seconds, 0.000 MB of memory in use
====================================================

WallClock: 13.387387  CPUTime: 13.058638  Memory: 0.000000 MB
[Partition 0][Node 0] End of program
```
## Discussion

The tutorial demonstrated how to run the  molecular dynamics IPOA1 benchmark 
using NVIDIA GPUs on Google Cloud. The infrastructure was deploye3d by the Cluster Toolkit,
and the NVIDIA container was deployed by Apptainer. 

Slurm was used as a workload manager. Simulation output was viewed in a text file.

# Clean up

To avoid incurring charges to your Google Cloud account for the resources used in this tutorial, either delete the project containing the resources, or keep the project and delete the individual resources.

## Destroy the HPC cluster

To delete the HPC cluster, run the following command:
```
~/cluster-toolkit/gcluster destroy lammps-slurm --auto-approve
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

