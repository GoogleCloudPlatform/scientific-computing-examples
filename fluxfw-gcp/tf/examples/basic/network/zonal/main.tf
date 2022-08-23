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

module "network" {
  source       = "github.com/terraform-google-modules/terraform-google-network"
  project_id   = var.project_id
  network_name = var.network_name
  subnets      = [
    {
      subnet_name   = "${var.network_name}-subnet-01"
      subnet_ip     = var.subnet_ip
      subnet_region = var.region
    }
  ]
}

module "nat" {
  source        = "github.com/terraform-google-modules/terraform-google-cloud-nat"
  project_id    = var.project_id
  region        = var.region
  network       = module.network.network_name
  create_router = true
  router        = "${module.network.network_name}-router"
}

module "firewall" {
  source          = "github.com/terraform-google-modules/terraform-google-network/modules/firewall-rules"
  project_id      = var.project_id
  network_name    = module.network.network_name
  rules           = [
    {
      name                    = "${var.network_name}-allow-ssh"
      direction               = "INGRESS"
      priority                = null
      description             = null
      ranges                  = ["0.0.0.0/0"]
      source_tags             = null
      source_service_accounts = null
      target_tags             = ["flux"]
      target_service_accounts = null
      allow                   = [
        {
          protocol = "tcp"
          ports    = ["22"]
        }
      ],
      deny                    = []
      log_config              = {
        metadata = "INCLUDE_ALL_METADATA"
      }
    },
    {
      name                    = "${var.network_name}-allow-interal-traffic"
      direction               = "INGRESS"
      priority                = null
      description             = null
      ranges                  = ["0.0.0.0/0"]
      source_tags             = null
      source_service_accounts = null
      target_tags             = ["ssh", "flux"]
      target_service_accounts = null
      allow                   = [
        {
          protocol = "icmp"
          ports    = []
        },
        {
          protocol = "udp"
          ports    = ["0-65535"]
        },
        {
          protocol = "tcp"
          ports    = ["0-65535"]
        }
      ]
      deny                    = []
      log_config              = {
        metadata = "INCLUDE_ALL_METADATA"
      }
    }
  ]
}
