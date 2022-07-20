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

module "sm11_jobs" {
  source = "../modules/higgsjob"
  name = "sm11legdrzzto2e2mumll47tev-pw-py600000"
  namespace = var.namespace

  dataset = "sm11legdr_zzto2e2mu_mll4_7tev-pw-py6"
  input_files = var.sm11_files_small
  higgs-cms-image = var.higgs-cms-image
  higgs-worker-image = var.higgs-worker-image

  CMS_CONFIG = "/configs/demoanalyzer_cfg_level4MC.py"
  GCS_PROJECT_ID = "${data.external.env.result.GOOGLE_CLOUD_PROJECT}"
  REDIS_HOST = "redis.${var.namespace}.svc.cluster.local"
}
