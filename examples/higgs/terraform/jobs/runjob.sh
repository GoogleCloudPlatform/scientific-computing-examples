#!/bin/bash
#
# Copyright 2022 Google LLC
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

set -eo pipefail
[ ! -z "${TRACE:-}" ] && set -x

log() {
  echo "* [${2:-INFO}] $1"
}

die() {
  log >&2 "$1" "ERROR"
  exit 1
}

main() {
  log "running cmsRun"
  export CMS_INPUT_FILES="file:///inputs/$(basename $CMS_INPUT_FILES)"
  time /opt/cms/entrypoint.sh cmsRun $CMS_CONFIG

  log "extracting json output"
  mkdir -p /tmp/outputs
  CMS_OUTPUT_JSON_FILE="/tmp/outputs/$(basename $CMS_INPUT_FILES)"
  /opt/cms/entrypoint.sh python /dump_json_pyroot.py \
    $CMS_OUTPUT_FILE \
    $CMS_DATASET_NAME \
    $CMS_OUTPUT_JSON_FILE

  log "debug"
  cat ${CMS_OUTPUT_JSON_FILE}
  echo ${CMS_LUMINOSITY_DATA}

  log "publishing output"
  python /publish_single.py $CMS_OUTPUT_JSON_FILE

  log "cleaning up"
  rm -f "/mnt/inputs/$(basename $CMS_INPUT_FILES)" || true

  log "done"
}

main "$@"
