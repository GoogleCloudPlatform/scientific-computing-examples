# Cluster Toolkit Docker build

This repository contains a Cloud Build YAML file to create a Docker image.
This Docker image will be used by other processes (gcloud builds) to create infrastructure using
the Google Cloud Cluster Toolkit.

## Run Cloud build

In this directory, run the command:

`gcloud builds submit --config cloudbuild.yaml --no-source`

The successful output should end with something like this:

```
6c30f8129230: Pushed
9f7564cbf64c: Pushed
latest: digest: sha256:b599231573707dbfe371ce9534fc98f2898a7efb827adfef0d4f87786523f927 size: 3679
DONE
```
You can run it as:
```
gcloud auth configure-docker gcr.io
docker run gcr.io/ai-infra-jrt-2/gcluster-builder:
```
The output should be:
```
gHPC provides a flexible and simple to use interface to accelerate
HPC deployments on the Google Cloud Platform.

Usage:
  gcluster [flags]
  gcluster [command]

Available Commands:
  completion     Generate completion script
  create         Create a new deployment.
  deploy         deploy all resources in a Toolkit deployment directory.
  destroy        destroy all resources in a Toolkit deployment directory.
  expand         Expand the Environment Blueprint.
  export-outputs Export outputs from deployment group.
  help           Help about any command
  import-inputs  Import input values from previous deployment groups.

Flags:
  -h, --help       help for gcluster
      --no-color   Disable colorized output.
  -v, --version    version for gcluster

Use "gcluster [command] --help" for more information about a command.
```