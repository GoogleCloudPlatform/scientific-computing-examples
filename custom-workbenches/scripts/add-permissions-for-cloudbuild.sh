#!/bin/bash
#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#GOOGLE_CLOUD_PROJECT=mycoolproject
CLOUD_BUILD_ACCOUNT=$(gcloud projects get-iam-policy ${GOOGLE_CLOUD_PROJECT} --filter="(bindings.role:roles/cloudbuild.builds.builder)"  --flatten="bindings[].members" --format="value(bindings.members[])")

for role in roles/compute.admin \
  roles/compute.instanceAdmin \
  roles/iam.serviceAccountUser \
  roles/iap.tunnelResourceAccessor
do
  gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} --member ${CLOUD_BUILD_ACCOUNT} --role ${role}
done

#gcloud builds submit . --region us-central1 --config=cloudbuild.yaml

