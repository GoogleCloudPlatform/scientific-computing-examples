#!/usr/bin/env bash

# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value core/project) --format="value(projectNumber)")

if [ "X$(gcloud projects get-iam-policy $PROJECT_NUMBER --flatten=bindings --filter='bindings.role:roles/cloudkms.cryptoKeyDecrypter' --format='value(bindings.members)')" == "X" ]; then
  CLOUD_BUILD_SERVICE_ACCOUNT=$(gcloud projects get-iam-policy $PROJECT_NUMBER --format "value(bindings.members)" | tr ';' '\n' | grep '@cloudbuild' | head -n1 | cut -d"'" -f2)
  gcloud projects add-iam-policy-binding $PROJECT_NUMBER --member=${CLOUD_BUILD_SERVICE_ACCOUNT} --role=roles/cloudkms.cryptoKeyDecrypter
fi

if [ "X$(gcloud iam service-accounts list --filter='email ~ image-builder' --format='value(email)')" == "X" ]; then
    gcloud iam service-accounts create image-builder
fi

IMAGE_BUILDER_SERVICE_ACCOUNT=$(gcloud iam service-accounts list --filter="email ~ image-builder" --format="value(email)")
gcloud iam service-accounts keys create image-builder.key --iam-account=${IMAGE_BUILDER_SERVICE_ACCOUNT}
gcloud projects add-iam-policy-binding $PROJECT_NUMBER --member=serviceAccount:${IMAGE_BUILDER_SERVICE_ACCOUNT} --role=roles/editor

if [ "X$(gcloud kms keyrings list --location=global --filter='name ~ packer' --format='value(name)')" == "X" ]; then
  gcloud kms keyrings create packer --location=global
  gcloud kms keys create pk --keyring=packer --location=global --purpose=encryption
fi

gcloud kms encrypt --keyring=packer --key=pk --location=global --plaintext-file=image-builder.key --ciphertext-file=image-builder-enc.key
