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

FROM nvidia/cuda:12.2.0-devel-ubuntu20.04 
RUN apt-get update && apt-get install -y --no-install-recommends \ 
     python3.5 \ 
     apt-transport-https ca-certificates gnupg curl sudo \
     python3-pip  && \ 
     apt-get clean && \ 
     rm -rf /var/lib/apt/lists/* 
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg  add - && apt-get update -y && apt-get install google-cloud-cli -y
RUN pip3 install --upgrade gcloud
RUN pip3 install google-cloud-pubsub
RUN pip3 install absl-py
COPY pull_fifo_id.py /tmp/pull_fifo_id.py
COPY simpleCUFFT_2d_MGPU /tmp/simpleCUFFT_2d_MGPU