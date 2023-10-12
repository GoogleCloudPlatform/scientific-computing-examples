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

import json
import os
import uuid
import yaml

from absl import app
from absl import flags
from google.api_core.operation import Operation
from google.cloud import batch_v1
from google.cloud import pubsub_v1

from typing import Iterable
from yaml.loader import SafeLoader

"""
We define multiple command line flags:
"""

FLAGS = flags.FLAGS

flags.DEFINE_string("config_file", None, "Config file in YAML")
flags.DEFINE_boolean("pubsub", False , "Run Pubsub Topic and Subscriber")
flags.DEFINE_string("previous_job_id", None, "For Pubsub restart, specifies topic to read from")
flags.DEFINE_string("project_id", None, "Google Cloud Project ID, not name")
flags.DEFINE_spaceseplist("volumes", None, "List of GCS paths to mount. Example, \"bucket_name1:mountpath1 bucket_name2:mountpath2\"" )
flags.DEFINE_boolean("create_job", False, "Creates job, otherwise just prints config.")
flags.DEFINE_boolean("list_jobs", False, "If true, list jobs for config.")
flags.DEFINE_string("delete_job", "", "Job name to delete.")
flags.DEFINE_boolean("debug", False, "If true, print debug info.")

# Required flag.
flags.mark_flag_as_required("config_file")

class PubSub:
  def __init__(self, job_id: str, config) -> None:
      """Class to create Pub/Sub related cloud resources.

      Used to create a topic and a subscription. 
      Topic name identical to job_id and subscription is `sub-` + job_id.

      Args: 
          config: 
            Contains the structure defined by the Config.yaml file. 
          job_id: 
            The name of the job, which becomes the name of the pubsub topic.

      Raises:
        None

      `project_id` is set  based on config, env, or argv in that order.
      """
      self.config = config
      self.job_id = job_id

      if self.config["project_id"]: 
        self.project_id = self.config["project_id"] 
      if os.environ.get('GOOGLE_CLOUD_PROJECT'): 
        self.project_id  = os.environ.get('GOOGLE_CLOUD_PROJECT') 
      if FLAGS.project_id:
        self.project_id = FLAGS.project_id

      publisher_options = pubsub_v1.types.PublisherOptions(enable_message_ordering=True)

      """
      Sending messages to the same region ensures they are received in order
      even when multiple publishers are used.
      """

      client_options = {"api_endpoint": f'{self.config["region"]}-pubsub.googleapis.com:443'}
      self.publisher = pubsub_v1.PublisherClient(
          publisher_options=publisher_options, client_options=client_options
      )

  def create_topic(self):
    """
    Creates a topic with name the same as Job.

    The `topic_path` method creates a fully qualified identifier
    in the form `projects/{project_id}/topics/{topic_id}`

    Args:
      None

    Returns:
      None
    """
    self.topic_path = self.publisher.topic_path(self.project_id, self.job_id)
    self.topic = self.publisher.create_topic(request={"name": self.topic_path})
    print(f"Created topic {self.topic_path}\n")

  def create_subscription(self, previous_job_id=None):
    """
    Creates a subscription with name the same as `sub-` + Job.

    Subscription will be ordered and have exactly one time delivery.

    Args:
      previous_job_id: if specified, the subscription is connected to a previous pubsub subscription.

    Returns:
      None
    """

    self.subscriber = pubsub_v1.SubscriberClient()
    self.subscription_id = "sub-" + self.job_id

    if previous_job_id:
      self.topic_path = self.publisher.topic_path(self.project_id, previous_job_id)
    else:
      self.topic_path = self.publisher.topic_path(self.project_id, self.job_id)

    self.subscription_path = self.subscriber.subscription_path(self.project_id, self.subscription_id)

    with self.subscriber:
      self.subscription = self.subscriber.create_subscription(
        request={
          "name": self.subscription_path, 
          "topic": self.topic_path,
          "enable_message_ordering": True,
          "enable_exactly_once_delivery": True,
        }
      )
    print(f"Created subscription {self.subscription_path}\n")
    

  def publish_fifo_ids(self):
    """
    Publish integer ID messages to the pubsub topic.

    Simple queue create via the Pubsub Topic to create queue. 
    If the queue is not fully pulled, the project can restart with the same queue.
    Picking up where it left off.

    Args:
      None

    Returns:
      None
    """
    self.order_key = "fifo"
    for i in range(0, self.config["task_count"] ):
        # Data must be a bytestring
        data = str(i).encode("utf-8")
        # When you publish a message, the client returns a future.
        future = self.publisher.publish(self.topic_path, data=data, ordering_key=self.order_key)
        print(f'Future: {future.result()}, Message: {data}')


    

class Jobs:

  def __init__(self, job_id: str, config) -> None:
    """
    Class to create all cloud resources for Batch Jobs

    Args:
      job_id: an arbitrary string to name the job.
      config: data structure from YAML to represent everything in the config file.

    Returns:
      None
    """
    self.config = config
    self.job_id = job_id
    
    #set  "project_id"  based on config, env, or argv in that order.
  
    if self.config["project_id"]: 
      self.project_id = self.config["project_id"] 
    if os.environ.get('GOOGLE_CLOUD_PROJECT'): 
      self.project_id  = os.environ.get('GOOGLE_CLOUD_PROJECT') 
    if FLAGS.project_id:
      self.project_id = FLAGS.project_id

  def _create_runnable(self) -> batch_v1.Runnable:

    self.runnable = batch_v1.Runnable()
    self.runnable.environment = batch_v1.Environment()
    self.runnable.environment = {"variables":{"JOB_ID": self.job_id}}

    if "container" in self.config:
      self.runnable.container = batch_v1.Runnable.Container()
      self.runnable.container.image_uri = self.config["container"]["image_uri"] 
      self.runnable.container.entrypoint =  self.config["container"]["entry_point"] 
      self.runnable.container.commands =  self.config["container"]["commands"] 
      self.runnable.container.options = "--privileged"
      if "install_gpu_drivers" in self.config:
        self.runnable.container.volumes.append("/var/lib/nvidia/lib64:/usr/local/nvidia/lib64")
        self.runnable.container.volumes.append("/var/lib/nvidia/bin:/usr/local/nvidia/bin")

    else:
      self.runnable.script = batch_v1.Runnable.Script()
      self.runnable.script.text = self.config["script_text"]
    return(self.runnable)

    
  def _create_task(self) -> batch_v1.TaskSpec:
    """
    _summary_

    :return: _description_
    :rtype: batch_v1.TaskSpec
    """
    self.task = batch_v1.TaskSpec()
    self.task.max_retry_count = 2
    self.task.max_run_duration = "604800s"

    self.task.volumes = []

    if "nfs_server" in self.config:

      nfs_server = batch_v1.NFS()
      nfs_server.server = self.config["nfs_server"]
      nfs_server.remote_path = self.config["nfs_remote_path"] if "nfs_remote_path" in self.config else "/nfshare"

      nfs_volume = batch_v1.Volume()
      nfs_volume.nfs = nfs_server
      nfs_volume.mount_path = self.config["nfs_path"] if "nfs_path" in self.config else "/mnt/nfs"

      self.task.volumes.append(nfs_volume)


# Use commmand line flags first, then config file, to set
# gcs bucket mounts
    if(FLAGS.volumes):
      self.volumes_list = []
      for volume_pair in FLAGS.volumes:
        (bucket_name, gcs_path) = volume_pair.split(":")
        self.volumes_list.append({"bucket_name":bucket_name, "gcs_path":gcs_path})
    elif "volumes" in self.config:
      self.volumes_list = self.config["volumes"]
    else:
      self.volumes_list = None
      

    if(not self.volumes_list is None):
      gcs_volume = batch_v1.Volume()
      for volume in self.volumes_list:
        gcs_bucket = batch_v1.GCS()
        gcs_bucket.remote_path = volume["bucket_name"]
        gcs_volume.mount_path = volume["gcs_path"]
        gcs_volume.gcs = gcs_bucket
        self.task.volumes.append(gcs_volume)
        if "container" in self.config:
          self.runnable.container.volumes.append(
            volume["gcs_path"]+":"+volume["gcs_path"]+":rw")

  # We can specify what resources are requoested by each task.

    resources = batch_v1.ComputeResource()
    resources.cpu_milli = self.config["cpu_milli"] if "cpu_milli" in self.config else 1000 
    resources.memory_mib = self.config["memory_mib"] if "memory_mib" in self.config else 102400
    resources.boot_disk_mib = self.config["boot_disk_mib"] if "boot_disk_mib" in self.config else 102400
    self.task.compute_resource = resources

    return(self.task)

    
  def _create_allocation_policy(self) -> batch_v1.AllocationPolicy:

      # Policies are used to define on what kind of virtual machines the tasks will run on.
      # In this case, we tell the system to use an instance template that defines all the
      # required parameters.

      self.allocation_policy = batch_v1.AllocationPolicy()
      self.instance = batch_v1.AllocationPolicy.InstancePolicyOrTemplate()
      self.instance_policy = batch_v1.AllocationPolicy.InstancePolicy()
      self.accelerator = batch_v1.AllocationPolicy.Accelerator()
      self.network_policy = batch_v1.AllocationPolicy.NetworkPolicy()
      self.network = batch_v1.AllocationPolicy.NetworkInterface()

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

      if "network" in self.config:
        if "no_external_ip_address" in self.config:
          self.network.no_external_ip_address = self.config["no_external_ip_address"]
          self.network.subnetwork = f'regions/{self.config["region"] }/subnetworks/{self.config["subnetwork"]}'
          
        self.network.network = f'projects/{ self.project_id }/global/networks/{self.config["network"]}'
        self.network_policy.network_interfaces = [self.network]
        self.allocation_policy.network = self.network_policy

      if "allowed_locations" in self.config:
        location_policy.allowed_locations = self.config["allowed_locations"]
        self.allocation_policy.location = location_policy

      return(self.allocation_policy)
    
  def _create_taskgroup(self):
      """ 
        Tasks are grouped inside a job using TaskGroups.
        Currently, it's possible to have only one task group.
      """

      self.group = batch_v1.TaskGroup()
      self.group.task_spec = self.task
      self.group.task_count = self.config["task_count"] if "task_count" in self.config else 1
      self.group.parallelism = self.config["parallelism"] if "parallelism" in self.config else 1
      self.group.task_count_per_node = self.config["task_count_per_node"] if "task_count_per_node" in self.config else 1

      return(self.group)

  def create_job(self):
      """Creates job after configuration is completed. 
      """

      self.job = batch_v1.Job()
      self.job.labels = self.config["labels"] if "labels" in self.config else {"env": "hpc", "type": "hpc"}

      self.job.task_groups = [self.group]
      self.job.allocation_policy = self.allocation_policy

      # We use Cloud Logging as it's an out of the box available option
      self.job.logs_policy = batch_v1.LogsPolicy()
      self.job.logs_policy.destination = batch_v1.LogsPolicy.Destination.CLOUD_LOGGING
      return(self.job)
    
  def _create_job_request(self) -> batch_v1.Job:

      # Define what will be done as part of the job.

      self._create_runnable()
      self._create_task()
      self.task.runnables = [self.runnable]
      self._create_taskgroup()
      self._create_allocation_policy()
      self.create_job()

      create_request = batch_v1.CreateJobRequest()
      create_request.job = self.job
      create_request.job_id = self.job_id
      
      # The job's parent is the region in which the job will run
      create_request.parent = f'projects/{ self.project_id }/locations/{self.config["region"]}'

      return(create_request)
  # [END batch_create_job_with_template]

  def delete_job(self, delete_job) -> Operation:
      """
      Triggers the deletion of a Job.

      Args:
        delete_job: name of the job to delete

      Returns:
          An operation object related to the deletion. You can call `.result()`
          on it to wait for its completion.
      """
      client = batch_v1.BatchServiceClient()

      return client.delete_job(name=f"projects/{self.project_id}/locations/{self.config['region']}/jobs/{delete_job}")

  def list_jobs(self) -> Iterable[batch_v1.Job]:
      """
      Get a list of all jobs defined in given region.

      Returns:
          An iterable collection of Job object.
      """
      client = batch_v1.BatchServiceClient()

      return client.list_jobs(parent=f"projects/{self.project_id}/locations/{self.config['region']}")



def parse_yaml_file(file_name: str):
  """
  Parse the provided YAML file to get the job configuration

  :param file_name: The path to the YAML configuration file
  :type file_name: str
  """
  with open(file_name) as f:
    data = yaml.load(f, Loader=SafeLoader)
    return(data)


def main(argv):
  """
  This is where the Job and Pubsub objects are created and used.

  :param argv: Standard commandline arguments
  :type argv: _type_
  """

  config = parse_yaml_file(FLAGS.config_file)


  jobid = config["job_prefix"] + uuid.uuid4().hex[:8]
  client = batch_v1.BatchServiceClient()

  jobs = Jobs(jobid, config)
  # This does not create the job yet
  create_request = jobs._create_job_request()

  if(FLAGS.delete_job):
    print("Deleting job")
    deleted_job = jobs.delete_job(FLAGS.delete_job)
    print(deleted_job.result)

    exit()

    
  if(FLAGS.list_jobs):
    print("Listing jobs")
    jobs = jobs.list_jobs()

    for job in jobs:
      print(job.name,"\t",job.status.state)

    exit()

  if FLAGS.debug:
    print(config)

    
    # If pubsub queue is required 
  if FLAGS.pubsub and not FLAGS.debug:
    pubsub = PubSub(jobid, config)

    # If there is a previous queue to read from:
    if FLAGS.previous_job_id:
      pubsub.create_subscription(previous_job_id=FLAGS.previous_job_id)
    else:
      pubsub.create_topic()
      pubsub.create_subscription()
      pubsub.publish_fifo_ids()

  if FLAGS.create_job:
    # Create the job
    print(client.create_job(create_request))
  else:
    print(create_request.job)
    

if __name__ == "__main__":
    """ This is executed when run from the command line """
    app.run(main)
