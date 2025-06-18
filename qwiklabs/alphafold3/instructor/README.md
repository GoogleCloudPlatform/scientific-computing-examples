# Running Alphafold3 inference on Slurm with Google Cloud Cluster Toolkit

![Alphafold3](images/alphafold3.jpeg)

This guide provides instructions on how to run
[Alphafold3](https://blog.google/technology/ai/google-deepmind-isomorphic-alphafold-3-ai-model),
inference using the
[Google Cloud Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/setup/configure-environment),
on [Slurm](https://slurm.schedmd.com/overview.html)

# Getting Started
## Explore costs

In this tutorial, you use several billable components of Google Cloud. 

* Compute Engine
* Filestore
* Cloud Storage
* Cloud Build

You can evaluate the costs associated to these resources using the [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)

## Obtaining Model Parameters

The Alphafold3 Github repository contains all necessary code for AlphaFold 3 inference. 
This repository builds the containers used in this tutorial.
To request access to the AlphaFold 3 model parameters, please complete
[this form](https://forms.gle/svvpY4u2jsHEwWYS6). Access will be granted at
Google DeepMind’s sole discretion. We will aim to respond to requests within 2–3
business days. You may only use AlphaFold 3 model parameters if received
directly from Google. Use is subject to these
[terms of use](https://github.com/google-deepmind/alphafold3/blob/main/WEIGHTS_TERMS_OF_USE.md).

## Review basic requirements

Some basic items are required to get started.

* A Google Cloud Project with billing enabled.
* Basic familiarity with Linux and command-line tools.

For installed software, you need a few tools.

* [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and configured.
* [Terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli) installed.
* [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) installed.

These tools are already installed within the [Google Cloud Shell](https://shell.cloud.google.com/) and Cloud Shell Editor.

## Install the Google Cloud Cluster Toolkit

To run the remainder of this tutorial, you must:

* Set up [Cloud Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/setup/configure-environment). During the setup ensure you enable all the required APIs, and permissions, and grant credentials to Terraform. Also ensure you clone and build the Cloud Cluster Toolkit repository in your local environment.
* Review the [best practices](https://cloud.google.com/cluster-toolkit/docs/tutorials/best-practices).

# Build the Alphafold3 containers
We build the Alphafold3 docker container and from that we create an
[Apptainer](https://apptainer.org/)
container. Apptainer containers are better suited to run on 
[Slurm](https://slurm.schedmd.com/overview.html).

In this tutorial we make use of
[Google Cloud Build](https://cloud.google.com/build/docs/overview). This ensures
that the build environment is consistent and does not interfere with local
configurations.

## Create an Apptainer Cloud Builder
Google Cloud provides a large number of
[Cloud Builders](https://cloud.google.com/build/docs/cloud-builders)
but Apptainer is not yet one of them. For this reason, we can easily build our own.
Two steps are required.

1. Clone the [scientific-computing-examples](https://github.com/GoogleCloudPlatform/scientific-computing-examples.git) repository:
```
git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples.git
cd apptainer/builders/cloud/buildstep
```
2. Run the Cloud Build command:
```
gcloud builds submit --config cloudbuild.yaml .
```
This will take several minutes.  The end of the output will look something like:

```
DONE
-------------------------------------------------------------------------------------------------------------------------------------------------------
ID                                    CREATE_TIME                DURATION  SOURCE                                                                                           IMAGES                                        STATUS
7e2e8314-d4b3-4366-a1d0-529c7585f4e5  2023-11-09T16:30:30+00:00  1M7S      gs://myproject_cloudbuild/source/1699547428.666519-093b1756b5e74774b02660be6fe56e81.tgz  gcr.io/myproject/apptainer (+1 more)  SUCCESS

```
This Apptainer builder will be used in subsequent steps.

## Build the Alphafold3 container
The Alphafold3 container requires a larger Cloud Build environment. For this we create a custom
Build Pool. The `gcloud` command to create a custom build pool is shown below.
```
gcloud builds worker-pools create mypool --region=us-central1 --worker-disk-size=100 \
--worker-machine-type=e2-highmem-8
```
With a custom build pool created the Cloud Build command is below.
```
PROJECT_ID=$(gcloud config get-value project)
gcloud builds submit --region=us-central1 --config=apptainer_cloudbuild.yaml --worker-pool=projects/${PROJECT_ID}/locations/us-central1/workerPools/mypool
```
* This build can take several minutes. You can follow the build progress
[in the console](https://console.cloud.google.com/cloud-build/builds).
* When the build is complete you will be able to see the containers
[in the console](https://console.cloud.google.com/artifacts).

There is an Alphafold3 Docker container (under `docker`)
and an Apptainer container (under `sifs`).

You are now ready to create the Slurm HPC cluster using Cluster Toolkit

# Create the Slurm HPC cluster
Assuming you installed the Cluster Toolkit in the `root` directory, the commands are shown below.
Please update the commands with the correct path if necessary.

Execute the `gcluster` command. If the Toolkit is installed in the \$HOME directory, the command is:

```
~/cluster-toolkit/gcluster deploy af3_slurm_cluster_tk.yaml.yaml \
--skip-validators="test_apis_enabled"  --auto-approve \
  --vars project_id=$(gcloud config get project)
```
This will take several minutes. Once complete:

> You can see the created VM instances [in the console](https://console.cloud.google.com/compute/instances).

## Connect to Slurm
> IMPORTANT: The remaining steps in this tutorial will all be run on the Slurm cluster login node.

SSH is used to connect to the login node, and `gcloud` offers an option for SSH connections.
```
gcloud compute ssh --zone "us-central1-a" "af3slurm-login-001" --project $(gcloud config get project)
```
An alternative to SSH connection to the login node is to connect from the 
[Cloud Console](https://console.cloud.google.com/compute/instances). Click on the `SSH` link.

Once you login to the Slurm login node, you need to ensure that the Slurm configuration has completed. 
The `sinfo` command will ensure Slurm is ready.
```
sinfo
```
When Slurm is ready, the output should be something like:
```
PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
a2           up   infinite     20  idle~ af3slurm-a2nodeset-[0-19]
compute*     up   infinite     20  idle~ af3slurm-computenodeset-[0-19]
g2           up   infinite     20  idle~ af3slurm-g2nodeset-[0-19]
```
# Configure required data
To run Alphafold 3 there are several databases and the model parameters required.
## Download required databases
Several databases are required for Alphafold3. They must be downloaded from DeepMind's Google
Cloud Storage bucket. We recommend using a Slurm job to run the `fetch_databases.sh` script.

For convenience, we have created a Slurm job file to run the script. For your convenience, the 
Cluster Toolkit copied the files over to your `/tmp` directory. Copy them to your home directory.
```
cp /tmp/fetch_databases* .
```
The Slurm job can then be started.
```
sbatch fetch_databases_slurm.job
```
You can view the job running via the `squeue` Slurm command.
```
squeue
```
The output will list the job.
```
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
                14   compute fetch_da drj_gcp_ CF       0:01      1 af3slurm-computenodeset-0
```
When complete, `squeue` will no longer list the active job.
> This job must finish before you can run Alphafold 3.

## Obtain model parameters
As indicated above, the model parameters must be requested from DeepMind.

When you obtain the model parameters they will be in a Zstandard compressed file.
```
af3.bin.zst
```
Uncompress the model parameters.
```
unzstd -d af3.bin.zst
```
Move the uncompressed file a directory in your home directory (`~/models`).
```
mv af3.bin ~/models
```

## Copy the JSON input file
For convenience, we have uploaded the JSON input file to the `/tmp` directory on your VM. Copy it
to your home directory.
```
cp /tmp/fold_input.json .
```

# Run Alphafold 3 end to end

With all the required components in place, you are ready to run a Slurm job that runs Alphafold 3.
The job is run using the Apptainer container you built at an earlier step. For convenience, we uploaded
as Slurm job file to your `/tmp` directory. Copy it to your home directry.
```
cp /tmp/af3_slurm.job .
```
##
Submit the job to Slurm
```
sbatch af3_slurm.job
```
You can verify the job is running using `squeue`.
```
squeue
```
The output will list the job.
```
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
                15        g2 alphafol drj_gcp_ CF       0:02      1 af3slurm-g2nodeset-0
```
This takes about 40 minutes to complete on the L4 GPUs provisioned in this example.  

This job runs the "Data Pipeline" and the "Inference" steps of Alphafold 3. 

Output will be located in a directory `out_###` where `###` is the JOBID used by Slurm


# Discussion

The tutorial demonstrated how to run Deepmind's Alphafold3 on Google Cloud using Apptainer
containers on an HPC GPU cluster using the Slurm workload manager.

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

