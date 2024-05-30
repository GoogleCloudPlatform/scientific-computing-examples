# Creating Custom VertexAI Workbench Instances for Scientific Machine Learning

Here are some example template snippets used to spin up Vertex AI Workbench
instances in Google Cloud.  This includes examples of how to customize those
instances once they're spun up as well as how to customize the images used to
create the instances if you have more persistent changes you'd like to use.

Please note that these are provided only as examples to help guide
infrastructure planning and are not intended for use in production. They are
deliberately simplified for clarity and lack significant details required for
production-worthy infrastructure implementation.

The goal here is to establish a base set of workbench instances and learn how
to customize them to your needs.

Beyond that we'll explore how these workbench instances might be used as
a "base of operations" for managing resources in Google Cloud.  From
a workbench, it can be useful to drive Vertex AI pipelines to train custom
models as well as use tools such as the HPC Toolkit (rebranded as the Google
Supercomputer Toolkit I think) to spin up and manage HPC clusters to run
simulation workloads on accelerated hardware.

![Typical compute cluster on GCP Architecture](media/typical-compute-cluster-architecture.png)

Here, we'll only focus on standing up a static cluster of standalone compute nodes
for testing instance types with other schedulers.  We focus on:

![standalone compute cluster on GCP Architecture](media/standalone-compute-cluster-architecture.png)

In this example, you'll create:
- A dedicated Identity and Access Management (IAM) **Service Account** w/ appropriate
  roles adopting a "Principle of least privilege" approach.
- A dedicated **isolated network** with no ingress traffic allowed.
- **VertexAI Workbench** instances.
- And then create and use **custom images** to make those workbench instances your own.


## Costs

If you run the example commands below, you will use billable components of
Google Cloud Platform, including:

- Compute Engine
- Cloud Monitoring
- Cloud Logging
- Cloud Build
- Cloud Artifact Registry
- Vertex AI Workbench Instances

as well as a selection of other services.

You can use the
[Pricing Calculator](https://cloud.google.com/products/calculator)
to generate a cost estimate based on your projected usage.

Check out the [Google Cloud Free
Program](https://cloud.google.com/free/docs/gcp-free-tier) for potential
credits for tutorial resources.

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

You need to enable Compute Engine and Vertex AI services as enabling these APIs
allows you to create the required resources.

[Enable Example Services](https://console.cloud.google.com/flows/enableapi?apiid=compute.googleapis.com,logging.googleapis.com,monitoring.googleapis.com,artifactregistry.googleapis.com,cloudbuild.googleapis.com)

compute.googleapis.com,
logging.googleapis.com,
monitoring.googleapis.com,
notebooks.googleapis.com,
artifactregistry.googleapis.com,
cloudbuild.googleapis.com,
cloudresourcemanager.googleapis.com,
cloudkms.googleapis.com
containerregistry.googleapis.com
iam.googleapis.com
iap.googleapis.com
    
Next, make sure the project you just created is selected in the top of the
Cloud Console.

Then open a Cloud Shell associated with the project you just created

[Launch Cloud Shell](https://console.cloud.google.com/?cloudshell=true)

It's important that the current Cloud Shell project is the one you just
created.  Verify that

```bash
echo $GOOGLE_CLOUD_PROJECT
```

shows that new project.

All example commands below run from this Cloud Shell.


## Example source

Get the source

```bash
git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples
cd custom-workbenches
```

All example commands below are relative to this particular example directory.

## Tools

We use [Terraform](terraform.io) for these examples and the latest version is
already installed in your GCP Cloudshell.


## Create some preliminary resources

Create a Service Account and a Customer-Managed Encryption Keys (CMEK) to use
when we create all of the compute resources used in this project:

```bash
cd terraform/setup
terraform init
terraform plan
terraform apply
```

The output of this command will display links for the Service Account and CMEK.
We'll need those in later steps.


## Create a tutorial network

Create a `tutorial` network dedicated to the compute cluster instead of using
the `default` network for the project we created.

```bash
cd terraform/network
terraform init
terraform plan
terraform apply
```

This creates a network with egress but no ingress rules. The output of this
command will display the names of the network and subnetwork created for the
tutorial.


## Create some storage volumes

NFS volumes are common in compute cluster scenarios.  Here we create them just
as an example as well as potentially providing convenience for infrastructure
development and testing.  E.g., shared home directories on compute nodes.

In this part of the example we'll need to use outputs from the `setup` steps 
to specific terraform variables in a `tfvars` file.

Change to the storage server example directory

```bash
cd ../storage
```

Copy over the template variables

```bash
cp storage.tfvars.example storage.tfvars
```

Edit `storage.tfvars` to set some missing variables.

You need to edit several fields:


### Edit the CMEK used to encrypt disks and storage

Uncomment
```terraform
# cmek_self_link = "projects/<project>/locations/global/keyRings/tutorial-keyring/cryptoKeys/tutorial-cmek"
```
and set this variable to the value output from the setup step above.


### Edit Service Account used for the various compute node types

Uncomment the following variables throughout the file
```terraform
# compute_node_service_account = "default"
```
and set the value of each to the value output from the setup step above.

Note the output IP addresses reported from the `apply`.

You could now use those terraform outputs to set terraform variables in the
next steps just like we did in this step.  However, we'll take a bit of
a shortcut in the next step and access outputs directly from the terraform
state for previous steps.


## Create a cluster of compute nodes

Create an example static cluster of compute nodes.

Change to the compute cluster example directory

```bash
cd terraform/compute-partition
```

Copy over the template variables

```bash
cp compute.tfvars.example compute.tfvars
```

Edit `compute.tfvars` to set some missing variables.

You need to edit several fields:


### Edit the CMEK used to encrypt disks and storage

Uncomment
```terraform
# cmek_self_link = "projects/<project>/locations/global/keyRings/tutorial-keyring/cryptoKeys/tutorial-cmek"
```
and set this variable to the value output from the setup step above.


### Edit Service Account used for the various compute node types

Uncomment the following variables throughout the file
```terraform
# controller_service_account = "default"
# login_node_service_account = "default"
# compute_node_service_account = "default"
```
and set the value of each to the value output from the setup step above.


### Spin up the compute nodes

Next spin up the cluster.
Still within the `compute-partition` example directory above, run

```bash
terraform init
terraform plan -var-file compute.tfvars
terraform apply -var-file compute.tfvars
```

and wait for the resources to be created.  This should only take a minute or two.




## Run a compute-intensive job

Once the cluster is up, you are ready to associate the compute nodes
to a scheduler and run jobs.

Since the cluster has no access to the outside world, the easiest way to
transfer files around is to use a login node. Without a "local" login node, it
might be easiest to transfer files to/from any compute node is to use Google
Cloud Storage (GCS).

Create a bucket in the Cloud Console, add files you need to that bucket, and
then copy them directly from any node in the cluster.

From a node, download any files from GCS using something like

```sh
gsutil ls gs://
gsutil ls gs://<my-cool-bucket-name>/
gsutil cp gs://<my-cool-bucket-name>/<some-filename> .
```

You can then extract and kick off jobs from there.


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

    [GO TO THE PROJECTS PAGE](https://console.cloud.google.com/cloud-resource-manager)

2. In the project list, select the project you want to delete and click Delete
   delete.
3. In the dialog, type the project ID, and then click Shut down to delete the
   project.

### Deleting resources using Terraform

Alternatively, if you added the tutorial resources to an _existing_ project, you
can still clean up those resources using Terraform.

From the `workbenches` sub-directory, run

```sh
terraform destroy
cd ../storage
terraform destroy
cd ../network
terraform destroy
```

...and then optionally,
```sh
cd ../setup
terraform destroy
```
to clean up the rest.

## What's next

There are so many exciting directions to take to learn more about what you've
done here!

Learn about what's new in
- [Cloud](https://cloud.google.com/)
- [Vertex AI with Gemini](https://cloud.google.com/vertex-ai/docs/start/introduction-unified-platform)
- [High Performance Computing (HPC) on GCP](https://cloud.google.com/solutions/hpc?hl=en)
- Scientific Machine Learning on Google Cloud

