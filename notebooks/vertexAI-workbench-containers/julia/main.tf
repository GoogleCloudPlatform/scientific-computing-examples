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
  }
}

locals {
  #us-central1-docker.pkg.dev/openfoam-jrt/my-repository
  repo_url = "${google_artifact_registry_repository.my-repo.location}-docker.pkg.dev"
  repo_path = "${local.repo_url}/${google_artifact_registry_repository.my-repo.name}"
}


resource "google_artifact_registry_repository" "my-repo" {
  location      = "us-central1"
  repository_id = "my-repository"
  description   = "example docker repository"
  format        = "DOCKER"
  docker_config {
    immutable_tags = true
  }
}

resource "docker_image" "vertex_julia" {
  provider = docker
  name     = "${local.repo_path}/vertex-julia:1.0"
  build {
    context   = path.cwd
  }
}

#resource "docker_registry_image" "vertex_julia" {
#  name                 = docker_image.vertex_julia.name
#  insecure_skip_verify = true
#  keep_remotely        = true
#}

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

output "repo_name" {
  #us-central1-docker.pkg.dev/openfoam-jrt/my-repository
  value = local.repo_url
}

output "repo_url" {
  value = docker_image.vertex_julia.name

}
data "google_project" "project" {
}

output "project_number" {
  value = data.google_project.project.project_id
}
