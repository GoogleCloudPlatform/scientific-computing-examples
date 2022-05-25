# Flux Framework MPI Example - Cluster Deployment

This deployment uses the [Flux Framework Cluster Module]() to bring together the remote state from the foundation deployment
with the Flux Framework images built with Cloud Build to instantiate a cluster of Compute Engine instances.
The cluster will contain two pairs of nodes, one for each of Google Cloud's _compute-optimized_ machine types. You 
will use them to run a couple of simple MPI benchmarks.

In addition to demostrating the execution of MPI codes this example illustrates the use of user-specified properties and boot scripts.

# Usage

Initialize the deployment with the command:

```bash
terraform init
```

The file `benchmarking.tfvars` contains the cluster specification, deploy it with the command:

```bash
terraform apply -var-file benchmarking.tfvars
```

# Benchmarking

Once the `terraform apply` command completes you can log into your cluster using the command:

```bash
gcloud compute ssh benchmark-login-001 --zone us-central1-a
```

While the cluster `manager` and `login` nodes are up the compute nodes may take a few minutes to finish installing
the MPI benchmark tests via the `install-mpitests.sh` boot script. Each set of nodes defined by the cluster's 
`compute_node_specs` attribute may have an associated boot script that will be executed the first time each node
in the set boots. This example uses the same boot script for each pair of nodes to install the `mpitests-mpich`
package.

One or more user-specified properties may also be associated with each set of nodes defined by the cluster's
`compute_node_specs` attribute. This example uses this mechanism to associate the *Intel* property with the
C2 nodes and *AMD* with the C2D nodes. You will use these properties to select pairs of nodes on which to 
execute benchmarks.

Check the state of the cluster with the command:

```bash
flux resource list
```

When the cluster is ready you will see output that looks like:

```bash
     STATE PROPERTIES NNODES   NCORES    NGPUS NODELIST
      free x86-64,e2       1        2        0 benchmark-login-001
      free x86-64,c2,      2        8        0 intel-benchmark-compute-[001-002]
      free c2d,x86-64      2        8        0 amd-benchmark-compute-[001-002]
 allocated                 0        0        0 
      down                 0        0        0 
```

To see the properties associated with each nodelist use the command:

```bash
flux resource list -o "{state:>10} {properties:<25.25} {nnodes:>6} {ncores:>8} {ngpus:>8} {nodelist}"
```

```
     STATE PROPERTIES                NNODES   NCORES    NGPUS NODELIST
      free x86-64,e2                      1        2        0 benchmark-login-001
      free x86-64,c2,Intel                2        8        0 intel-benchmark-compute-[001-002]
      free c2d,x86-64,AMD                 2        8        0 amd-benchmark-compute-[001-002]
 allocated                                0        0        0 
      down                                0        0        0 
```

## MPI Execution

Running MPI codes on the flux-framework is simple. You use either the the `flux` *run* or *submit*
commands to run a job consisting of N copies of an MPI program launched together as a parallel job.

```bash
flux run -n N <mpi-code>
```

The flux runtime handles all the underlying details of correctly setting up the environment and running
the MPI code.

The next sections use the OSU MPI microbenchmarks to give concrete examples of simple, but useful, MPI jobs.

## Latency

The `osu_get_latency` benchmark measures one-way latency between two nodes. The sender node
sends a message of a certain size and waits for a reply from the receiver. The receiver gets the message
and responds with a message of the same size. The reported result for that message size is the 
average of the latencies measured over many iterations.

Note that this example is just an MPI demonstration. You are not measuring _optimal_ latency. There are many
ways to tune the environment for optimal performance that are beyond the scope of this example.

To run the latency benchmark interactively on Intel chips, use the command:

```bash
flux run -N2 --requires=Intel /usr/lib64/mpich/bin/mpitests-osu_get_latency
```

for AMD chips, use the command:

```bash
flux run -N2 --requires=AMD /usr/lib64/mpich/bin/mpitests-osu_get_latency
```

In each case you will have to wait for the command to complete. If you want to submit the benchmarks as
flux-framework jobs, use the commands:

```bash
flux submit -N2 --requires=Intel --output=intel.out /usr/lib64/mpich/bin/mpitests-osu_get_latency
flux submit -N2 --requires=AMD --output=amd.out /usr/lib64/mpich/bin/mpitests-osu_get_latency
```

In each case when the command or job finishes the output will resemble:

```
# OSU MPI_Get latency Test v5.8
# Window creation: MPI_Win_allocate
# Synchronization: MPI_Win_flush
# Size          Latency (us)
1                      34.06
2                      33.65
4                      33.58
8                      33.43
16                     33.62
32                     33.69
64                     33.54
128                    33.61
256                    34.09
512                    34.45
1024                   37.14
2048                   39.63
4096                   41.20
8192                   46.20
16384                  57.15
32768                  74.76
65536                 142.58
131072                144.79
262144                206.22
524288                376.56
1048576               815.16
2097152              1686.69
4194304              3567.82
```

## Bandwidth

The `osu_get_bw` benchmark measures the maximum sustained data rate that can be achieved at the network level.
The sender transmits a fixed number of back-to-back messages to the reciever and then waits for a response from
the receiver. The receiver only responds after it receives all the messages. After mulitple iterations the
bandwidth is computed based on the elapsed time, from the time the sender sends the first message until it
receives the response from the receiver, and the number of bytes sent by the sender.

Note that this example is just an MPI demonstration. You are not measuring _optimal_ bandwidth. There are many
ways to tune the environment for optimal performance that are beyond the scope of this example.

To run the bandwidth benchmark interactively on Intel chips, use the command:

```bash
flux run -N2 --requires=Intel /usr/lib64/mpich/bin/mpitests-osu_get_bw
```

for AMD chips, use the command:

```bash
flux run -N2 --requires=AMD /usr/lib64/mpich/bin/mpitests-osu_get_bw
```

In each case you will have to wait for the command to complete. If you want to submit the benchmarks as
flux-framework jobs, use the commands:

```bash
flux submit -N2 --requires=Intel --output=intel.out /usr/lib64/mpich/bin/mpitests-osu_get_bw
flux submit -N2 --requires=AMD --output=amd.out /usr/lib64/mpich/bin/mpitests-osu_get_bw
```

In each case when the command or job finishes the output will resemble:

```
# OSU MPI_Get Bandwidth Test v5.8
# Window creation: MPI_Win_allocate
# Synchronization: MPI_Win_flush
# Size      Bandwidth (MB/s)
1                       0.32
2                       0.63
4                       1.24
8                       2.53
16                      4.79
32                     10.43
64                     19.89
128                    38.56
256                    78.74
512                   130.86
1024                  170.63
2048                  347.62
4096                  637.08
8192                 1104.65
16384                1125.77
32768                1305.71
65536                1202.52
131072               1159.63
262144               1184.08
524288               1177.66
1048576              1154.64
2097152              1148.27
4194304              1140.76
```

## Summary

This example demonstrated the execution of real, but simple, MPI codes on a flux-framework cluster. 
It also illustrated the use of the `compute_node_specs` `boot_script` and `properties` attributes to
customize a set of compute nodes at boot time and associated user-specified properties with them for
use in controlling job execution.
