#!/bin/bash

project_id="$(gcloud config get-value core/project)"
main_bucket="${project_id}_main"
variables_bucket="${project_id}_variables"

gcloud storage buckets create gs://${main_bucket}
gcloud storage buckets create gs://${variables_bucket}

gcloud storage cp ./main.tf gs://${main_bucket}
gcloud storage cp ./variables.tf gs://${variables_bucket}

cat << EOF > ./fuse-mounts.sh
#!/bin/bash

mkdir /mnt/main
gcsfuse -o ro,allow_other ${main_bucket} /mnt/main

mkdir /mnt/variables
gcsfuse -o rw,allow_other ${variables_bucket} /mnt/variables
EOF
