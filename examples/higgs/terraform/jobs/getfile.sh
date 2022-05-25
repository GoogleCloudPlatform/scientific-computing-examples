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

usage() {
  echo "Usage: $0 <URL>"
}
[ $# -lt 1 ] && usage && exit 1
download_url=${1:-default}

download_data_file() {
  local from_url=$1

  local from=${from_url//gs\//gs:\/\/}
  local to="/inputs/$(basename $from_url)"
  log "downloading..."
  log "  from: $from"
  log "  to: $to"
  gsutil -m cp $from $to
}

main() {
  log "download_url: $download_url"
  download_data_file $download_url
}

main "$@"
