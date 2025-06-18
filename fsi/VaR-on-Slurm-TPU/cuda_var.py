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
Run MC simulation for VaR portfolio risk
"""

import avro.schema
import io
import importlib
import numpy as np
import os
import time
import yfinance as yf
import time

from absl import app
from absl import flags
from avro.io import DatumWriter, BinaryEncoder
from datetime import datetime
from datetime import timedelta
from google.cloud import pubsub_v1
from google.cloud.pubsub import SchemaServiceClient


PROJECT_ID = 'ai-infra-jrt-2'
INCOMING_TOPIC_ID = 'fsimontecarlo_topic_3531e9e7'
INCOMING_TOPIC_SCHEMA = 'fsimontecarlo_schema_3531e9e7'
DATASET_ID = 'fsimontecarlo_dataset_969eaff0'
TABLE_ID = 'fsimontecarlo_table_25f6bf11'

FLAGS = flags.FLAGS

flags.DEFINE_string("ticker", 'GOOG', "Nasdaq Stock Ticker to run, default GOOG")
flags.DEFINE_string("start_date", '2022-01-01' , "Start data for data query, default 2022-01-01")
flags.DEFINE_integer("prng_seed", None , "Enter a random number seed for the simulation, defaults to time.")
flags.DEFINE_integer("calendar_days", 365 , "How many calendar days to include in the calculation")
flags.DEFINE_integer("epoch_time", f'{int(time.time())}' , "Epoch time, number of seconds since January 1st, 1970 at 00:00:00 UTC.")
flags.DEFINE_integer("iterations", 100 , "Number of iterations to run.")
flags.DEFINE_integer("pub_iterations", 100 , "Number of iterations to publish to BigQuery.")
flags.DEFINE_boolean("print_raw", False, "Dump raw data.")
flags.DEFINE_boolean("debug", False, "Print debug info.")
flags.DEFINE_boolean("jax", False, "Use JAX based code")
flags.DEFINE_boolean("cuda", False, "Use CUDA based code")
flags.DEFINE_boolean("quiet", True, "Don't print informational output.")
flags.DEFINE_enum("jax_platform", "cuda",["cuda","rocm","cpu","tpu"],"Acceptable values for jax_platform")


def dynamic_import(module_name):
  """Dynamically imports a module."""
  try:
    module = importlib.import_module(module_name)
    return module
  except ImportError:
    return None  # Or raise the exception, depending on your needs

class VaRSimulator:
  def  __init__(self):
    pass

  def get_seed_from_time(self):
    """
    Generates a random number seed based on the current time.

    Returns:
        An integer seed value.
    """
    # Get the current time in seconds since the epoch
    current_time = time.time()

    # Convert the time to an integer and return it as the seed
    return int(current_time)

  def  get_data(self):
    self.get_historical_data_yahoo()
  
  def get_historical_data_yahoo(self):

  # get historical market data: https://pypi.org/project/yfinance/

    self.raw_data = yf.Ticker(self.ticker).history(start=self.start_date, end=self.end_date )
    self.data = self.raw_data.Close

  def print_raw(self):
    print(self.get_stats())
    print(type(self.raw_data))
    print(self.raw_data)

  def get_stats(self):
    close = self.data
    self.first = close.iloc[0]
    self.last = close.iloc[-1]
    self.trading_days = len(close)
    self.cagr = (self.last / self.first) ** (365.0/self.calendar_days) -1.0
    self.volatility =  self.data.pct_change().std()
    return(self.first, self.last, self.trading_days, self.cagr, self.volatility)

  def create_record(self):

    results = self.get_returns_slice(self.iteration)

    self.record = {
      "ticker": self.ticker,
      "epoch_time": self.epoch_time,
      "iteration": self.iteration,
      "start_date": self.start_date,
      "end_date": self.end_date,
      "simulation_results": list(map(lambda x: {"price":x}, results))
    } 
    return(self.record)

def jit_simulation(iterations=1000000,
                   trading_days=365,
                   cagr=1.0,
                   volatility=1.0,
                   last=1.0,
                   seed=1234
                   ):

  returns = jax.random.normal(seed, shape=(trading_days,iterations)) \
            * volatility + (1 + cagr/trading_days)

  returns1 = jnp.ones((1,iterations))
  returns = jnp.concatenate([returns1, returns], axis=0)
  simulation_results = last * jnp.cumprod(returns, axis=0)
  return(simulation_results)

class JaxSimulator(VaRSimulator):
  def  __init__(self):
    os.environ["JAX_PLATFORMS"] = FLAGS.jax_platform
    global jax
    global jnp
    import jax
    import jax.numpy as jnp
    jax.config.update("jax_enable_x64", True)

    if(FLAGS.prng_seed):
      self.seed = jax.random.PRNGKey(FLAGS.prng_seed)
    else:
      self.seed = jax.random.PRNGKey(self.get_seed_from_time())

  def run_simulation(self):
    run_jit = jax.jit(jit_simulation)
    self.iterations = FLAGS.iterations

    self.simulation_results = run_jit(
                     self.iterations,
                     self.trading_days,
                     self.cagr,
                     self.volatility,
                     self.last,
                     self.seed
                     )
    return(self.simulation_results)

  def old_run_simulation(self):
    self.iterations = FLAGS.iterations

    returns = jax.random.normal(self.seed, shape=(self.trading_days,self.iterations)) \
              * self.volatility + (1 + self.cagr/self.trading_days)

    returns1 = jnp.ones((1,self.iterations))
    returns = jnp.concatenate([returns1, returns], axis=0)
    self.simulation_results = self.last * jnp.cumprod(returns, axis=0)
    return(self.simulation_results)

  def get_returns_slice(self, slice_number):
    simulation_slice = self.simulation_results[:,slice_number]
    return(np.array(simulation_slice))

class CudaSimulator(VaRSimulator):
  def  __init__(self):
    global cp
    import cupy as cp
    if(FLAGS.prng_seed):
      cp.random.seed(FLAGS.prng_seed)
    else:
      cp.random.seed(self.get_seed_from_time())

  def run_simulation(self):
    self.iterations = FLAGS.iterations

    returns = cp.random.normal(self.cagr/self.trading_days,
                               self.volatility,
                               size=(self.trading_days,self.iterations)) + 1 
    returns1 = cp.ones((1,self.iterations))
    returns = cp.concatenate((returns1, returns), axis=0)
    self.simulation_results = self.last * returns.cumprod(axis=0)
    return(self.simulation_results)

  def get_returns_slice(self, slice_number):
    simulation_slice = self.simulation_results[:,slice_number]
    return(cp.asnumpy(simulation_slice))

class Simulator(VaRSimulator):

  def  __init__(self):
    pass


  def run_simulation(self):
    self.iterations = FLAGS.iterations

    returns = np.random.normal(self.cagr/self.trading_days,
                               self.volatility,
                               size=(self.trading_days,self.iterations)) + 1 
    returns1 = np.ones((1,self.iterations))
    returns = np.concatenate((returns1, returns), axis=0)
    self.simulation_results = self.last * returns.cumprod(axis=0)
    return(self.simulation_results)

  def get_returns_slice(self, slice_number):
    simulation_slice = self.simulation_results[:,slice_number]
    return(simulation_slice)


class PubsubToBiquery:

  def __init__(self):

    the_time = int(time.time())

    self.project_id = PROJECT_ID

    self.publisher_client = pubsub_v1.PublisherClient()
    self.topic_path = self.publisher_client.topic_path(self.project_id, INCOMING_TOPIC_ID)

    self.schema_client = SchemaServiceClient()
    self.schema_path = self.schema_client.schema_path(self.project_id, INCOMING_TOPIC_SCHEMA)

    pubsub_schema = self.schema_client.get_schema(request={"name": self.schema_path})
    avro_schema = avro.schema.parse(pubsub_schema.definition)
    if(FLAGS.debug):
      print(avro_schema)

    self.writer = DatumWriter(avro_schema)


  def publish_record(self,record):

    byte_stream = io.BytesIO()
    encoder = BinaryEncoder(byte_stream)
    self.writer.write(record, encoder)
    data = byte_stream.getvalue()
    byte_stream.flush()
    future = self.publisher_client.publish(self.topic_path, data)
    if(FLAGS.debug):
      print(record)
    #if(not FLAGS.quiet):
    print(f"Published message ID: {future.result()}")


def main(argv):



  global vr
  if(FLAGS.jax):
    vr = JaxSimulator()
  if(FLAGS.cuda):
    vr = CudaSimulator()
  if(not FLAGS.cuda and not FLAGS.jax):
    vr = Simulator()
  pbbq = PubsubToBiquery()

  vr.ticker =FLAGS.ticker
  vr.start_date =FLAGS.start_date
  vr.end_date =f'{(datetime.strptime(FLAGS.start_date,"%Y-%m-%d") + timedelta(days = FLAGS.calendar_days)).date()}'
  vr.calendar_days = FLAGS.calendar_days
  vr.epoch_time = FLAGS.epoch_time
  vr.iteration = 1

  vr.get_data()
  vr.get_stats()

  start_time = time.time()
  vr.run_simulation()
  print("--- %s seconds ---" % (time.time() - start_time))

  for i in range(FLAGS.pub_iterations):
    vr.iteration = i
    pbbq.publish_record(vr.create_record())

  if(FLAGS.print_raw):
    vr.print_raw()
  


if __name__ == "__main__":
  """ This is executed when run from the command line """
  app.run(main)
