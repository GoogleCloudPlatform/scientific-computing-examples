# GKE H4D with Dynamic Workload Scheduler (DWS) Flex-start & GCP Cluster Toolkit & Queued Provisioning Test Demo

This repository contains the configuration files for deploying a **Google Kubernetes Engine (GKE)** cluster utilizing **H4D machine types** with **Dynamic Workload Scheduling (DWS) Flex Start** and **Queued Provisioning** enabled for optimizing resource utilization in High-Performance Computing (HPC) workloads.


## 🚀 Deployment

The GKE infrastructure is provisioned using the `gcluster` blueprint deployment tool. This process automatically handles the creation of the necessary VPC networks, service accounts, the GKE cluster, and the specialized node pool.

## Create the Cluster

Navigate to your cluster toolkit directory and deploy the blueprint, using the files located in this repository as input.

```
cd ~/cluster-toolkit 
./gcluster deploy -d \
gke-h4d-dws-test-2/gke-h4d-deployment.yaml \
gke-h4d-dws-test-2/gke-h4d.yaml
```

### Key DWS Configuration Notes
The combination of DWS Flex Start and Queued Provisioning allows GKE to efficiently manage capacity for specialized, high-demand machine types like H4D, with a non-preemptible guarantee for the run duration.

### DWS Flex Start Requirements
Static Nodes: DWS Flex Start does not work with static node configurations. The static_node_count parameter cannot be set in the node pool configuration.

Auto Repair: To prevent disruptions to running Flex Start workloads, auto_repair should be explicitly set to false.

### Queued Provisioning Requirements
Queued Provisioning ensures that your job waits until the entire requested resource capacity is available before provisioning the nodes, which is crucial for gang-scheduled HPC workloads.

Queued provisioning does not work with static_node_count (already covered by Flex Start).

It requires the Cluster Autoscaler to be able to scale down completely: autoscaling_total_min_nodes must be set to 0.

## Run a Sample Job
The directory includes a sample-job.yaml file that demonstrates how to submit a Kubernetes Job that leverages the Queued Provisioning feature by using specific node selectors and annotations.

1. Connect to the Cluster
Use the gcloud command to connect your local environment to the newly created GKE cluster:

```
gcloud container clusters get-credentials <cluster-name> \
  --location <location> \
  --project <project-id>
```
Replace <cluster-name> with the name of your cluster, <location> with the compute region (e.g., us-central1), and <project-id> with your GCP project ID.

2. Submit the Job
Apply the sample job configuration:

```
kubectl apply -f gke-h4d-dws-test-2/sample-job.yaml
```

3. Monitor the Job
Use the following kubectl commands to track the status of the job and its associated pods:

Job Status:
```
kubectl get jobs
kubectl describe job <job-name>
Pod Status:
```

```
kubectl get pods
kubectl describe pod <pod-name>
```