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

resource "kubernetes_daemonset" "prepull" {
  metadata {
    name = "prepull"
    namespace = "${kubernetes_namespace.higgs-tutorial.id}"
  }

  spec {
    selector {
      match_labels = {
        name = "prepull"
      }
    }

    template {
      metadata {
        labels = {
          name = "prepull"
        }
      }

      spec {
        termination_grace_period_seconds = 5
        init_container {
          name  = "prepull"
          image = "${var.higgs-cms-image}"
          command = ["bash", "-c", "echo", "1"]
        }
        init_container {
          name  = "prepull-worker"
          image = "${var.higgs-worker-image}"
          command = ["bash", "-c", "echo", "1"]
        }
        container {
          name  = "pause"
          image = "gcr.io/google_containers/pause"
        }
      }
    }
  }
}
