#!/usr/bin/env python3
"""
Tools to run batch API
"""

__author__ = "J Ross Thomson drj@"
__version__ = "0.0.0"

from absl import app
from absl import flags

from venv import create
import list_jobs
import delete_job
import create_job
import create_container_job
import parse_yaml
import uuid
from google.cloud import batch_v1


FLAGS = flags.FLAGS
flags.DEFINE_string("config_file", None, "Config file in YAML")
flags.DEFINE_boolean("create_job", False, "Creates job, otherwise just prints config.")
flags.DEFINE_boolean("list_jobs", False, "If true, list jobs for config.")
flags.DEFINE_boolean("container", False, "If true, run container jobs.")
flags.DEFINE_string("delete_job", "", "Job name to delete.")
flags.DEFINE_boolean("debug", False, "If true, print debug info.")

# Required flag.
flags.mark_flag_as_required("config_file")

def main(argv):

  config = parse_yaml.parse_yaml_file(FLAGS.config_file)

  if(FLAGS.delete_job):
    print("Deleting job")
    deleted_job = delete_job.delete_job(config["project_id"], config["region"], FLAGS.delete_job)
    print(deleted_job.result)

    exit()

    
  if(FLAGS.list_jobs):
    print("Listing jobs")
    jobs = list_jobs.list_jobs(config["project_id"], config["region"])

    for job in jobs:
      print(job.name,"\t",job.status.state)

    exit()

    

  jobid = config["job_prefix"] + uuid.uuid4().hex[:8]
  client = batch_v1.BatchServiceClient()

  if(FLAGS.container):
    print("Container job")
    print(create_container_job.create_container_job(jobid, config))
    exit()
	
  create = create_job.CreateJob(jobid, config)
  
  create_request = create.create_script_job()

  if FLAGS.debug:
    print(config)

  if FLAGS.create_job:
    print(client.create_job(create_request))
  else:
    print(create_request)
    

if __name__ == "__main__":
    """ This is executed when run from the command line """
    app.run(main)
