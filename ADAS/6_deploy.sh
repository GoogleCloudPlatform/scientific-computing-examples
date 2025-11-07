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

gcloud functions deploy GCStoPubsub --runtime nodejs20 --stage-bucket gs://${STAGING_BUCKET_NAME} --trigger-topic ${UPLOAD_NOTIFICATION_TOPIC} --entry-point GCStoPubsub --region us-east1
gcloud functions deploy videoIntelligenceAPI --runtime nodejs20 --stage-bucket gs://${STAGING_BUCKET_NAME} --trigger-topic videointelligenceservice --entry-point videoIntelligenceAPI --timeout 540 --region us-east1
gcloud functions deploy insertIntoBigQuery --runtime nodejs20 --stage-bucket gs://${STAGING_BUCKET_NAME} --trigger-topic bqinsert --entry-point insertIntoBigQuery --region us-east1