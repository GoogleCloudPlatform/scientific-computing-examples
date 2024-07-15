# Copyright 2019 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Shows the functionality of exec using a Busybox container.
"""

import time

import kubernetes.client
from kubernetes import config
from kubernetes.client import Configuration
import kubernetes.client.api_client
import google.cloud.container_v1 as container_v1




def exec_commands(api_instance):
  name = 'busybox-test'
  resp = None

  configuration = kubernetes.client.Configuration()
  print(configuration)

  container = kubernetes.client.V1Container(name="sleep")
  container.image = 'busybox'
  container.args = [
  '/bin/sh',
  '-c',
  'while true;do date;sleep 5; done'
  ]
  containers = [container]

  node_pool = container_v1.NodePool()
  node_pool.name = 'n1-standard-4'
  node_pool.autoscaling_algorithm = 'BestEffort'
  node_pool.autoscaling = True
  node_pool.node_selector = node_selector_terms()
  print(node_pool)

  horizontal_pod_autoscaler = kubernetes.client.V1HorizontalPodAutoscaler()
  horizontal_pod_autoscaler.metadata = kubernetes.client.V1ObjectMeta(name=name)
  horizontal_pod_autoscaler.spec = kubernetes.client.V1HorizontalPodAutoscalerSpec()
  horizontal_pod_autoscaler.spec.max_replicas = 5
  horizontal_pod_autoscaler.spec.min_replicas = 1
  
  
  metadata=kubernetes.client.V1ObjectMeta(name=name)

  pod = kubernetes.client.V1Pod(api_version='v1', kind='Pod', metadata=metadata)

  podspec = kubernetes.client.V1PodSpec(containers=containers)
  pod.spec = podspec

  podspec.restart_policy = 'Never'
  podspec.affinity = kubernetes.client.V1Affinity()
  podspec.affinity.node_affinity = kubernetes.client.V1NodeAffinity()

  user_toleration = kubernetes.client.V1Toleration()
  user_toleration.key = 'user-workload'
  user_toleration.operator = 'Equal'
  user_toleration.value = 'true'
  user_toleration.effect = 'NoSchedule'
  podspec.tolerations = [user_toleration]

  node_pool = kubernetes.client.V1Poo


  mt = kubernetes.client.V1TopologySelectorTerm()
  mt.match_label_selector = mt

  nst = node_selector_terms()

  ns = kubernetes.client.V1NodeSelector(node_selector_terms=nst)


  podspec.affinity.node_affinity.required_during_scheduling_ignored_during_execution = ns
      
  print(pod)
  resp = api_instance.create_namespaced_pod(body=pod, namespace='default')



def node_selector_terms():
  node_selector_terms=[
     kubernetes.client.V1NodeSelectorTerm(
         match_expressions=[
             kubernetes.client.V1NodeSelectorRequirement(
                 key="cloud.google.com/gke-nodepool",
                 operator="In",
                 values=[
                     "n1-standard-4"
                 ],
             )
         ]
     ),
  ]
  return(node_selector_terms)

def main():
  config.load_kube_config()
  try:
      c = Configuration().get_default_copy()
  except AttributeError:
      c = Configuration()
      c.assert_hostname = False
  Configuration.set_default(c)
  core_v1 = kubernetes.client.api.CoreV1Api()

  exec_commands(core_v1)

if __name__ == '__main__':
    main()
