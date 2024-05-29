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
  echo """
  usage: $0 [-p <project>] [-z <zone>] [-i <image_name>] <workbench_name>
    where
      -p project (defaults to GOOGLE_CLOUD_PROJECT env var)
      -z zone (defaults to CLOUDSDK_COMPUTE_ZONE env var)
      -i image_name, workbench image name (defaults to '${default_image_tag}')
      workbench_name is the name of the notebook instance to deploy
  """
}

check_args() {
  if [ -z "$project" ] || \
     [ -z "$zone" ] || \
     [ -z "$image_name" ] || \
     [ -z "$workbench_name" ]; then
    usage
    die 'need args!'
  fi

  if [ -n "$remaining_args" ]; then
    usage
    die 'unknown extra args!'
  fi
}

check_dependencies() {
  local missing_dep=""
  $(which -s gcloud) || missing_dep="${missing_dep} gcloud"
  $(which -s docker) || missing_dep="${missing_dep} docker"
  if [ -n "$missing_dep" ]; then
    usage
    die "missing dependencies!  Please install: $missing_dep"
  fi
}

check_services() {
  log "check services"
}

enable_service() {
  log "enable services"
}

build_image() {
  #local region="${zone%%-[a-f]}"
  
  log "build image"
}

create_repository() {
  local zone="${1:-us-central1-c}"
  local repository_name="tutorial"

  log gcloud artifacts repositories create ${respository_name} \
    --location=${zone} \
    --repository-format="DOCKER"

  #  gcloud artifacts repositories create (REPOSITORY : --location=LOCATION) --repository-format=REPOSITORY_FORMAT [optional flags]
  #  optional flags may be  --allow-snapshot-overwrites | --async | --description |
  #                         --disable-remote-validation | --help |
  #                         --immutable-tags | --kms-key | --labels | --location |
  #                         --mode | --remote-apt-repo | --remote-apt-repo-path |
  #                         --remote-docker-repo | --remote-mvn-repo |
  #                         --remote-npm-repo | --remote-password-secret-version |
  #                         --remote-python-repo | --remote-repo-config-desc |
  #                         --remote-username | --remote-yum-repo |
  #                         --remote-yum-repo-path | --upstream-policy-file |
  #                         --version-policy

}

push_image_to_repository() {
  #local region="${zone%%-[a-f]}"
  log "push image to repository"
}

create_workbench() {
  local project=$1
  local zone=$2
  local image_name=$3
  local workbench_name=$4

    #--container-repository=${container_repository} \
  gcloud notebooks instances create ${workbench_name} \
    --location=${zone} \
    --container-tag=${image_name}
  # Usage: gcloud notebooks instances create (INSTANCE : --location=LOCATION) [optional flags]
  # optional flags may be  --accelerator-core-count | --accelerator-type |
  #                        --async | --boot-disk-size | --boot-disk-type |
  #                        --container-repository | --container-tag |
  #                        --custom-gpu-driver-path | --data-disk-size |
  #                        --data-disk-type | --disk-encryption | --environment |
  #                        --environment-location | --help |
  #                        --install-gpu-driver | --instance-owners | --kms-key |
  #                        --kms-keyring | --kms-location | --kms-project |
  #                        --labels | --location | --machine-type | --metadata |
  #                        --network | --post-startup-script | --no-proxy-access |
  #                        --no-public-ip | --no-remove-data-disk |
  #                        --reservation | --reservation-affinity |
  #                        --service-account | --shielded-integrity-monitoring |
  #                        --shielded-secure-boot | --shielded-vtpm | --subnet |
  #                        --subnet-region | --tags | --vm-image-family |
  #                        --vm-image-name | --vm-image-project



}

main() {
  #default_image_tag="gcr.io/deeplearning-platform-release/base-gpu.py310"
  default_image_tag="base-gpu.py310"

  while getopts ':p:z:i:' OPT; do
    case $OPT in
      p) project_opt=$OPTARG ;;
      z) zone_opt=$OPTARG ;;
      i) image_name_opt=$OPTARG ;;
    esac
  done
  project=${project_opt:-$GOOGLE_CLOUD_PROJECT} # opt overrides env default
  zone=${zone_opt:-$CLOUDSDK_COMPUTE_ZONE} # opt overrides env default
  image_name=${image_name_opt:-$default_image_tag}

  shift $(($OPTIND - 1))
  workbench_name=$1

  shift || : # TODO double-check this... I think this works
  remaining_args=$@

  check_args
  check_dependencies
  check_services # might be the easiest way to handle this...

  if [ "$image_name" != "$default_image_tag" ] \\
     && [ "$image_name" != "$default_image_tag:latest" ]; then
    build_image ${image_name}
    create_repository "custom-workbench-images"
    push_image_to_repository ${image_name} "custom-workbench-images"
  fi

  create_workbench ${project} ${zone} ${image_name} ${workbench_name}
}
main $@
