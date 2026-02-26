# Copyright 2025 Google LLC
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

gcloud storage cp -r gs://spls/gsp138/cloud-functions-intelligentcontent-nodejs .
cd cloud-functions-intelligentcontent-nodejs
export DATASET_ID=intelligentcontentfilter
export TABLE_NAME=filtered_content
bq --project_id ${PROJECT_ID} mk ${DATASET_ID}
bq --project_id ${PROJECT_ID} mk --schema intelligent_content_bq_schema.json -t ${DATASET_ID}.${TABLE_NAME}
bq --project_id ${PROJECT_ID} show ${DATASET_ID}.${TABLE_NAME}