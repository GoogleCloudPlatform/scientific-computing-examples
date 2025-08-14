# Example - Standalone EDA VMs

Lots of folks want to test various "shapes" of VM to determine the best number
of cores, memory, and storage for particular EDA jobs. Here are some example
template snippets used to spin up Google Cloud resources to run EDA workloads
on various sizes and shapes of standalone VMs. They provide quick and easy ways
to spin up the following test matrix of VMs for your own experiments. 

| Name | `machine-type` | Chipset | vCpus | Memory (GB) | Available Storage |
| --- | --- | --- | --- | --- | --- |
| eda-n2-0 | `n2-standard-2` | Cascade Lake | 2 | 8 | PersistentDisk, LocalSSD, NFS |
| eda-n2d-0 | `n2d-highmem-2` | EPYC Rome | 2 | 16 | PersistentDisk, LocalSSD, NFS |
| eda-c2-0 | `c2-standard-4` | Cascade Lake | 4 | 16 | PersistentDisk, LocalSSD, NFS |
| ... | ... | ... | ... | ... | ... |

You can adjust this to your own interests by adding different sizes and classes of
machine types `m2`, `e2`, etc. using the
[GCP machine type comparison](https://cloud.google.com/compute/docs/machine-types#machine_type_comparison)
for reference. You will need to check for availability in the region you're
intending to run in as well as potentially ask for more quota for certain
machine types.

The current scripts provided start the specified machines and mount the
various storage volumes that are created.

Machine types should be finalized after validation in production or
pre-production environment. Machine recommendations in this document are
provided to guide infrastructure planning. They are deliberately simplified for
clarity and lack significant details required for production-worthy
infrastructure implementation.


## Costs

If you run the example commands below, you will use billable components of
Google Cloud Platform, including:

- Compute Engine
- Cloud Filestore

You can use the
[Pricing Calculator](https://cloud.google.com/products/calculator)
to generate a cost estimate based on your projected usage.


## Before you begin

Start by opening
[https://console.cloud.google.com/](https://console.cloud.google.com/)
in a browser.

Create a new GCP Project using the
[Cloud Resource Manager](https://console.cloud.google.com/cloud-resource-manager).
The project you create is just for this example, so you'll delete it below
when you're done.

You will need to
[enable billing](https://support.google.com/cloud/answer/6293499#enable-billing)
for this project.

You will also need to enable the Compute Engine (GCE) service for this account

[Enable Example Services](https://console.cloud.google.com/flows/enableapi?apiid=compute.googleapis.com,file.googleapis.com,cloudresourcemanager.googleapis.com)
    
Next, make sure the project you just created is selected in the top of the
Cloud Console.

Then open a Cloud Shell associated with the project you just created

[Launch Cloud Shell](https://console.cloud.google.com/?cloudshell=true)

It's important that the current Cloud Shell project is the one you just
created.  Verify that

    echo $GOOGLE_CLOUD_PROJECT

shows that new project.

All example commands below run from this Cloud Shell.


## Example source

Get the source

    git clone https://github.com/GoogleCloudPlatform/eda-examples
    cd eda-examples

All example commands below are relative to this top-level directory of the
examples repo.


## Tools

We use [Terraform](terraform.io) for these examples and the latest version is
already installed in your GCP Cloudshell.


## Create a license server

Create an instance used to run a license manager in GCP.

    cd terraform/licensing
    terraform init
    terraform plan
    terraform apply

This creates an example instance and shows how license manager binaries and
dependencies can be installed using `provision.sh` during instance creation.


## Create NFS volumes

Create two NFS volumes using Google Cloud Filestore.  One for `/home` (3TB) and
one for `/tools` (3TB).

    cd ../storage
    terraform init
    terraform plan
    terraform apply

and wait for the resources to be created.  It can take a few minutes for the
volume creation to complete.


## Create a test matrix of standalone VMs

Next, spin up the following test matrix of VM configurations

| Name | `machine-type` | Chipset | vCpus | Memory (GB) | Available Storage |
| --- | --- | --- | --- | --- | --- |
| eda-n2-0 | `n2-standard-2` | Cascade Lake | 2 | 8 | PersistentDisk, LocalSSD, NFS |
| eda-n2d-0 | `n2d-highmem-2` | EPYC Rome | 2 | 16 | PersistentDisk, LocalSSD, NFS |
| eda-c2-0 | `c2-standard-4` | Cascade Lake | 4 | 16 | PersistentDisk, LocalSSD, NFS |

Change to the standalone compute example directory

    cd ../standalone-compute

and spin up the test VMs:

    terraform init
    terraform plan
    terraform apply

and wait for the resources to be created.

Edit `main.tf` to create your own test matrix on subsequent example runs.


## Log in and run a common test suite

Once the test nodes are up, you are ready to run various standalone jobs. Here,
we'll use the popular [Phoronix Test
Suite](https://www.phoronix-test-suite.com/) as an example standalone node test
platform.

For each VM, Log into that node

    gcloud compute ssh <vm_name> --zone <zone>

for example

    gcloud compute ssh eda-n2-0 --zone us-central1-f

At the prompt, install some dependencies for the Phoronix test suite

    sudo yum install -y wget php-cli php-xml bzip2

then download and install the Phoronix Test Suite

    wget https://phoronix-test-suite.com/releases/phoronix-test-suite-8.4.1.tar.gz
    tar xvfz phoronix-test-suite-8.4.1.tar.gz
    cd phoronix-test-suite
    sudo ./install-sh

You can then run

    phoronix-test-suite list-available-tests


## Run an EDA job

Here, we'll run an example open source functional verification regression
using an open source simulator (Icarus).

From each VM, install some dependencies for the verification tool-chain

    yum -y install iverilog tcsh glibc.i686 elfutils-libelf-devel perl-Bit-Vector

Next, download an example design project from

    wget https://github.com/PrincetonUniversity/openpiton/archive/openpiton-19-10-23-r13.tar.gz

Extract this

    tar xzvf openpiton-19-10-23-r13.tar.gz
    cd openpiton-openpiton-19-10-23-r13

Next you need to update the environment to set up the execution context:

- Set up the `PITON_ROOT` environment variable

    export PITON_ROOT=`pwd`

- Set up simulator home

    export ICARUS_HOME=/usr

- Source required settings

    source $PITON_ROOT/piton/piton_settings.bash

- And then you can

    sims -sim_type=icv -group=tile1_mini

  which will run the sims on the current node.
    

## Cleaning up

To avoid incurring charges to your Google Cloud Platform account for the
resources used in this tutorial:

### Delete the project using the GCP Cloud Console

The easiest way to clean up all of the resources used in this tutorial is
to delete the project that you initially created for the tutorial.

Caution: Deleting a project has the following effects:
- Everything in the project is deleted. If you used an existing project for
  this tutorial, when you delete it, you also delete any other work you've done
  in the project.
- Custom project IDs are lost. When you created this project, you might have
  created a custom project ID that you want to use in the future. To preserve
  the URLs that use the project ID, such as an appspot.com URL, delete selected
  resources inside the project instead of deleting the whole project.

1. In the GCP Console, go to the Projects page.

    GO TO THE PROJECTS PAGE

2. In the project list, select the project you want to delete and click Delete
   delete.
3. In the dialog, type the project ID, and then click Shut down to delete the
   project.

### Deleting resources using Terraform

Alternatively, if you added the tutorial resources to an _existing_ project, you
can still clean up those resources using Terraform.

From the `standalone-compute` sub-directory, run

    terraform destroy

then

    cd ../storage
    terraform destroy

and

    cd ../licensing
    terraform destroy


## What's next

There are so many exciting directions to take to learn more about what you've
done here!

- Infrastructure.  Learn more about
  [Cloud](https://cloud.google.com/),
  High Performance Computing (HPC) on GCP
  [reference architectures](https://cloud.google.com/solutions/hpc/) and 
  [posts](https://cloud.google.com/blog/topics/hpc).

