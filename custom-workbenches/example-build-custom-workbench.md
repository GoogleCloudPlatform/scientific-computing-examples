# Creating Custom VertexAI Workbench Instances for Scientific Machine Learning

Here are some example script snippets used to manage Vertex AI Workbench
instances in Google Cloud.  In [a previous example](example-simple-workbench.md),
we covered the basics of how to spin up Vertex AI Workbench instances and
customize them once they're up and running. Here we'll show how to make Vertex
AI Workbench instances your own by customizing the images used to create the
instances if you have more persistent changes you'd like to make.

In this example, you'll create:
- A dedicated [Artifact Registry](https://cloud.google.com/artifact-registry)
  to store your custom container images.
- A dedicated Identity and Access Management (IAM)
  [Service Account](https://cloud.google.com/iam/docs/service-account-overview)
  with appropriate roles adopting a "Principle of least privilege" approach
  used to build images.
- [VertexAI Workbench](https://cloud.google.com/vertex-ai/docs/workbench/instances/introduction)
  instances.
- And then you'll create and use
  [custom workbench container images](https://cloud.google.com/vertex-ai/docs/workbench/instances/create-custom-container)
  to make your VertexAI Workbench instances your own.

You can reuse the same project, service account, and network infrastructure
from the previous example if it's still up and running.

Please note that these are provided only as examples to help guide
infrastructure planning and are not intended for use in production. They are
deliberately simplified for clarity and lack significant details required for
production-worthy infrastructure implementation.


## Costs

If you run the example commands below, you will use billable components of
Google Cloud Platform, including:

- Compute Engine
- Cloud Artifact Registry
- Cloud Build
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

[Launch CloudShell](https://console.cloud.google.com/?cloudshell=true)

It's important that the current Cloud Shell project is the one you just
created.  Verify that

```bash
echo $GOOGLE_CLOUD_PROJECT
```

shows that new project.

All example commands below run from this Cloud Shell.


## Example source

The commands in this example are captured as scripts in a repo. You can
cut/paste commands into your cloudshell instance or you can optionally just
clone this repo into your cloudshell instance and run the scripts from there.

Get the source

```bash
git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples
cd custom-workbenches
```

All example commands below are relative to this particular example directory.

## Tools

We use [gcloud](https://cloud.google.com/cli?hl=en) for these examples and the
latest version is already installed in your GCP CloudShell.


## Build a custom workbench image


### Create an image repo to keep your custom images

```bash
REGION="us-central1"
REPO_NAME="mycustomimagerepo"
gcloud artifacts repositories create \
  --location=${REGION} \
  --repository-format="docker" \
  ${REPO_NAME}
```

The resulting registry URL should take the form:
`<region>-<format>.pkg.dev/<project>/<repo_name>`.

E.g.,
```
us-central1-docker.pkg.dev/mycoolprojectname/mycustomimagerepo
```

You can look it up using

```bash
REGION="us-central1"
REPO_NAME="mycustomimagerepo"
gcloud artifacts repositories describe \
  --location=${REGION} \
  ${REPO_NAME}
```

### Create a custom workbench image using docker

Example `Dockerfile` to create a custom workbench image:

```Dockerfile
FROM gcr.io/deeplearning-platform-release/workbench-container:latest

RUN pip install -q flask
```

See [vertex-ai-samples](https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/community-content/alphafold_on_workbench/Dockerfile)
for an example of adding cuda-related tool updates and config.


### How to build your new image

Note that you have some options for building this container image.

You can build your custom image using the cloudshell instance we've been using
for this tutorial.  It takes quite a while because the upstream `FROM`
image is unfortunately just huge.

If you're using a local environment, you'll need `gcloud` and Docker installed.
Then you can enable the helper to allow docker to auth against the repository
you created above using

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

If you're just going to build within CloudShell, this is already done for you.


### Build your image using CloudShell or a local Docker environment

```bash
docker build -t us-central1-docker.pkg.dev/mycoolprojectname/mycustomimagerepo/mycustomimage:latest .
```

### Push your new image to make it available for use

```bash
docker push us-central1-docker.pkg.dev/mycoolprojectname/mycustomimagerepo/mycustomimage:latest
```


### Build your image using CloudBuild

Another option is to simply use [Cloud Build](https://cloud.google.com/build)
to build and push your image to your image repo.  We'll cover that example
next, but feel free to skip straight to spinning up a new workbench using your
custom image once you have it built (and pushed!) whichever route you've
chosen.


### Alternatively - Create a custom workbench image using Cloud Build

First, add a couple of roles to the default CloudBuild Service Account:

```bash
CLOUD_BUILD_ACCOUNT=$(gcloud projects get-iam-policy ${GOOGLE_CLOUD_PROJECT} --filter="(bindings.role:roles/cloudbuild.builds.builder)"  --flatten="bindings[].members" --format="value(bindings.members[])")

gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} --member $CLOUD_BUILD_ACCOUNT --role roles/compute.instanceAdmin
gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} --member $CLOUD_BUILD_ACCOUNT --role roles/iam.serviceAccountUser
gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} --member $CLOUD_BUILD_ACCOUNT --role roles/iap.tunnelResourceAccessor
gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} --member $CLOUD_BUILD_ACCOUNT --role roles/compute.admin
```

We'll still use the same `Dockerfile`, but now we'll add a cloud build config
file `cloudbuild.yaml` that looks like
```yaml
steps:
- name: 'gcr.io/cloud-builders/docker'
    args: [ 'build', '-t', '${_IMAGE_URI}:${_IMAGE_TAG}', '.' ]
- name: 'gcr.io/cloud-builders/docker'
  args: [ 'push', '${_IMAGE_URI}:${_IMAGE_TAG}' ]
images: [ '${_IMAGE_URI}:${_IMAGE_TAG}' ]
```
Note that this `cloudbuild.yaml` and a basic `Dockerfile` can be found in the
accompanying repo in `images/mycustomimage/`.

Kick off a build in the cloud with
```
REGION="us-central1"
IMAGE_URI="us-central1-docker.pkg.dev/mycoolprojectname/mycustomimagerepo/mycustomimage"
IMAGE_TAG="latest"

gcloud builds submit . \
  --region ${REGION} \
  --substitutions="_IMAGE_URI=${IMAGE_URI},_IMAGE_TAG=${IMAGE_TAG}"
```

### Create a custom workbench instance using the image we just pushed

Example command to create workbench instance using the image we pushed above:

```bash
ZONE="us-central1-c"
IMAGE_URI="us-central1-docker.pkg.dev/mycoolprojectname/mycustomimagerepo/mycustomimage"
IMAGE_TAG="latest"

gcloud workbench instances create \
  --location="${ZONE}" \
  --container-repository="${IMAGE_URI}" \
  --container-tag="${IMAGE_TAG}" \
  --metadata="notebook-disable-root=TRUE" \
  --disable-public-ip \
  "mycustomworkbench-0"
```

See the
[command reference](https://cloud.google.com/sdk/gcloud/reference/workbench/instances/create)
for available options.


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

To clean up your network resources and container image builds / artifacts, it's
easiest to just delete the project as it shows in the previous section.


## What's next

See the custom workbenches [README](README.md) for more examples.
