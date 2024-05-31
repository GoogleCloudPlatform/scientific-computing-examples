# Creating Custom VertexAI Workbench Instances for Scientific Machine Learning

Here are some example template snippets used to manage Vertex AI Workbench
instances in Google Cloud.  This includes examples of how spin them up and
then customize those instances once they're up and running.

In [another example](example-build-custom-workbench.md), we'll show how to
customize the images used to create the instances if you have more persistent
changes you'd like to use.

In this example, you'll create:
- A dedicated Identity and Access Management (IAM) **Service Account** w/ appropriate
  roles adopting a "Principle of least privilege" approach.
- A dedicated **isolated network** with no ingress traffic allowed.
- **VertexAI Workbench** instances.

Please note that these are provided only as examples to help guide
infrastructure planning and are not intended for use in production. They are
deliberately simplified for clarity and lack significant details required for
production-worthy infrastructure implementation.


## Costs

If you run the example commands below, you will use billable components of
Google Cloud Platform, including:

- Compute Engine
- Vertex AI Workbench Instances

as well as a selection of other services for things like monitoring and
logging.

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

TODO fix this mess
    
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

TODO combine setup + network into a single step

We'll use a Google Cloud Storage bucket as a backend to store the Terraform
state for the resources created in this set of tutorials.

Create a GCS bucket
```bash
gcloud storage buckets create gs://<yourcoolbucketname>
```
and then
```bash
cp terraform/backend.conf.example terraform/backend.conf
```
and edit the `terraform/backend.conf` file to add the name of your bucket.

Create a Service Account and some IAM resources to use when we create all of
the compute resources used in this project:

```bash
cd terraform/setup
terraform init -backend-config ../backend.conf
terraform plan
terraform apply
```

Next create a dedicated `tutorial` network for our workbenches.

We're not simply using the `default` network for the project because it's best
practice to only ever use internal IP addresses, and creating a dedicated
`tutorial` network keeps all the NAT gateway and firewall rules in one place
that's easier to manage than adding bits and pieces to the `default` network.

```bash
cd terraform/network
terraform init -backend-config ../backend.conf
terraform plan
terraform apply
```

This creates a network with egress but no ingress rules. The output of this
command will display the names of the network and subnetwork created for the
tutorial.


## Create a Workbench instance

Create...
TODO

Change to the workbenches example directory

```bash
cd terraform/workbenches
```

and spin up a workbench using the default python image

```bash
terraform init -backend-config ../backend.conf
terraform plan
terraform apply
```

and wait for the resources to be created.  This typically takes a few minutes.


## Open JupyterLab

Open the [Cloud Console Vertex AI Workbenches View](https://console.cloud.google.com/)

![Picture of the Cloud Console Vertex AI Workbenches View](media/cloud-console-vertexai-workbenches-view.png)

and click on the `Open JupyterLab` link for the `workbench-0`  workbench instance.

Alternatively, you can just grab the Proxy URI from

```bash
gcloud workbenches describe <workbench-name> --location <zone>
```

(E.g., `gcloud workbenches describe workbench-0 --location us-central1-c`)
and open that in a new browser tab.


## Customize JupyterLab

Dark mode!  :-)

Keep in mind that any customizations you make will survive stopping and
starting the workbench instance, but will be blown away when you destroy the
workbench instance.

If you want to persist changes beyond the life of a single workbench instance,
you'll need to
[create your own workbench image](example-build-custom-workbench.md)
to use for your workbench instances.


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
```

...and then optionally,
```sh
cd ../network
terraform destroy
cd ../setup
terraform destroy
```
to clean up the rest.

Hint, keep those around for the next tutorial.


## What's next

See the custom workbenches [README](README.md) for more examples.

