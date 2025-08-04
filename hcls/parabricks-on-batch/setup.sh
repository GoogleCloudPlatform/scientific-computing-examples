export GCSPATH=`uuid | tr -d '-' | head -c 8`

gsutil mb gs://${GCSPATH}

# From Broad public datasets: https://console.cloud.google.com/marketplace/product/broad-institute/references

# Use Bucket to bucket transfer, extremely fast. 

gsutil cp gs://gcp-public-data--broad-references/hg38/v0/Homo_sapiens_assembly38.fasta gs://${GCSPATH}/

# From https://42basepairs.com/search?query=.fastq&bucket=gs/deepvariant

gsutil cp gs://deepvariant/benchmarking/fastq/wgs_pcr_free/30x/HG001.novaseq.pcr-free.30x.R1.fastq.gz gs://${GCSPATH}/
gsutil cp gs://deepvariant/benchmarking/fastq/wgs_pcr_free/30x/HG001.novaseq.pcr-free.30x.R2.fastq.gz gs://${GCSPATH}/

envsubst < smi_temp.json > smi.json
