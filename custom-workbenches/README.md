# Creating Custom VertexAI Workbench Instances for Scientific Machine Learning

The goal here is to establish a base set of workbench instances and learn how
to customize them to your needs.

Here are examples showing how to:
- [Create a Vertex AI Workbench Instance](example-simple-workbench.md)
- [Build and use your own Vertex AI Workbench Images](example-build-custom-workbench.md)

Beyond that we'll explore how these workbench instances might be used as
a "base of operations" for managing resources in Google Cloud.  From
a workbench, it can be useful to drive Vertex AI pipelines to train custom
models as well as use tools such as the HPC Toolkit (rebranded as the Google
Supercomputer Toolkit I think) to spin up and manage HPC clusters to run
simulation workloads on accelerated hardware.

![Typical compute cluster on GCP Architecture](media/typical-compute-cluster-architecture.png)

Here, we'll only focus on standing up a static cluster of standalone compute nodes
for testing instance types with other schedulers.  We focus on:

![standalone compute cluster on GCP Architecture](media/standalone-compute-cluster-architecture.png)

Please note that these are provided only as examples to help guide
infrastructure planning and are not intended for use in production. They are
deliberately simplified for clarity and lack significant details required for
production-worthy infrastructure implementation.

## What's next

There are so many exciting directions to take to learn more about what you've
done here!

Learn about what's new in
- [Vertex AI with Gemini](https://cloud.google.com/vertex-ai/docs/start/introduction-unified-platform)
- [High Performance Computing (HPC) on GCP](https://cloud.google.com/solutions/hpc?hl=en)
- Scientific Machine Learning on Google Cloud

