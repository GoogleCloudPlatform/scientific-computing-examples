#  Copyright 2023 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
BIN_VERSION="1.2.0" BASE="/mnt/disks/work/${BATCH_JOB_UID}"
INPUT_DIR="${BASE}/input"
OUTPUT_DIR="${BASE}/output"
DATA_DIR="${INPUT_DIR}/data"
TMP_DIR="${INPUT_DIR}/tmp"

REF="GRCh38_no_alt_analysis_set.fasta"
BAM="HG003.novaseq.pcr-free.35x.dedup.grch38_no_alt.chr20.bam"
#BAM="HG004.novaseq.pcr-free.35x.dedup.grch38_no_alt.bam"
OUTPUT_VCF="HG004.output.vcf.gz"
OUTPUT_GVCF="HG004.output.g.vcf.gz"

mkdir -p "${OUTPUT_DIR}"
mkdir -p "${INPUT_DIR}"
mkdir -p "${DATA_DIR}"
mkdir -p "${TMP_DIR}"

echo ${BATCH_TASK_INDEX}

env

# Input BAM and BAI files:
cp /mnt/disks/deepvariant/case-study-testdata/"${BAM}" "${DATA_DIR}"
cp /mnt/disks/deepvariant/case-study-testdata/"${BAM}".bai "${DATA_DIR}"

# GRCh38 reference FASTA file:
FTPDIR=ftp://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids

curl -s ${FTPDIR}/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz | gunzip > "${DATA_DIR}/${REF}"
curl -s ${FTPDIR}/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.fai > "${DATA_DIR}/${REF}".fai


/opt/deepvariant/bin/run_deepvariant \
    --model_type=WGS \
    --ref="${DATA_DIR}/${REF}" \
    --reads="${DATA_DIR}/${BAM}" \
    --output_vcf=${OUTPUT_DIR}/${OUTPUT_VCF} \
    --output_gvcf=${OUTPUT_DIR}/${OUTPUT_GVCF} \
    --num_shards=$(nproc) \
    --intermediate_results_dir ${TMP_DIR} 