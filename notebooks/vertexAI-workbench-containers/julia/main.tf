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

locals {
  #us-central1-docker.pkg.dev/openfoam-jrt/my-repository
  repo_url = "${google_artifact_registry_repository.my-repo.location}-docker.pkg.dev"
  repo_path = "${local.repo_url}/${data.google_project.project.name}/${google_artifact_registry_repository.my-repo.name}"
  suffix         = random_id.resource_name_suffix.hex 
}

resource "random_id" "resource_name_suffix" {
  byte_length = 4
}

resource "google_artifact_registry_repository" "my-repo" {
  location      = "us-central1"
  repository_id = "my-repository"
  description   = "example docker repository"
  format        = "DOCKER"
  docker_config {
    immutable_tags = false
  }
}

resource "docker_image" "vertex_julia" {
  provider = docker
  name     = "${local.repo_path}/vertex-julia:${local.suffix}"
  build {
    context   = path.cwd
  }
}

 resource "null_resource" "build_and_push_image" {
   provisioner "local-exec" {
     command = <<-EOT
     cd ${path.cwd}
     gcloud builds submit --tag ${docker_image.vertex_julia.name} .
     gcloud auth configure-docker us-central1-docker.pkg.dev
     docker push ${docker_image.vertex_julia.name}
     EOT
   }
 }

resource "google_workbench_instance" "instance" {
  name = "workbench-instance"
  location = "us-west1-a"

  gce_setup {
    container_image {
      repository = docker_image.vertex_julia.name
    }
  }
}

output "repo_name" {
  value = local.repo_path
}

output "repo_url" {
  value = docker_image.vertex_julia.name

}
data "google_project" "project" {
}

output "project_number" {
  value = data.google_project.project.project_id
}
