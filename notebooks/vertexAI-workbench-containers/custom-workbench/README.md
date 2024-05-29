# Create a custom workbench image


## Overview of steps

- create a project
- enable services
- create an image repository
- build a custom image and push it to the repository
- spin up workbench images from that custom image


## Notes

- This should work well from a cloudshell.  Your `gcloud` is already auth'd and
  `docker` is installed. The only concern is the size of the base workbench
  container images... they're _huge_.
- We'll first provide example `gcloud` commands that you can customize.  We can
  put together some example code hitting the APIs directly if that's more
  useful.


## Trying things out

### Create a vanilla workbench instance

Example command to create workbench instance:

```bash
ZONE="us-central1-c"
REPOSITORY="gcr.io/deeplearning-platform-release"
IMAGE="base-gpu.py310:latest"

gcloud notebooks instances create \
  --location="${ZONE}" \
  --container-repository="${REPOSITORY}" \
  --container-tag="${IMAGE}" \
  --no-public-ip \
  "mycustomworkbench-0"
```

Even though this only has internal IP addresses, you can still log into it
using the cloud console web page. It transparently uses Identity Aware Proxy
(IAP) to connect.  Note this might be blocked via org-level policies.

You can also ssh directly to the instance:
```bash
gcloud compute ssh mycustomworkbench-0
```
Note this access can also be limited using org-level policies.

Delete this workbench instance using `gcloud` commands similar to:
```bash
gcloud notebooks instances list
```
and
```bash
gcloud notebooks instances delete mycustomworkbench-0 --location us-central1-c
```


## Now customize your workbenches


### Create an image repo to keep your custom images

```bash
REGION="us-central1"
gcloud artifacts repositories create \
  --location=${REGION} \
  --repository-format="docker" \
  "mycustomimagerepo"
```


### Create a custom workbench image

Example `Dockerfile` to create a custom workbench image:

```Dockerfile
FROM gcr.io/deeplearning-platform-release/base-gpu.py310

RUN pip install -q flask
```

See [vertex-ai-samples](https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/community-content/alphafold_on_workbench/Dockerfile)
for an example of adding cuda-related tool updates and config.

Build your image locally with
```bash
docker build -t mycustomimage:latest .
```

Note that the `FROM` image is unfortunately _huge_!  You might be better off
using Cloud Build to build and push your image to your image repo without
having to download anything to your actual laptop.


### Push your new image to make it available for use

Push it up to `mycustomimagerepo`...



### Create a _custom_  workbench instance

Example command to create workbench instance:

```bash
LOCATION="us-central1-c"
REPOSITORY="gcr.io/mycustomimagerepo"
IMAGE="mycustomimage:latest"


gcloud notebooks instances create \
  --location="${LOCATION}" \
  --container-repository="${REPOSITORY}" \
  --container-tag="${IMAGE}" \
  --no-public-ip \
  "mycustomworkbench-0"
```

