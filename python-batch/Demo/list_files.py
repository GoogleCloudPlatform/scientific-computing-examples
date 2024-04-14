#!/usr/bin/env python3
#  Copyright 2024 Google LLC
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

"""
import random

from absl import app
from absl import flags
from google.cloud import storage

FLAGS = flags.FLAGS
flags.DEFINE_string("source_bucket", "sb_input", "Source Cloud Storage bucket")
flags.DEFINE_string("source_path", "Job1/", "Source objects path")
flags.DEFINE_string("destination_bucket", "sb_output", "Destination Cloud Storage bucket")
flags.DEFINE_string("working_bucket", "sb_working", "Working Cloud Storage bucket")

class Processor():
  def process(self, cloud_storage_blob):
    self.bytes = cloud_storage_blob.download_as_bytes()
    print(cloud_storage_blob.name)
    print(self.bytes)
    try:
      exec(self.bytes)
      return(True)
    except Exception:
      print("Process failed: {cloud_storage_blob.name}")
      return(False)

    

class StorageManager(storage.Client):
  def __init__(self, source_bucket_name, source_path, working_bucket_name, destination_bucket_name, delimiter="/"):
    super().__init__()
    self.client = super()
    self.source_bucket_name = source_bucket_name
    self.source_path = source_path
    self.working_bucket_name = working_bucket_name
    self.destination_bucket_name = destination_bucket_name
    self.delimiter = delimiter
    self.source_bucket = self.client.bucket(self.source_bucket_name)
    self.destination_bucket = self.client.bucket(self.destination_bucket_name)
    self.working_bucket = self.client.bucket(self.working_bucket_name)
    self.blob_list = self.client.list_blobs(
      self.source_bucket_name,
      prefix=self.source_path,
      delimiter=self.delimiter
    )

  def select_blob(self):
    # convert to Tuple so we can count and select at random

    self.selected_blob = next(self.blob_list, None)
    if(self.selected_blob is None):
      print(f"Processed all files found at source bucket ({self.source_bucket_name}) and path ({self.source_path})")
      return(None)
    return(self.selected_blob)

  def move_blob(self, blob, target_bucket):

    # This generation ensure that the file does not exist at the destination
    destination_generation_match_precondition = 0

    blob_copy = None
    blob.bucket
    try: 
      # attempt the copy
      blob_copy =blob.bucket.copy_blob(
        blob, 
        target_bucket, 
        blob.name, 
        if_generation_match=destination_generation_match_precondition,
      )
      # delete source if no exception
      blob.bucket.delete_blob(blob.name)
    except Exception:
      print(f"Can't move file {blob.name}")
      return(None)
    return(blob_copy)

  def process_files(self, processor):
    while True:
      selected_blob = self.select_blob()
      if(selected_blob is None):
        # if selected_blob is None, it means no target files were found
        break
      else:
        working_blob = self.move_blob(selected_blob, self.working_bucket)
        if(working_blob is not None):
          print("Begin Processing")
          if(processor.process(working_blob)):
            print("Processing is Complete")
            final_blob = self.move_blob(working_blob, self.destination_bucket)
            if(final_blob is not None):
              print(f"Process Complete")
            else:
              print(f"Process Failed")
          else:
            print("Processing Failed")
        else:
          print(f"Failed to copy to working directory")

def main(argv):

  store_man = StorageManager(
    source_bucket_name = FLAGS.source_bucket,
    source_path = FLAGS.source_path,
    working_bucket_name = FLAGS.working_bucket,
    destination_bucket_name = FLAGS.destination_bucket
  )

  processor = Processor()

  store_man.process_files(processor)

if __name__ == "__main__":
    """ This is executed when run from the command line """
    app.run(main)

