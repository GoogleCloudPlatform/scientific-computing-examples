# fluxfw-gcp

This repo contains scripts and Terraform configs that make it easy to deploy the 
[Flux Framework](https://flux-framework.org/) resource job management software designed
by LLNL engineers in the Google Cloud Platform.

The scripts in the [img](img) directory build Flux Framework GCP images for management, 
compute and login nodes.

The Terraform modules in the [tf](tf) directory are used to deploy and configure the Flux Framework
GCP images, along with additional GCP components, to form a working HPC system.
