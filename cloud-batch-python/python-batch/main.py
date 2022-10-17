#!/usr/bin/env python3
"""
Tools to run batch API
"""

__author__ = "J Ross Thomson drj@"
__version__ = "0.0.0"

from venv import create
import list_jobs
import create_with_template

def main():
  print("hello world")
  #print(list_jobs.list_jobs("wdc-hpc-demo1", "us-central1") )
  print(create_with_template.create_script_job_with_template("wdc-hpc-demo1", 
                                                             "us-central1", 
                                                             "samp",
                                                             "projects/wdc-hpc-demo1/global/instanceTemplates/wdc-hpc") )




if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()