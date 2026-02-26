#  Copyright 2023 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

provider "google-beta" {
  region = var.region
  zone   = var.zone
  project = var.project
}
locals {
  sa_email = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}
resource "google_compute_project_metadata" "default" {
  project = var.project
  metadata = {
    bq_table_prefix  = var.name_prefix
    bq_table_suffix  = var.name_suffix
  }
}
resource "google_compute_network" "vpc_network" {
  name = "${var.name_prefix}-network"
  project = var.project
}
variable "gcp_service_list" {
  description ="The list of apis necessary for the project"
  type = list(string)
  default = [
    "cloudresourcemanager.googleapis.com",
    "batch.googleapis.com",
    "serviceusage.googleapis.com"
  ]
}

resource "google_project_service" "gcp_services" {
  for_each = toset(var.gcp_service_list)
  project = "${var.project}"
  disable_dependent_services = true
  service = each.key

}

resource "google_notebooks_instance" "instance" {
  name = "notebooks-instance-${var.name_suffix}"
  depends_on = [google_project_service.vertex_ai_notebooks_api]
  location = "us-west1-a"
  machine_type = "e2-medium"
  project = var.project
  vm_image {
    project      = "deeplearning-platform-release"
    image_family = "tf-latest-cpu"
  }
}

 resource "google_project_service" "vertex_ai_notebooks_api" {
   service = "notebooks.googleapis.com"
   project = data.google_project.project.project_id
   # lifecycle {
   #  prevent_destroy = true
   # }
}

 resource "google_project_service" "bigquery" {
   service = "bigquery.googleapis.com"
   disable_dependent_services = true
   project = data.google_project.project.project_id
   # lifecycle {
   #  prevent_destroy = true
   # }
 }

resource "google_project_iam_member" "data_editor" {
  project = data.google_project.project.project_id
  role = "roles/bigquery.dataEditor"
  member = "user:${var.user_email}"
}

resource "google_project_iam_member" "metadata_viewer" {
  project = data.google_project.project.project_id
  role = "roles/bigquery.metadataViewer"
  member = "user:${var.user_email}"
}

resource "google_pubsub_topic" "example" {
  name = "${var.name_prefix}_topic_${var.name_suffix}"
  depends_on = [google_pubsub_schema.example]
  project = var.project
  schema_settings {
    schema = "${data.google_project.project.id}/schemas/${var.name_prefix}_schema_${var.name_suffix}"
    encoding = "BINARY"
  }
}

resource "google_pubsub_schema" "example" {
  name = "${var.name_prefix}_schema_${var.name_suffix}"
  project = var.project
  type = "AVRO"

  definition = <<CCE
{  
  "name" : "Avro",  
  "type" : "record", 
  "fields" : 
      [
       {"name" : "ticker", "type" : "string"},
       {"name" : "epoch_time", "type" : "int"},
       {"name" : "iteration", "type" : "int"},
       {"name" : "start_date", "type" : "string"},
       {"name" : "end_date", "type" : "string"},
       {
           "name":"simulation_results",
           "type":{
               "type": "array",  
               "items":{
                   "name":"Child",
                   "type":"record",
                   "fields":[
                       {"name":"price", "type":"double"}
                   ]
               }
           }
       }
      ]
 }
CCE
}

resource "google_pubsub_subscription" "example" {
  name  = "${var.name_prefix}_subscription_${var.name_suffix}"
  topic = google_pubsub_topic.example.name
  project = var.project

  bigquery_config {
    table = "${google_bigquery_table.pbsb.project}.${google_bigquery_table.pbsb.dataset_id}.${google_bigquery_table.pbsb.table_id}"
    use_topic_schema = true
    write_metadata = true
  }

  depends_on = [google_project_iam_member.viewer, google_project_iam_member.editor]
}

data "google_project" "project" {
  project_id = "${var.project}"
}

resource "google_project_iam_member" "viewer" {
  project = data.google_project.project.project_id
  role   = "roles/bigquery.metadataViewer"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "editor" {
  project = data.google_project.project.project_id
  role   = "roles/bigquery.dataEditor"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_bigquery_dataset" "pbsb" {
  depends_on = [resource.google_project_service.bigquery]
  dataset_id = "${var.name_prefix}_dataset_${var.name_suffix}"
  project = data.google_project.project.project_id
}

resource "google_bigquery_table" "pbsb" {
  deletion_protection = false
  project = var.project
  table_id   = "${var.name_prefix}_table_${var.name_suffix}"
  dataset_id = google_bigquery_dataset.pbsb.dataset_id

  schema = <<EOF
[
  {
    "name": "subscription_name", "type": "STRING"
  },
  {
    "name": "message_id", "type": "STRING"
  },
  {
    "name": "publish_time", "type": "TIMESTAMP"
  },
  {
    "name": "simulation_results", "type": "RECORD", "mode": "REPEATED",
    "fields": [
      {
        "name" : "price",
        "type" : "NUMERIC"
      }
    ]
  },
  {
    "name": "ticker", "type": "STRING"
  }
  ,{
    "name": "epoch_time", "type": "INT64"
  }
  ,{
    "name": "iteration", "type": "INT64"
  }
  ,{
    "name": "start_date", "type": "STRING"
  }
  ,{
    "name": "end_date", "type": "STRING"
  }
  ,{
    "name": "attributes", "type": "STRING"
  }
]
EOF
}

data "template_file" "batch_yaml" {
  template = "${file("${path.module}/batch.tpl.yaml")}"
  vars = {
    project_id = "${data.google_project.project.project_id}"
    region = "${var.region}"
    bucket_name = "${google_storage_bucket.fsi_bucket.name}"
  }
}
resource "local_file" "batch_yaml_file" {
  filename = "batch.yaml"
  content  = data.template_file.batch_yaml.rendered
}

data "template_file" "python" {
  template = "${file("${path.module}/pubsub_bq.tpl.py")}"
  vars = {
    project_id = "${data.google_project.project.project_id}"
    topic_name = "${google_pubsub_topic.example.name}"
    schema_name = "${google_pubsub_schema.example.name}"
    dataset_name = "${google_bigquery_dataset.pbsb.dataset_id}"
    table_name = "${google_bigquery_table.pbsb.table_id}"
  }
}
resource "local_file" "python_script" {
  filename = "pubsub_bq.py"
  content  = data.template_file.python.rendered
}
resource "local_file" "python_requirements" {
  filename = "requirements.txt"
  content  =<<EOR
absl-py
avro
google-auth
google-cloud
google-cloud-batch
google-cloud-pubsub
google-cloud-bigquery
yfinance
PyYAML
EOR

  provisioner "local-exec" {
    command = "python3 -m venv .fsi; source .fsi/bin/activate; python3 -m pip install -r requirements.txt"
  }

}
resource "google_storage_bucket" "fsi_bucket" {
  name          = "${var.name_prefix}_bucket_${var.name_suffix}"
  project = var.project
  location      = "US"
  force_destroy = true
  uniform_bucket_level_access = true


  public_access_prevention = "enforced"
  provisioner "local-exec" {
    command = "gcloud storage cp iteration.sh pubsub_bq.py requirements.txt gs://${var.name_prefix}_bucket_${var.name_suffix}"
  }
  depends_on = [
    local_file.python_script
  ]
}