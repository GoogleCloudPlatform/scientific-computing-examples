gcloud compute instance-templates create wdc-template3  \
    --machine-type=n1-standard-4   \
    --maintenance-policy=TERMINATE    \
    --image-family=schedmd-v5-slurm-22-05-3-hpc-centos-7   \
    --image-project=schedmd-slurm-public    \
    --scopes="https://www.googleapis.com/auth/cloud-platform" \
    --accelerator="count=1,type=nvidia-tesla-t4" \
    --boot-disk-size=300