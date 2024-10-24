# Apptainer Enabled Slurm Clusters

The [Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/overview) streamlines the definition and deployment of HPC Systems via _blueprints_ that it uses to generate and deploy [Terraform](https://www.terraform.io/) configurations. Here we provide two example blueprints that build custom [Apptainer](https://apptainer.org/) enabled images for use in the HPC system configuration created by the Cluster Toolkit `gcluster` command line tool. The blueprints are:
- [slurm-apptainer.yaml](./slurm-apptainer.yaml)
- [slurm-apptainer-gpu.yaml](./slurm-apptainer-gpu.yaml)

The [Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/overview) streamlines the definition and deployment of HPC Systems via _blueprints_ that it uses to generate and deploy [Terraform](https://www.terraform.io/) configurations. The `community/examples` directory in the Cluster Toolkit repository contains a blueprint that builds custom Apptainer images for use in the HPC system configuration created by the Cluster Toolkit `gcluster` command line tool.

## Blueprint Prep

Download the Cluster Toolkit `community/examples/hpc-slurm6-apptainer.yaml` blueprint with the command

```bash
wget https://raw.githubusercontent.com/GoogleCloudPlatform/cluster-toolkit/refs/heads/main/community/examples/hpc-slurm6-apptainer.yaml
```

If you want to deploy a Slurm-based HPC system with a GPU partition apply the `hpc-slurm6-gputainer.patch` file to the blueprint downloaded via the command above

```bash
patch -o hpc-slurm6-apptainer.yaml -i hpc-slurm6-gputainer.patch
```

## Deployment

Now you can create the deployment artifacts with the command

```bash
./gcluster create ./hpc-slurm6-apptainer.yaml \
  --vars project_id=$(gcloud config get project)
```

Which should result in out put like
```
To deploy your infrastructure please run:

./gcluster deploy slurm6-apptainer

Find instructions for cleanly destroying infrastructure and advanced manual
deployment instructions at:

slurm6-apptainer/instructions.txt
```

Or, if you are creating an HPC system with a GPU partition use the command

```bash
gcluster create BLUEPRINT \
  --vars project_id=$(gcloud config get core/project) \
  --vars guest_accelerator_type="nvidia-tesla-v100" \
  --vars guest_accelerator_count=1 \
  --vars max_dynamic_node_count=8 \
  --vars static_node_count=1 \
  --vars enable_placement=false --vars exclusive=false
```
Which should result in output like
```
To deploy your infrastructure please run:

./gcluster deploy slurm6-gputainer

Find instructions for cleanly destroying infrastructure and advanced manual
deployment instructions at:

slurm6-gputainer/instructions.txt
```

Enter ```./gcluster deploy slurm6-apptainer```, or ```./gcluster deploy slurm6-gputainer```,to deploy the HPC system.

Once the deployment is complete you can login to the system's login node with the command

```bash
gcloud compute ssh \
  $(gcloud compute instances list \
      --filter="NAME ~ login" \
      --format="value(NAME)") \
  --tunnel-through-iap
```

After you have logged into the login node check to ensure Apptainer is installed using the command

```bash
apptainer
```

You should see output that looks like

```
apptainer 
Usage:
  apptainer [global options...] <command>

Available Commands:
  build       Build an Apptainer image
  cache       Manage the local cache
  capability  Manage Linux capabilities for users and groups
  checkpoint  Manage container checkpoint state (experimental)
  completion  Generate the autocompletion script for the specified shell
  config      Manage various apptainer configuration (root user only)
  delete      Deletes requested image from the library
  exec        Run a command within a container
  inspect     Show metadata for an image
  instance    Manage containers running as services
  key         Manage OpenPGP keys
  oci         Manage OCI containers
  overlay     Manage an EXT3 writable overlay image
  plugin      Manage Apptainer plugins
  pull        Pull an image from a URI
  push        Upload image to the provided URI
  remote      Manage apptainer remote endpoints, keyservers and OCI/Docker registry credentials
  run         Run the user-defined default command within a container
  run-help    Show the user-defined help for an image
  search      Search a Container Library for images
  shell       Run a shell within a container
  sif         Manipulate Singularity Image Format (SIF) images
  sign        Add digital signature(s) to an image
  test        Run the user-defined tests within a container
  verify      Verify digital signature(s) within an image
  version     Show the version for Apptainer

Run 'apptainer --help' for more detailed usage information.
```

Now you can run Apptainer containerized workloads. For examples of containerized development environments, MPI, and GPU-based codes checkout the [examples](../examples/) directory.

## Cleanup

When your work is complete you can teardown the HPC system with

```bash
./gcluster destroy hpctainer # or gputainer
```