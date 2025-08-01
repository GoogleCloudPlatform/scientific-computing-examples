export GCSPATH=`uuid | tr -d '-' | head -c 8`

gsutil mb gs://${GCSPATH}
wget -o ${GCSPATH}.fasta https://storage.googleapis.com/gcp-public-data--broad-references/hg38/v0/${GCSPATH}.fasta 
gsutil cp ${GCSPATH}.fasta gs://${GCSPATH}/Homo_sapiens_assembly38.fasta 
rm ${GCSPATH}.fasta
envsubst < smi_temp.json > smi.json
