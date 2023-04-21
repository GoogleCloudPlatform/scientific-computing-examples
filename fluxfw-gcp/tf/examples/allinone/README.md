# Flux Framework Consolidated Configuration Example - Cluster Deployment

This deployment illustrates deploying a flux-framework cluster on Google Cloud without the presence of the 
foundation components used in other fluxfw-gcp examples.

# Usage

Initialize the deployment with the command:

```bash
terraform init
```

Deploy the cluster with the command:

```bash
terraform apply -var-file allinone.tfvars \
  -var region=us-central1 \
  -var project_id=$(gcloud config get-value core/project) \
  -var network_name=foundation-net \
  -var zone=us-central1-a
```

Feel free to change any of the `-var` values to be appropriate for your environment.

Verify that the cluster is up:

```bash
gcloud compute ssh gffw-login-001 --zone us-central1-a
```

```bash
flux resource list
```

When you are finished destroy the cluster:

```bash
terraform destroy -var-file allinone.tfvars \
  -var region=us-central1 \
  -var project_id=$(gcloud config get-value core/project) \
  -var network_name=foundation-net \
  -var zone=us-central1-a
```
