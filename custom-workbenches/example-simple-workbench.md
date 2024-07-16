# Creating VertexAI Workbench Instances for Scientific Machine Learning

Here are some example script snippets used to manage Vertex AI Workbench
instances in Google Cloud.  This includes examples of how spin them up and
then customize those instances once they're up and running.

In [another example](example-build-custom-workbench.md), we'll show how to
customize the images used to create the instances if you have more persistent
changes you'd like to use.

In this example, you'll create:
- A [NAT router](https://cloud.google.com/nat/docs/overview) to use private IPs
  and not require ingress traffic to access workbench instances.
- [VertexAI Workbench](https://cloud.google.com/vertex-ai/docs/workbench/instances/introduction)
  instances.

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

[Enable Example Services](https://console.cloud.google.com/flows/enableapi?apiid=compute.googleapis.com,logging.googleapis.com,monitoring.googleapis.com,notebooks.googleapis.com,artifactregistry.googleapis.com,cloudbuild.googleapis.com,cloudresourcemanager.googleapis.com,containerregistry.googleapis.com,iam.googleapis.com,iap.googleapis.com)

Note that some of these are needed in other examples but are included here so
you can just use one project for all of these "custom workbench" examples.

Next, make sure the project you just created is selected in the top of the
Cloud Console.

Then open a [Cloud Shell](https://cloud.google.com/shell) associated with the
project you just created.

[Launch Cloud Shell](https://console.cloud.google.com/?cloudshell=true)

It's important that the current Cloud Shell project is the one you just
created.  Verify that

```bash
echo $GOOGLE_CLOUD_PROJECT
```

shows that new project.

All example commands below run from this Cloud Shell.  They should also run
on any machine with the Google Cloud SDK installed and auth'd for your org,
just be careful to export the `GOOGLE_CLOUD_PROJECT` environment variable
if you're not using Cloud Shell.


## Example source

The commands in this example are captured as scripts in a repo. You can
cut/paste into your cloudshell instance or you can optionally just clone this
repo into your cloudshell instance and run the scripts from there.

Get the source

```bash
git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples
cd custom-workbenches
```
All example commands below are relative to this particular example directory.


## Tools

We use [gcloud](https://cloud.google.com/cli?hl=en) for these examples and the
latest version is already installed in your GCP Cloudshell.


## Create some preliminary resources

The following step will create a dedicated
[NAT router](https://cloud.google.com/nat/docs/overview)
so we can use instances with internal-only IPs in the `default` network for our
workbenches.

```bash
REGION="us-central1"
NETWORK="default"

gcloud compute routers create nat-router \
    --network "${NETWORK}" \
    --region "${REGION}"

gcloud compute routers nats create nat-config \
    --router-region "${REGION}" \
    --router nat-router \
    --nat-all-subnet-ip-ranges \
    --auto-allocate-nat-external-ips
```

It's best practice to create a dedicated network for the task at hand and not
use the `default` network for anything.  For simplicity, we'll just use the
`default` network but then only use internal IP addresses for these tutorials.


## Create a Workbench instance

Example command to create workbench instance:

```bash
ZONE="us-central1-c"

gcloud workbench instances create \
  --location="${ZONE}" \
  --disable-public-ip \
  myworkbench-0
```

Spin up a workbench using these default settings and wait for the resources to
be created.  This typically takes a few minutes.


## Open JupyterLab

Open the
[Cloud Console Vertex AI Workbenches View](https://console.cloud.google.com/vertex-ai/workbench/instances)
and click on the `Open JupyterLab` link for the `workbench-0`  workbench instance.

Alternatively, you can just grab the Proxy URI from
```bash
ZONE="us-central1-c"

gcloud workbench instances describe \
  --location ${ZONE} \
  myworkbench-0 
```
and open that in a new browser tab.


## Use JupyterLab to manage other Google Cloud resources

Note you can open a terminal pane in JupiterLab and use various tools
to manage Google Cloud infrastructure.

Things we can do from the JupyterLab interface:
- `gcloud` from a workbench to manage Vertex AI pipelines.
- use the kubeflow python APIs from within a notebook to manage Vertex AI
  pipelines.
- Use the [HPC Toolkit](https://cloud.google.com/hpc-toolkit/docs/overview) to
  spin up a slurm cluster.
- Use any Docker-based tooling as Docker is already installed.


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

### Deleting resources using `gcloud`

Alternatively, if you added the tutorial resources to an _existing_ project, you
can still clean up those resources using gcloud commands.

To clean up any workbenches, list them
```bash
gcloud workbench instances list --location <zone>
```
and then
```bash
gcloud workbench instances delete <workbench-name> --location <zone>
```
to delete a workbench.  Note that this command is picky about "location"
so use the zone you created them in before.  It doesn't roll zonal resources
up into a "regional" instances list.

To clean up your network resources, list them
```bash
gcloud compute routers list
```
and then
```bash
gcloud compute routers delete nat-router
```
to delete the NAT config and corresponding NAT router we created above.

Note that you might want to keep the project and the network config for
the [next example](example-build-custom-workbench.md) in this series.


## What's next

See the custom workbenches [README](README.md) for more examples.

