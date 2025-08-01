export GCSPATH=`uuid | tr -d '-' | head -c 8`

gsutil mb gs://${GCSPATH}
curl https://storage.googleapis.com/gcp-public-data--broad-references/hg38/v0/Homo_sapiens_assembly38.fasta | gsutil cp - gs://${GCSPATH}/Homo_sapiens_assembly38.fasta 
envsubst < smi_temp.json > smi.json
