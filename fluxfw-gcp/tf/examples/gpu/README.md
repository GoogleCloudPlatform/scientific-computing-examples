Flux Framework GPU Example - Cluster Deployment

This deployment uses the [Flux Framework Cluster Module]() to bring together the remote state from the foundation deployment
with the Flux Framework images built with Cloud Build to instantiate a cluster of Compute Engine instances
with attached NVIDIA GPUs managed by the Flux Framework resource job management software.

# Usage

Initialize the deployment with the command:

```bash
terraform init
```

Make a copy of the `gpu.tfvars.example` file:

```bash
cp gpu.tfvars.example gpu.tfvars
```

Modify the gpu.tfvars to specify the desired configuration. For this example only one instance with 
a single GPU attached is required. Feel free, however, to add additional nodes and/or additional GPUs
up to your available quota.

Note that many of the module variables receive their values from the remote state of other components.

Deploy the cluster with the command:

```bash
terraform apply -var-file gpu.tfvars
```

### Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| cluster_storage | A map with keys 'share' and 'mountpoint' describing an NFS export and its desired mount point | map(string) | n/a | yes |
| compute_node_specs | A list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', and 'instances' which describe the compute node instances to create | list(maps(string)) | n/a | yes |
| compute_scopes | The set of access scopes for compute node instances | set(string) | [ "cloud-platform" ] | yes |
| login_node_specs | A list of maps each with the keys: 'name_prefix', 'machin_arch', 'machine_type', `gpu_count`, `gpu_type` and 'instances' which describe the login node instances to create | list(map(string)) | n/a | yes |
| login_scopes | The set of access scopes for login node instances | set(string) | [ "cloud-platform" ] | yes |
| manager_machine_type | The Compute Engine machine type to be used for the management node, not must be an x86_64 or AMD machine type | string | n/a | yes |
| manager_name_prefix | The name prefix for the management node instance, the full instance name will be this prefix followed by node number | string | n/a | yes |
| manager_scopes | The set of access scopes for management node instance | set(string) | [ "cloud-platform" ] | yes |
| project_id | The GCP project ID | string | n/a | yes |
| region | The GCP region where the cluster resides | string | n/a | yes |
| service_account_emails | A map with keys: 'compute', 'login', 'manager' that map to the service account to be used by the respective nodes | map(string) | n/a | yes |
| subnetwork | Subnetwork to deploy to | string | n/a | yes |

# Example Code

## Setup

### Node Allocation

Once the `terraform apply` command completes you can log into your cluster using the command:

```bash
gcloud compute ssh gpuex-login-001
```

While the cluster `manager` and `login` nodes are up the GPU compute node may take up to thirty minutes to finish installing 
the Julia programming language and the NVIDIA drivers and runtime. Julia and its associated CUDA libraries are installed via
the `install_juliacuda.sh` script which is run at compute node boot time.

Check the state of the compute node with the command:

```bash
flux resource list
```

When the compute node is ready you will see output that looks like:

```bash
     STATE PROPERTIES NNODES   NCORES    NGPUS NODELIST
      free x86-64,e2       1        2        0 gpuex-login-001
      free n1,x86-64       1        4        1 gpuex-compute-a-001
 allocated                 0        0        0
      down                 0        0        0
```

Once the compute node is ready you can allocate it with the command:

```bash
flux alloc -N1 -c4 -g1
```

Flux will allocate the node and give you a new shell on it. Now you can start working with the GPU attached to it. 

## SAXPY

The _single-precision a*x + y_ (*SAXPY*) program is one of the _hello world_ codes for parallel programming. In this section
you will run multiple versions of SAXPY that illustrate the range of Julia/GPU possibilities. Each of the codes you will run
come from the excellent HPC.NRW [video](https://youtu.be/6pYUhi5zhPE) _Several Ways to SAXPY: Julia + CUDA.jl_.

### Serial SAXPY

Start the Juila REPL using the command

```bash
JULIA_DEPOT_PATH=/usr/local/share/applications/julia/depot:$JULIA_DEPOT_PATH ; juila -t4
```

As a base-line here is a simple serial version of SAXPY:

```julia
julia> const dim = 100_000_000;
julia> const a = 3.1415;

julia> x = ones(Float32, dim);
julia> y = ones(Float32, dim);
julia> z = zeros(Float32, dim);

julia> z .= a .* x .+ y
```

This code uses Julia's [broadcasting](https://docs.julialang.org/en/v1/manual/arrays/#Broadcasting) mechanism to make even
the serial version as simple and efficient as possible. To measure the runtime you can use the `@benchmark` macro from the
`BenchmarkTools` package:

```julia
julia> using BenchmarkTools
julia> @benchmark z .= a .* x .+ y
```

```bash
BenchmarkTools.Trial: 49 samples with 1 evaluation.
 Range (min … max):  101.848 ms … 105.649 ms  ┊ GC (min … max): 0.00% … 0.00%
 Time  (median):     103.208 ms               ┊ GC (median):    0.00%
 Time  (mean ± σ):   103.256 ms ± 794.319 μs  ┊ GC (mean ± σ):  0.00% ± 0.00%

 Memory estimate: 128 bytes, allocs estimate: 4.
```

### CUArray SAXPY

For array-based problems like SAXPY Julia provides `CUArrays` that behave like regular arrays except that their
values reside on the GPU-device and operations on them take place in parallel on the GPU. The code is identical 
to the serial version save for the CUDA annocations:

```julia
julia> x_d = CUDA.ones(Float32, dim);
julia> y_d = CUDA.ones(Float32, dim);
julia> z_d = CUDA.zeros(Float32, dim);

julia> CUDA.@sync z_d .= a .* x_d .+ y_d
```

Note the use of the `CUDA.@sync` macro. By default code run on the GPU executes asynchronous. The `CUDA.@sync` macro tells Julia
to wait for the GPU code to complete before continuing.

Again, you can use the `@benchmark` macro to see how much faster, if any, the parallel code runs:

```julia
julia> @benchmark CUDA.@sync z_d .= a .* x_d .+ y_d
```
```bash
BenchmarkTools.Trial: 2682 samples with 1 evaluation.
 Range (min … max):  1.691 ms …  15.258 ms  ┊ GC (min … max): 0.00% … 0.00%
 Time  (median):     1.827 ms               ┊ GC (median):    0.00%
 Time  (mean ± σ):   1.855 ms ± 271.584 μs  ┊ GC (mean ± σ):  0.00% ± 0.00%

 Memory estimate: 6.14 KiB, allocs estimate: 102.
```

Runtimes will vary but you can see that for large vectors the parallel version is significantly faster.

### SAXPY Kernel Function

While it is good practice to use the CUArray approach whenever possible Julia also makes it easy to write GPU _kernel fuctions_, 
code that executes directly on the GPU-device. The details of writing GPU kernel functions are outside the scope of this tutorial.
However, the following code shows how SAXPY would be written as a kernel function:

```julia
julia> function saxpy_gpu_kernel!(z,a,x,y)
           i = (blockIdx().x - 1) * blockDim().x + threadIdx().x
           if i <= length(z)
               @inbounds z[i] = a * x[i] + y[i]
           end
           return nothing
       end
saxpy_gpu_kernel! (generic function with 1 method)
```
```julia
julia> nthreads = CUDA.attribute(device(), CUDA.DEVICE_ATTRIBUTE_MAX_THREADS_PER_BLOCK);
julia> nblocks = cld(dim, nthreads);
julia> CUDA.@sync @cuda(threads=nthreads, blocks=nblocks, saxpy_gpu_kernel!(z_d,a,x_d,y_d))
```

Benchmarking the kernel shows only a marginal improvement over the CUArray.

```julia
julia> @benchmark CUDA.@sync @cuda(threads=nthreads, blocks=nblocks, saxpy_gpu_kernel!(z_d,a,x_d,y_d))
```
```bash
BenchmarkTools.Trial: 2756 samples with 1 evaluation.
 Range (min … max):  1.624 ms …   2.390 ms  ┊ GC (min … max): 0.00% … 0.00%
 Time  (median):     1.800 ms               ┊ GC (median):    0.00%
 Time  (mean ± σ):   1.806 ms ± 101.343 μs  ┊ GC (mean ± σ):  0.00% ± 0.00%

 Memory estimate: 4.69 KiB, allocs estimate: 85.
 ```
### CUBLAS SAXPY

The CUDA implementation of the _Basic Linear Algebra Subprograms_ (BLAS) package, CUBLAS, also provides an implementation
of SAXPY. The Julia CUDA package wraps many of the libraries included in NVIDIAs CUDA toolkit and CUBLAS is one of them.
So, in this last example you will call the CUBLAS `axpy!` function.

```julia
julia> using CUDA.CUBLAS
julia> CUDA.@sync CUBLAS.axpy!(dim,a,x_d,y_d)
```

Note that unlike the other examples which returned the computed values in a separate vector the CUBLAS `axpy!` function
modifies the `y` argument with the result of the computation. 

Benchmarking the CUBLAS function may show a very small improvement over the SAXPY kernel fuction.

```julia
julia> @benchmark CUDA.@sync CUBLAS.axpy!(dim,a,x_d,y_d)
```
```bash
BenchmarkTools.Trial: 2835 samples with 1 evaluation.
 Range (min … max):  1.615 ms …  2.213 ms  ┊ GC (min … max): 0.00% … 0.00%
 Time  (median):     1.742 ms              ┊ GC (median):    0.00%
 Time  (mean ± σ):   1.756 ms ± 81.147 μs  ┊ GC (mean ± σ):  0.00% ± 0.00%

 Memory estimate: 2.98 KiB, allocs estimate: 49.
```

### Summary

For _large_ inputs running even simple codes like SAXPY on a GPU can acheive significant speed ups. As demonstrated above
Julia makes GPU programming very approachable. Of course there are CUDA libraries for other common HPC languages like FORTRAN,
C/C++, and Python as well. You should choose the one that best fits your programming environment and skill set.
