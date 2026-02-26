# Running GROMACS


# Getting Started
## Explore costs

In this tutorial, you use several billable components of Google Cloud. 

* Compute Engine
* Filestore
* Cloud Storage

You can evaluate the costs associated to these resources using the [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)


[![Open in Cloud Shell (Gromacs)](https://gstatic.com/cloudssh/images/open-btn.svg)](https://shell.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https%3A%2F%2Fgithub.com%2FGoogleCloudPlatform%2Fscientific-computing-examples.git&cloudshell_image=us-central1-docker.pkg.dev%2Fai-infra-jrt-1%2Fnvidia-repo%2Fcloudshell-nextflow%3Alatest&cloudshell_working_dir=hcls/gromacs-on-slurm&cloudshell_tutorial=README.md)

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

# Run GROMACS on Google Cloud

Running the GROMACS platform on Google Cloud using the Cluster Toolkit requires a few steps.

## Clone the Scientific Computing Example repo
Clone the tutorial repository. If you used the "Open in Google Cloud Shell" button, this will already be cloned and you will be in the correct directory.

```
    git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples
    cd hcls/gromacs-on-slurm
```
## Run the Cluster Toolkit blueprint
Execute the `gcluster` command. If the Toolkit is installed in the \$HOME directory, the command is:

```
gcluster deploy gromacs-slurm.yaml \
--skip-validators="test_apis_enabled"  --auto-approve \
  --vars project_id=$(gcloud config get project)
```
## Connect to Slurm

>  The remainder of this tutorial is run on the Slurm login Node.

The remaining steps in this tutorial will all be run on the Slurm cluster login node. SSH is used to connect to the login node, and `gcloud` offers an option for SSH connections.
```
gcloud compute ssh --zone "us-central1-b" "gromacsslu-login-001" --project $(gcloud config get project) --tunnel-through-iap
```
> An easier alternative to SSH connection to the login node is to connect from the 

[Cloud Console](https://console.cloud.google.com/compute/instances). Click on the `SSH` link.

## Download sample configuration
To run GROMACS, configuration files are required. NVIDIA shares information for the APOA1 benchmark. Download the benchmark configuration. 
```
wget https://zenodo.org/record/3893789/files/GROMACS_heterogeneous_parallelization_benchmark_info_and_systems_JCP.tar.gz 
tar xf GROMACS_heterogeneous_parallelization_benchmark_info_and_systems_JCP.tar.gz 
cd GROMACS_heterogeneous_parallelization_benchmark_info_and_systems_JCP/stmv
```

## Convert Docker to Apptainer
[Apptainer](https://apptainer.org/) is recommended for HPC applications. The published 
[NVIDIA Docker Container](https://catalog.ngc.nvidia.com/orgs/hpc/containers/gromacs)
is easily convereted to Apptainer compatible formats.

`apptainer` has been previously installed on the cluster.

The `apptainer build` command will convert a docker container into apptainer format. The Slurm `sbatch` will
run this step if `gromacs.sif` is not present, so this step is optional since the `sbatch` file contains 
commands to download and convert the container.
```
apptainer build gromacs.sif docker:nvcr.io/hpc/gromacs:2023.2 
```
This may take 5 minutes.

## Slurm batch file
To submit a job on Slurm, a Slurm Batch script must be created.

## Create the Slurm batch file
Alternatively, you can create the batch file manually.  Use the `heredoc` below. Cut and paste
the follwing into your Slurm login terminal. 

```
tee gromacs.job << JOB
#!/bin/bash
#SBATCH --job-name=gromacs
#SBATCH --partition=g2x4
#SBATCH --output=%3A/out_%a.txt
#SBATCH --error=%3A/err.txt
#SBATCH --array=0
#SBATCH --gres=gpu:4 
#

# Build SIF, if it doesn't exist

echo "Running: "  ${dirs[$SLURM_ARRAY_TASK_ID]}
cd GROMACS_heterogeneous_parallelization_benchmark_info_and_systems_JCP/stmv
apptainer run --nv ~/gromacs.sif gmx mdrun -ntmpi 8 -ntomp 16 -nb gpu -pme gpu -npme 1 -update gpu -bonded gpu -nsteps 100000 -resetstep 90000 -noconfout -dlb no -nstlist 300 -pin on -v -gpu_id 0123  
JOB
```
This creates a Slurm batch file named gromacs.job

## Submit the job
The command to submit a job with Slurm is [sbatch](https://slurm.schedmd.com/sbatch.html). 

Submit the job.
```
sbatch gromacs.job
```

## Review the output
As configured in the `gromacs.job` file, the standard output of the Slurm job is directed to
`###/out.txt`, where `###` is the JOBID. When the job is complete, it will not be visible
in the  `squeue` output and the output files will be present.


You can use `head` to see the start of the output.
```
head 001/out*.txt 
```

# Clean up

To avoid incurring charges to your Google Cloud account for the resources used in this tutorial, either delete the project containing the resources, or keep the project and delete the individual resources.

## Destroy the HPC cluster

To delete the HPC cluster, run the following command:
```
~/cluster-toolkit/gcluster destroy gromacs-slurm --auto-approve
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


```
An alternative to SSH connection to the login node is to connect from the 
[Cloud Console](https://console.cloud.google.com/compute/instances). Click on the `SSH` link.

Once you are connected to the CRD VM, you must open a new window on the CRD page:

https://remotedesktop.google.com/headless

1. Click on "Begin": ![Begin](images/crd_1.png)
1. Then click on "Next": ![Next](images/crd_2.png)
1. Then click on "Authorize": ![Authorize](images/crd_3.png)
1. Finally, "Copy to Clipboard" for Debian: ![Copy](images/crd_4.png)

### Paste authentication string into CRD VM Shell

The content that was copied in the previous step should be pasted into the shell on the CRD VM:

![Paste](images/crd_5.png)

If successful, you will be prompted for a 6 digit PIN.

### Connect to the VM via CRD
With authentication established, you can connect to the VM via CRD. Open the webpage.

https://remotedesktop.google.com/access

![Connect](images/crd_6.png)

You can now see a full Linux WM interface. 

### Start the VMD application

The following steps will allow you to start the VMD application and visualize the
simulated molecule.

1. Select the "Terminal Emulator": <p/> ![terminal](images/vmd_1.png)
1. Type "vmd" in the terminal window: ![vmd](images/vmd_2.png)
1. The VMD UI is now visible: ![vmdui](images/vmd_3.png)
1. Select "New Molecule" from the "VMD Main" menu : ![newmol](images/vmd_4.png)
1. "Browse" to "apoa1_gpu" and select "apoa1.pdb". Click "Okay" then "Load": ![pdb](images/vmd_5.png)
1. "Browse" to select "custom_trajectory.dcd". Click "Okay" then "Load": ![trajectory](images/vmd_6.png)
1. Update the Graphics to reflect the image, "licorice" ... "protein": ![graphics](images/vmd_7.png)
1. Finally, click the "Play" button to view the animation: ![animate](images/vmd_8.png)
1. The animation: ![animate](images/vmd_9.png)



# Clean up

To avoid incurring charges to your Google Cloud account for the resources used in this tutorial, either delete the project containing the resources, or keep the project and delete the individual resources.

## Destroy the HPC cluster

To delete the HPC cluster, run the following command:
```
~/cluster-toolkit/gcluster destroy gromacs-slurm --auto-approve
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

