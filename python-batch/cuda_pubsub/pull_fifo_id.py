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

from absl import app
from absl import flags
from google.api_core import retry
from google.cloud import pubsub_v1

FLAGS = flags.FLAGS
flags.DEFINE_bool("debug", False, "Print out extra info")
flags.DEFINE_string("project_id", None, "Google Cloud Project ID, not name")
flags.DEFINE_string("job_id", None, "Job ID")


def main(argv):
  subscription_id = "sub-" + FLAGS.job_id

  subscriber = pubsub_v1.SubscriberClient()
  subscription_path = subscriber.subscription_path(FLAGS.project_id, subscription_id)
  pull_response= subscriber.pull(subscription=subscription_path, max_messages=1)

  if FLAGS.debug: print(pull_response.received_messages)

  for msg in pull_response.received_messages:
      message = msg.message.data.decode('utf-8')
      # do your thing
      print(message)
      if FLAGS.debug: print(msg.ack_id)
      subscriber.acknowledge(subscription=subscription_path, ack_ids=[msg.ack_id])

if __name__ == "__main__":
  """ This is executed when run from the command line """
  app.run(main)
