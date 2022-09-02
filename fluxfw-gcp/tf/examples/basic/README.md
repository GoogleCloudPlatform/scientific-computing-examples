# Flux Framework Basic GCP Example

This example illustrates the creation of a basic cluster of Compute Engine instances with the
Flux Framework resource job management software deployed across them. The example also illustrates
the modular construction of the system, deploying and configuring components separately and
then composing them using Terraform remote state.

## Overview

The components of the example HPC system to be deployed are

- the network and associated NAT and firewall rules
- the IAM service accounts to be used by the system components
- the NFS exported /home directory for all of the cluster nodes
- the cluster nodes, management, login, and compute

Each component is deployed separately and the resources it provides are shared via Terraform remote state.

The deployments occur in the following order and are described in detail in the corresponding component directories

1. [network]()
1. [iam]()
1. [storage]()
1. [cluster]()
