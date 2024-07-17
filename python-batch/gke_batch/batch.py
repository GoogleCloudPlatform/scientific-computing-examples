#!/usr/bin/env python3
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

"""
Tools to run Google Cloud Batch API
"""

__author__ = "J Ross Thomson drj@"
__version__ = "0.1.0"

import os
import uuid
import yaml
import sys
import kubernetes.client

from absl import app
from absl import flags
from dynaconf import settings
from google.api_core.operation import Operation
from kubernetes.client import Configuration
from kubernetes.client.rest import ApiException
from pprint import pprint

from typing import Iterable
from yaml.loader import SafeLoader

"""
We define multiple command line flags:
"""

FLAGS = flags.FLAGS

flags.DEFINE_string("project_id", None, "Google Cloud Project ID, not name")
flags.DEFINE_boolean("create_job", False, "Creates job, otherwise just prints config.")
flags.DEFINE_boolean("list_jobs", False, "If true, list jobs for config.")
flags.DEFINE_string("delete_job", "", "Job name to delete.")
flags.DEFINE_boolean("debug", False, "If true, print debug info.")
flags.DEFINE_string("args_file", None, "TOML/YAML file with list of container commands")

def get_setting(setting, settings):
  if FLAGS.debug:
    print(f"Getting setting {setting}", file=sys.stderr)
  if setting in settings:
    return(settings[setting])
  else:
    print(f"Setting {setting} not found in settings file. Exiting.", file=sys.stderr)
    exit()

class KubernetesBatchJobs:
  def __init__(self) -> None:

    self.job_id = get_setting("job_id",settings)

    kubernetes.config.load_kube_config()
    try:
        self.kube_config = Configuration().get_default_copy()
    except AttributeError:
        self.kube_config = Configuration()
        self.kube_config.assert_hostname = False
    Configuration.set_default(self.kube_config)
    self.batch_v1 = kubernetes.client.BatchV1Api(kubernetes.client.ApiClient(self.kube_config))

    self.project_id = get_setting(setting="project_id",settings=settings)

    if os.environ.get('GOOGLE_CLOUD_PROJECT'): 
      self.project_id  = os.environ.get('GOOGLE_CLOUD_PROJECT') 
    if FLAGS.project_id:
      self.project_id = FLAGS.project_id

  def create_job_request(self):

    container1 = self._create_container()
    volumes1 = self._create_volumes()
    mounts1 = self._create_volume_mounts()
    container1.volume_mounts = mounts1
    pod_template1 = self._create_pod_template(container1, volumes1)

    # Create JobSpec
    parallelism = get_setting("parallelism", settings)
    suspend = get_setting("suspend", settings)
    job_spec=kubernetes.client.V1JobSpec(
      template=pod_template1, 
      suspend=suspend, 
      parallelism=parallelism
      )
    completion_mode = get_setting("completion_mode", settings)
    if completion_mode == "Indexed":
      completions = get_setting("completions", settings)
      job_spec.completion_mode = completion_mode
      job_spec.completions = completions

    # Create Job ObjectMetadata
    jobspec_metadata=kubernetes.client.V1ObjectMeta(
      name=self.job_id,
      labels={"app": self.job_id})
    # Create a V1Job object
    job = kubernetes.client.V1Job(
      api_version="batch/v1",
      kind="Job",
      spec=job_spec,
      metadata=jobspec_metadata,
    )
    return(job)

  def _create_volume_mounts(self):
    # Create Volume Mounts
    # Get volume settings
    mount_settings = get_setting("volume_mount", settings)
    volume_mount1 = kubernetes.client.V1VolumeMount(
      name="gcs-fuse-csi-ephemeral", 
      mount_path=mount_settings["mount_path"]
      )
    return([volume_mount1])

  def _create_volumes(self):
   # Create Volumes
    
    volume_settings = get_setting("volume", settings)

    volume_attributes1 = {"bucketName": volume_settings["bucketName"]}
    volume_source1 = kubernetes.client.V1CSIVolumeSource(
      driver=volume_settings["driver"],
      volume_attributes=volume_attributes1
      )
    volume1 = kubernetes.client.V1Volume(name="gcs-fuse-csi-ephemeral", csi=volume_source1)
    volumes = [volume1]
    return(volumes)

  def _create_container(self):

    # Get container settings
    container_settings = get_setting("container", settings)
    image = get_setting("image_uri", container_settings)

    # Get Job commands
    command = get_setting("command", settings)

    env1 = kubernetes.client.V1EnvVar(
      name = "JOB_ID",
      value = self.job_id
    )

    # Get Job Limits
    limits = get_setting("limits", settings)

    # Create container
    container = kubernetes.client.V1Container(
      name=f"{self.job_id}-container",
      image=image,
      command=command,
      resources=kubernetes.client.V1ResourceRequirements(
          limits=limits,
      ),
      env = [env1],
    )
    return(container)

  def _create_object_metadata(self):
    pass

  def _create_pod_template(self, container1, volumes):
    # Create Pod Template and PodSpec
    service_account_name = get_setting("service_account_name", settings)
    node_selector = get_setting("node_selector", settings)
    pod_annotations = get_setting("pod_annotations", settings)

    podspec_metadata=kubernetes.client.V1ObjectMeta(
      name=self.job_id, 
      labels={"app": self.job_id}, 
      annotations=pod_annotations
      )
    pod_spec=kubernetes.client.V1PodSpec(
      containers=[container1],
      restart_policy="Never",
      node_selector=node_selector,
      volumes=volumes,
      service_account_name=service_account_name,
      )
    # Create PodTemplateSpec
    pod_template=kubernetes.client.V1PodTemplateSpec(
      metadata=podspec_metadata,
      spec=pod_spec
      )
    return(pod_template)

  #
  # Here is where the jobs is actually created
  #
  def create_job(self, create_request):
  # Create the job in the cluster
    namespace = get_setting("namespace", settings)
    api_response = self.batch_v1.create_namespaced_job(
        namespace=namespace,
        body=create_request,
    )
    print(f"Job {self.job_id} created. Timestamp='{api_response.metadata.creation_timestamp}'" )


  def delete_job(self, job_id):
    namespace = get_setting("namespace", settings)
    try:
      api_response = self.batch_v1.delete_namespaced_job(job_id, namespace)
      print(api_response,file=sys.stderr)
    except ApiException as e:
      print("Exception when calling BatchV1Api->list_namespaced_job: %s\n" % e)


  def list_jobs(self):
    namespace = get_setting("namespace", settings)
    try:
      api_response = self.batch_v1.list_namespaced_job(namespace)
      for item in api_response.items:
        succeeded = item.status.succeeded
        failed = item.status.failed
        completed = item.status.completed_indexes
        print(f"Name: {item.metadata.labels['app']}\tSucceeded: {succeeded}\tFailed: {failed}\tCompleted Index: {completed}", file=sys.stderr)
    except ApiException as e:
      print("Exception when calling BatchV1Api->list_namespaced_job: %s\n" % e)

def main(argv):
  """
  """

  # Create unique job ID, required for Batch and k8s Jobs
  job_id = get_setting("job_prefix", settings) + uuid.uuid4().hex[:8]
  settings.job_id = job_id
  jobs = None
  if get_setting("platform", settings) == "gke-autopilot":
    jobs = KubernetesBatchJobs()
  else:
  # Create Cloud Batch jobs object
    print("platform must be set in the settings file. Exiting.")

  # Delete job. JobID must be passed.
  if(FLAGS.delete_job):
    print("Deleting job", file=sys.stderr)
    jobs.delete_job(FLAGS.delete_job)
    exit()

  # Prints list of jobs, in queue, running or complteted.
  if(FLAGS.list_jobs):
    print("Listing jobs", file=sys.stderr)
    jobs.list_jobs()
    exit()

  # Prints config file info
  if FLAGS.debug:
    pass

  if FLAGS.args_file:
    settings.load_file(path="args.toml")  # list or `;/,` separated allowed
    for arg in settings.ARGS: 
      print(f"This is the arg: {arg}")
      job_id = get_setting("job_prefix", settings) + uuid.uuid4().hex[:8]
      settings["job_id"] = job_id
      settings.command = arg
      jobs = KubernetesBatchJobs()
      print(jobs.create_job(jobs.create_job_request()), file=sys.stderr)
    exit()

    
  if FLAGS.create_job:
    # Create the job
    print(jobs.create_job(jobs.create_job_request()), file=sys.stderr)
  else:
    print(jobs.create_job_request(), file=sys.stderr)

if __name__ == "__main__":
    """ This is executed when run from the command line """
    app.run(main)
