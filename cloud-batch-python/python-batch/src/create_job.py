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

# [START batch_create_job_with_template]

import json
import re
import sys

from google.cloud import batch_v1
from io import TextIOWrapper, BytesIO

class CreateJob:
  def __init__(self, job_name: str, config) -> None:
    self.config = config
    self.job_name = job_name
    
  def create_runnable(self) -> batch_v1.Runnable:

    self.runnable = batch_v1.Runnable()
    self.runnable.environment = batch_v1.Environment()
    self.runnable.environment = {"variables":{"JOB_ID": self.job_name}}

    if "container" in self.config:
      self.runnable.container = batch_v1.Runnable.Container()
      self.runnable.container.image_uri = self.config["container"]["image_uri"] 
      self.runnable.container.entrypoint =  self.config["container"]["entry_point"] 
      self.runnable.container.commands =  self.config["container"]["commands"] 
      self.runnable.container.options  =  self.config["container"]["options"] if "options" in self.config["container"] else None
    else:
      self.runnable.script = batch_v1.Runnable.Script()
      self.runnable.script.text = self.config["script_text"]
    return(self.runnable)

    
  def create_task(self) -> batch_v1.TaskSpec:
    self.task = batch_v1.TaskSpec()
    self.task.max_retry_count = 2
    self.task.max_run_duration = "3600s"

  # set up storage volumes

    self.task.volumes = []

    if "nfs_server" in self.config:

      nfs_server = batch_v1.NFS()
      nfs_server.server = self.config["nfs_server"]
      nfs_server.remote_path = self.config["nfs_remote_path"] if "nfs_remote_path" in self.config else "/nfshare"

      nfs_volume = batch_v1.Volume()
      nfs_volume.nfs = nfs_server
      nfs_volume.mount_path = self.config["nfs_path"] if "nfs_path" in self.config else "/mnt/nfs"

      self.task.volumes.append(nfs_volume)

    if "bucket_name" in self.config:
      gcs_bucket = batch_v1.GCS()
      gcs_bucket.remote_path = self.config["bucket_name"]
      
      gcs_volume = batch_v1.Volume()
      gcs_volume.gcs = gcs_bucket
      gcs_volume.mount_path = self.config["gcs_path"] if "gcs_path" in self.config else "/mnt/gcs"

      self.task.volumes.append(gcs_volume)

  # We can specify what resources are requested by each task.

    resources = batch_v1.ComputeResource()
    resources.cpu_milli = self.config["cpu_milli"] if "cpu_milli" in self.config else 1000 
    resources.memory_mib = self.config["memory_mib"] if "memory_mib" in self.config else 102400
    resources.boot_disk_mib = self.config["boot_disk_mib"] if "boot_disk_mib" in self.config else 102400
    self.task.compute_resource = resources

    return(self.task)

  def create_allocation_policy(self) -> batch_v1.AllocationPolicy:

      # Policies are used to define on what kind of virtual machines the tasks will run on.
      # In this case, we tell the system to use an instance template that defines all the
      # required parameters.

      self.allocation_policy = batch_v1.AllocationPolicy()
      self.instance = batch_v1.AllocationPolicy.InstancePolicyOrTemplate()
      self.instance_policy = batch_v1.AllocationPolicy.InstancePolicy()
      self.accelerator = batch_v1.AllocationPolicy.Accelerator()

      if "template_link" in self.config:
        self.instance.instance_template = self.config["template_link"]
      elif "machine_type" in self.config:
        self.instance_policy.machine_type = self.config["machine_type"]
        self.instance.policy = self.instance_policy

        if "accelerator" in self.config:
          self.accelerator.type_ = self.config["accelerator"]["type"]
          self.accelerator.count = self.config["accelerator"]["count"]
          self.instance_policy.accelerators = [self.accelerator]
        if "install_gpu_drivers" in self.config:
          self.instance.install_gpu_drivers = True
        self.instance.policy = self.instance_policy
          
      else:
        raise(Error("No instance policy defined."))

      location_policy = batch_v1.AllocationPolicy.LocationPolicy()
        
      self.allocation_policy.instances = [self.instance]

      if "allowed_locations" in self.config:
        location_policy.allowed_locations = self.config["allowed_locations"]
        self.allocation_policy.location = location_policy

      return(self.allocation_policy)
    
  def create_taskgroup(self):
      # Tasks are grouped inside a job using TaskGroups.
      # Currently, it's possible to have only one task group.

      self.group = batch_v1.TaskGroup()
      self.group.task_spec = self.task
      self.group.task_count = self.config["task_count"] if "task_count" in self.config else 1
      self.group.parallelism = self.config["parallelism"] if "parallelism" in self.config else 1
      self.group.task_count_per_node = self.config["task_count_per_node"] if "task_count_per_node" in self.config else 1

      return(self.group)

  def create_job(self):
      self.job = batch_v1.Job()
      self.job.labels = self.config["labels"] if "labels" in self.config else {"env": "fluent", "type": "fluent"}

      self.job.task_groups = [self.group]
      self.job.allocation_policy = self.allocation_policy

      # We use Cloud Logging as it's an out of the box available option
      self.job.logs_policy = batch_v1.LogsPolicy()
      self.job.logs_policy.destination = batch_v1.LogsPolicy.Destination.CLOUD_LOGGING
      return(self.job)
    
  def create_script_job(self) -> batch_v1.Job:

      # Define what will be done as part of the job.

      self.create_runnable()
      self.create_task()
      self.task.runnables = [self.runnable]
      self.create_taskgroup()
      self.create_allocation_policy()
      self.create_job()

      create_request = batch_v1.CreateJobRequest()
      create_request.job = self.job
      create_request.job_id = self.job_name
      
      # The job's parent is the region in which the job will run
      create_request.parent = f'projects/{ self.config["project_id"] }/locations/{self.config["region"]}'

      return(create_request)
  # [END batch_create_job_with_template]