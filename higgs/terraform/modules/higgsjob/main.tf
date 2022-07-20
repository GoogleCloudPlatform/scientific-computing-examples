resource "kubernetes_job" "higgsjob" {
  count = length(var.input_files)
  metadata {
    name = "${var.name}-${format("%04d", count.index + 1)}"
    namespace = "${var.namespace}"
  }
  spec {
    template {
      metadata {}
      spec {
        termination_grace_period_seconds = 300
        restart_policy = "Never"
        share_process_namespace = true

        init_container {
          name = "prepull"
          image = "${var.higgs-worker-image}"
          command = [ "/bin/bash", "-c", "/getfile.sh ${var.input_files[count.index]}" ]

          #env {
            #name = "TRACE"
            #value = "1"
          #}

          resources {
            requests = {
              cpu = "0.9"
              memory = "6Gi"
            }
            limits = {
              cpu = "0.9"
              memory = "6Gi"
            }
          }

          volume_mount {
            mount_path = "/getfile.sh"
            sub_path = "getfile.sh"
            name = "getfile"
          }
          volume_mount {
            mount_path = "/inputs"
            name = "inputs"
          }
        }
        container {
          name = "cmsrun"
          image = "${var.higgs-cms-image}"
          command = [ "bash", "-c", "/runjob.sh" ]

          #env {
            #name = "TRACE"
            #value = "1"
          #}
          env {
            name = "CMS_LUMINOSITY_DATA"
            value = "${length(var.luminosity_data) != 0 ? var.luminosity_data[count.index] : "null"}"
          }
          env {
            name = "CMS_JSON"
            value = "${var.CMS_JSON}"
          }
          env {
            name = "CMS_INPUT_FILES"
            value = "${var.input_files[count.index]}"
          }
          env {
            name = "CMS_OUTPUT_FILE"
            value = "${var.CMS_OUTPUT_FILE}"
          }
          env {
            name = "CMS_OUTPUT_JSON_FILE"
            value = "${var.CMS_OUTPUT_JSON_FILE}"
          }
          env {
            name = "CMS_S3_BASEDIR"
            value = "${var.CMS_S3_BASEDIR}"
          }
          env {
            name = "CMS_OUTPUT_S3PATH"
            value = "${var.dataset}-${format("%04d", count.index + 1)}.json"
          }
          env {
            name = "CMS_CONFIG"
            value = "${var.CMS_CONFIG}"
          }
          env {
            name = "CMS_DATASET_NAME"
            value = "${var.dataset}"
          }
          env {
            name = "MC_MULTIPART_THREADS"
            value = "${var.MC_MULTIPART_THREADS}"
          }
          env {
            name = "S3_ACCESS"
            value = "${var.S3_ACCESS}"
          }
          env {
            name = "S3_SECRET"
            value = "${var.S3_SECRET}"
          }
          env {
            name = "S3_HOST"
            value = "${var.S3_HOST}"
          }
          env {
            name = "GCS_ACCESS"
            value = "${var.GCS_ACCESS}"
          }
          env {
            name = "GCS_SECRET"
            value = "${var.GCS_SECRET}"
          }
          env {
            name = "GCS_HOST"
            value = "${var.GCS_HOST}"
          }
          env {
            name = "GCS_PROJECT_ID"
            value = "${var.GCS_PROJECT_ID}"
          }
          env {
            name = "DOWNLOAD_MAX_KB"
            value = "${var.DOWNLOAD_MAX_KB}"
          }
          env {
            name = "UPLOAD_MAX_KB"
            value = "${var.UPLOAD_MAX_KB}"
          }
          env {
            name = "REDIS_HOST"
            value = "${var.REDIS_HOST}"
          }
          env {
            name = "DPATH"
            value = "${var.DPATH}"
          }

          resources {
            requests = {
              cpu = "0.9"
              memory = "6Gi"
            }
            limits = {
              cpu = "0.9"
              memory = "6Gi"
            }
          }

          volume_mount {
            mount_path = "/runjob.sh"
            sub_path = "runjob.sh"
            name = "runjob"
          }
          volume_mount {
            mount_path = "/inputs"
            name = "inputs"
          }

        }

        volume {
          name = "runjob"
          config_map {
            name = "runjob"
            default_mode = "0755"
          }
        }
        volume {
          name = "getfile"
          config_map {
            name = "getfile"
            default_mode = "0755"
          }
        }
        volume {
          name = "inputs"
          empty_dir {
            medium = "Memory"
          }
        }

      }
    }
    backoff_limit = 5
    completions = 1
    parallelism = 1
  }
  timeouts {
    create = "10m"
  }
}
