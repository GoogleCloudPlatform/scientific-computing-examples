FROM gcr.io/deeplearning-platform-release/base-gpu.py310

# ARG CUDA_MAJOR=11
# ARG CUDA_MINOR=0
# RUN apt-get -qq update \
#   && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y \
#     build-essential \
#     cmake \
#     cuda-command-line-tools-${CUDA_MAJOR}-${CUDA_MINOR} \
#     git \
#     hmmer \
#     kalign \
#     tzdata \
#     wget \
#   && apt-get -qq clean \
#   && rm -rf /var/lib/apt/lists/*

#RUN conda install -qy flask
#
# or
#
RUN pip install -q flask
#
# either way be sure that any users add
# `export PATH=/opt/conda/bin:$PATH`
# to their `.bashrc`.

# see
# https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/community-content/alphafold_on_workbench/Dockerfile
# for an example of more cuda tool updates/config

