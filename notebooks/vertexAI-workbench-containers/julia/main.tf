provider "google" {
  project = "openfoam-jrt"
  region  = "us-central1"
}
terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "3.0.2"
    }
    random = {
      source = "hashicorp/random"
    }
  }
}

resource "google_workbench_instance" "instance" {
  name = "workbench-instance"
  location = "us-central1-a"

  gce_setup {
    machine_type = "n1-standard-16" 
    container_image {
      repository = "us-east1-docker.pkg.dev/openfoam-jrt/auto-created-repository/julia-workbench"
    }
  }
}

