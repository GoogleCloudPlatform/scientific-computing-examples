export GCSPATH=`uuid | tr -d '-' | head -c 8`

gsutil mb gs://${GCSPATH}

# Input data from Broad public datasets: https://console.cloud.google.com/marketplace/product/broad-institute/references

# Use Bucket to bucket transfer, extremely fast. 

gsutil cp gs://gcp-public-data--broad-references/hg38/v0/Homo_sapiens_assembly38.fasta gs://${GCSPATH}/

# Input data from https://42basepairs.com/search?query=.fastq&bucket=gs/deepvariant

gsutil cp gs://deepvariant/benchmarking/fastq/wgs_pcr_free/30x/HG001.novaseq.pcr-free.30x.R1.fastq.gz gs://${GCSPATH}/
gsutil cp gs://deepvariant/benchmarking/fastq/wgs_pcr_free/30x/HG001.novaseq.pcr-free.30x.R2.fastq.gz gs://${GCSPATH}/



gsutil cp 8gpu.sh gs://${GCSPATH}/

# Prepare batch input file
envsubst < smi_temp.json > smi.json

# Enable APIs

gcloud services enable batch.googleapis.com aiplatform.googleapis.com

# Create Colab for Notebook visualization.

#export ID=$(gcloud colab runtime-templates create --display-name=af3-template --region=us-central1 --machine-type=n1-standard-8 --disk-size-gb=200 --disk-type=PD_SSD --display-name="Alphafold3" --enable-internet-access --format=json | jq -r '.name' | rev | cut -d '/' -f1 | rev)
#gcloud colab runtimes create  --display-name="AF3 Runtime" --runtime-template=${ID} --region=us-central1
