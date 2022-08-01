# Example: HPC Toolkit Support Slurm and Docker 

## Overview

This example creates a Slurm Cluster and allows Docker files to run.
All other components required to support the Slurm cluster are minimally created
as well: VPC; subnetwork; firewall rules; service accounts.

# Install HPC Toolkit

Follow [the instructions here](https://github.com/GoogleCloudPlatform/hpc-toolkit#quickstart) to install the HPC Toolkit.
In the Hpc Toolkit folder run an install.
```
make install
```

# Run the HPC Toolkit

* Create a GCP Project [as described here](https://cloud.google.com/resource-manager/docs/creating-managing-projects).

 [![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://shell.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/GoogleCloudPlatform/scientific-computing-examples.git)

```
cd slurm-cookbook/docker
ghpc slurm-docker.yaml
```

* Edit the `slurm-docker.yaml` file.
  * Change `<your project>` to be the `my-project-id` of the project you created in the previous step

When `ghpc` is in your path, you can run in this repo.

```
cd slurm-cookbook/docker
ghpc slurm-docker.yaml
```
The output of this job, when successful will show some terraform commands. Execute these commands to build out the Slurm cluster.

# Run a job in the cluster

When the cluster build has completed there will be two 

