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

unset subnetwork
unset zone

unset arm_machine_type
unset login_machine_type
unset manager_machine_type
unset x86_machine_type

rocky_linux_version="8"
subnetwork="default"

OPTIND=1

while getopts a:l:m:r:s:x:z: flag
do
    case "${flag}" in
        a) arm_machine_type=${OPTARG} ;;
        l) login_machine_type=${OPTARG} ;;
        m) manager_machine_type=${OPTARG} ;;
        r) rocky_linux_version=${OPTARG} ;;
        s) subnetwork=${OPTARG} ;;
        x) x86_machine_type=${OPTARG} ;;
        z) zone=${OPTARG} ;;
    esac
done

if [ "X${zone}" == "X" ]; then
    echo "Usage build-image.sh -z ZONE [-a ARM_MACHINE_TYPE -l LOGIN_MACHINE_TYPE -m MANAGER_MACHINE_TYPE -x X86_64_MACHINE_TYPE -r ROCKY_LINUX_VERSION]"
    exit 1
fi

substitutions="_ZONE=${zone}"

if [ "X${manager_machine_type}" != "X" ]; then
    source_image=$(gcloud compute images list --filter="name ~ rocky-linux-${rocky_linux_version}-optimized-gcp-v" --format="value(name)")
    gcloud builds submit --config=managerbuild.yaml --substitutions=_ZONE=${zone},_MACHINE_TYPE=${manager_machine_type},_SOURCE_IMAGE=${source_image},_SUBNETWORK=${subnetwork} .
fi

if [ "X${login_machine_type}" != "X" ]; then
    source_image=$(gcloud compute images list --filter="name ~ rocky-linux-${rocky_linux_version}-optimized-gcp-v" --format="value(name)")
    m4 --define=ROCKY_VERSION=${rocky_linux_version} flux-login-builder-startup-script.m4 > flux-login-builder-startup-script.sh
    gcloud builds submit --config=loginbuild.yaml --substitutions=_ZONE=${zone},_MACHINE_ARCHITECTURE="x86-64",_MACHINE_TYPE=${login_machine_type},_SOURCE_IMAGE=${source_image},_SUBNETWORK=${subnetwork} .
fi

if [ "X${arm_machine_type}" != "X" ]; then
    source_image=$(gcloud compute images list --filter="name ~ rocky-linux-${rocky_linux_version}-optimized-gcp-arm" --format="value(name)")
    m4 --define=ROCKY_VERSION=${rocky_linux_version} flux-compute-builder-startup-script.m4 > flux-compute-builder-startup-script.sh
    gcloud builds submit --config=computebuild.yaml --substitutions=_ZONE=${zone},_MACHINE_ARCHITECTURE="arm64",_MACHINE_TYPE=${arm_machine_type},_SOURCE_IMAGE=${source_image},_SUBNETWORK=${subnetwork} .
fi

if [ "X${x86_machine_type}" != "X" ]; then
    source_image=$(gcloud compute images list --filter="name ~ rocky-linux-${rocky_linux_version}-optimized-gcp-v" --format="value(name)")
    m4 --define=ROCKY_VERSION=${rocky_linux_version} --define=X86_64 flux-compute-builder-startup-script.m4 > flux-compute-builder-startup-script.sh
    gcloud builds submit --config=computebuild.yaml --substitutions=_ZONE=${zone},_MACHINE_ARCHITECTURE="x86-64",_MACHINE_TYPE=${x86_machine_type},_SOURCE_IMAGE=${source_image},_SUBNETWORK=${subnetwork} .
fi
