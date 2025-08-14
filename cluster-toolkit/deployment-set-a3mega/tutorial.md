## **Prerequisites and Environment Setup**

Before commencing the deployment process, ensure your environment meets the following prerequisites to guarantee a smooth and successful operation. This tutorial assumes familiarity with Google Cloud Platform (GCP), Terraform, and basic command-line operations.

**Create Terraform State Bucket** - this is required to hold the terraform state. 
```bash
export TF_STATE_BUCKET=<Bucket name>
export PROJECT_ID=<GCP Project ID>
export REGION=<region in selection>
gcloud storage buckets create gs://${TF_STATE_BUCKET} \
    --project=${PROJECT_ID} \
    --default-storage-class=STANDARD \
    --location=${REGION} \
    --uniform-bucket-level-access
gcloud storage buckets update gs://${TF_STATE_BUCKET} --versioning
```

After creating the bucket, please update the a3mega-slurm-deployment file with the terraform state bucket:

```yaml
terraform_backend_defaults:
  type: gcs
  configuration:
    bucket: <GCP Bucket Name>
```

**Updating the deployment yaml** please check the a3mega-slurm-deployment.yaml has your project id and regions set correctly.

If not, please update the following in the file:
```yaml
  project_id: # your project ID
  region: # region in use eg: us-central1
  zone: # zone in use eg: us-central1-a
```

* A **Google Cloud Project** with an active billing account.
* The **<code>gcloud</code> command-line tool** installed and authenticated (`gcloud auth login`) & (`gcloud auth application-default login`) follow the command below: 
* A **Git repository** (e.g., on GitHub, GitLab, or Cloud Source Repositories) containing your Cluster Toolkit configuration files. Cloud shell command shall already clone the repository required.

* Set the default GCP project:
    gcloud config set project <user project ID>
```bash
gcloud config set project 
```

* Run the gcloud auth login and gcloud auth application-default login 
```bash
gcloud auth login
```
```bash
gcloud auth application-default login
```
Note:
Credentials saved to file: [/tmp/xxxxx/application_default_credentials.json]
Copy them to this command below

   export GOOGLE_APPLICATION_CREDENTIALS=/tmp/xxxxx/application_default_credentials.json 
```bash
export GOOGLE_APPLICATION_CREDENTIALS=
```

* Then we need to run **make** command to build the **ghpc and gcluster** command. Cloud Shell should already have the Golang, Terraform and Packer
installed:

```bash
make
./gcluster --version
./gcluster --help
```

---

## **Step 3: Deploy the Cluster 🎉**

Since the deployment and blueprint files are provided by the team, There is no need to update them. 

**Full Deployment** - This is the single click deployment. If you did not yet create the network and built the image, please run this option, after you've updated the values in a3mega-deployment-set-main/a3mega-slurm-deployment-customer.yaml (including ensuring that the `TF_STATE_BUCKET`, `PROJECT_ID`, and `REGION` variables are updated to reflect what's above and what you plan on setting up in your environment):

**DWS Flex only cluster** - This does not require any reservation / quota request prior. 
```bash
./gcluster deploy -d deployment-set-a3mega-main/a3mega-slurm-deployment.yaml deployment-set-a3mega-main/a3mega-lustre-slurm-blueprint.yaml --auto-approve
```

**DWS Calendar and Flex cluster** - This requires DWS Calendar reservation done prior.
```bash
./gcluster deploy -d deployment-set-a3mega-main/a3mega-slurm-deployment.yaml deployment-set-a3mega-main/a3mega-lustre-slurm-blueprint-dws-2-partitions.yaml --auto-approve
```

Note:  
Image building process runs between 30 - 40 mins.
Managed Lustre creating process runs between 30 - 40 mins.


**Cluster Deploy / Destroy only**  - Deploy / Destroy the cluster only. This is for users who already created the network and have the custom image built. 
If you want to Deploy / Destroy the cluster only. Please follow the following steps: 

Deploy the cluster only: 

```bash
  ./gcluster import-inputs a3mega-lustre-base/cluster
  terraform -chdir=a3mega-lustre-base/cluster apply
```

Delete the cluster only:

```bash
  terraform -chdir=a3mega-lustre-base/cluster destroy
```

**Updating the Cluster configuration** - Cluster can be updated live with configuration like number of nodes, size of storage etc.

```bash
./gcluster deploy -d deployment-set-a3mega-main/a3mega-slurm-deployment.yaml deployment-set-a3mega-main/a3mega-lustre-slurm-blueprint.yaml -w  --only primary,cluster
```

---

## **Cleaning Up 🧹**

HPC clusters can be expensive, so it's critical to tear down your resources when you are finished.

You can destroy the deployment by running the `gcluster destroy` command locally with the same deployment file.

```bash
./gcluster destroy a3mega-lustre-base --auto-approve
```