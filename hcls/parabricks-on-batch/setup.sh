export GCSPATH=`uuid | tr -d '-' | head -c 8`

gsutil mb gs://${GCSPATH}
curl https://storage.googleapis.com/gcp-public-data--broad-references/hg38/v0/Homo_sapiens_assembly38.fasta | gsutil cp - gs://${GCSPATH}/Homo_sapiens_assembly38.fasta 
curl https://42basepairs.com/download/gs/deepvariant/benchmarking/fastq/wgs_pcr_free/30x/HG001.novaseq.pcr-free.30x.R1.fastq.gz | gsutil cp - gs://${GCSPATH}/HG001.novaseq.pcr-free.30x.R1.fastq.gz
curl https://42basepairs.com/download/gs/deepvariant/benchmarking/fastq/wgs_pcr_free/30x/HG001.novaseq.pcr-free.30x.R2.fastq.gz | gsutil cp - gs://${GCSPATH}/HG001.novaseq.pcr-free.30x.R2.fastq.gz

envsubst < smi_temp.json > smi.json
