#
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

module "cmsrun_jobs" {
  source = "../modules/higgsjob"
  name = "cmsrun2012cdoublemuparkedaod22jan2013-v120000"
  namespace = var.namespace

  dataset = "cms_run2012c_doublemuparked_aod_22jan2013-v1"
  input_files = var.cmsrun_input_files_small
  luminosity_data = var.cmsrun_luminosity_data_small
  higgs-cms-image = var.higgs-cms-image
  higgs-worker-image = var.higgs-worker-image

  CMS_CONFIG = "/configs/demoanalyzer_cfg_level4data.py"
  CMS_JSON = "/json_files/Cert_190456-208686_8TeV_22Jan2013ReReco_Collisions12_JSON.txt"
  GCS_PROJECT_ID = "${data.external.env.result.GOOGLE_CLOUD_PROJECT}"
  REDIS_HOST = "redis.${var.namespace}.svc.cluster.local"
}
