# Flux Framework Object Store Example - Cluster Deployment

This deployment uses the [Flux Framework Cluster Module]() to bring together the remote state from the foundation deployment
with the Flux Framework images built with Cloud Build to instantiate a cluster node Compute Engine instances managed by the
Flux Framework resource job management software.

This deployment demostrates the use of a `boot script` to mount [Cloud Storage](https://cloud.google.com/storage)
object store buckets on compute and/or login nodes in a [flux-framework](https://flux-framework.org/) cluster. 

# Usage

Initialize the deployment with the command:

```bash
terraform init
```

Create the buckets and the boot script that will mount them on the cluster login and compute nodes.

```bash
./mkbuckets.sh
```

Make a copy of the `objectstore.tfvars.example` file:

```bash
cp objectstore.tfvars.example objectstore.tfvars
```

Modify the objectstore.tfvars to specify the desired configuration. For example you may want more than
one login node, you probably want more than one compute node, and/or you may want a different machine_type.

The `boot_script` field in both the login and compute node specifications has the value `fuse_mounts.sh`. That
will result in the buckets you created above being mounted on both types of nodes. If you don't want them 
mounted on a node type just set the `boot_script` field to `null`. 

Deploy the cluster with the command:

```bash
terraform apply -var-file objectstore.tfvars
```

Verify that the buckets were mounted correctly:

```bash
gcloud compute ssh objstore-login-001 --zone us-central1-a
```

```bash
ls -R /mnt
```

output:
```
/mnt:
main  variables

/mnt/main:
main.tf

/mnt/variables:
variables.tf
```

```bash
flux run -N2 --requires=n2 bash -c 'echo $(hostname):$(ls /mnt)'
```

output:
```
objstore-compute-a-002:main variables
objstore-compute-a-001:main variables
```
