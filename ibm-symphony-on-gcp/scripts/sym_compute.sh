#!/bin/bash

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
set -o pipefail
set -x

export SYM_MASTER=$1
export EGO_TOP=$2

##### Configure Master VM.

source $EGO_TOP/profile.platform && egosetsudoers.sh -f

	su -s /bin/bash egoadmin -c "source $EGO_TOP/profile.platform && egoconfig join $SYM_MASTER -f && egosh ego start"

