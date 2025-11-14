# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

cd /mnt/data

apt install wget

wget -q -O parabricks_sample.tar.gz \
"https://s3.amazonaws.com/parabricks.sample/parabricks_sample.tar.gz"
tar xvf parabricks_sample.tar.gz

pbrun fq2bam --num-gpus 2 \
    --bwa-cpu-thread-pool 16 \
    --gpusort \
    --gpuwrite \
    --tmp-dir /mnt/data \
    --ref /mnt/data/parabricks_sample/Ref/Homo_sapiens_assembly38.fasta \
    --in-fq /mnt/data/parabricks_sample/Data/sample_1.fq.gz /mnt/data/parabricks_sample/Data/sample_2.fq.gz \
    --out-bam /mnt/data/fq2bam_output.bam

pbrun deepvariant \
    --ref /mnt/data/parabricks_sample/Ref/Homo_sapiens_assembly38.fasta \
    --in-bam /mnt/data/fq2bam_output.bam \
    --out-variants /mnt/gcs/share/deepvariant.vcf

cp /mnt/data/fq2bam_output.* /mnt/gcs/share/