# Running Docker with Slurm


## Get the repo
Currently this is in a fork from the main `slurm-gcp` repository. If you are reading this, you have the correct repo.

## Go to the example folder

If you are reading this you are there, otherwise, it is under `examples/docker`

## Edit the TF Vars file

1. Copy [basic.tfvars.example](basic.tfvars.example) to `basic.tfvars`
1. Edit [basic.tfvars](basic.tfvars) to add your project on line 2. 
1. *Optional* Edit [basic.tfvars](basic.tfvars) to change the zone where your compute nodes will run.
1. *Optional* Edit [basic.tfvars](basic.tfvars) to change the GPU type your compute nodes will support.


## Run Terraform

If you don't have `terrform` go to `terraform.io` to get the download.

1. Initialize terraform
	```
	terraform init
	```
1. Run the make command to apply the terrform
	```
	make apply
	```

When this completes successfully you will see an output similar to this.

	Outputs:

	config = <sensitive>
	controller_name = "docker-controller"
	controller_network_ips = [
	"10.0.0.2",
	]
	login_names = [
	"g1-login0",
	]
	login_network_ips = [
	"10.0.0.3",
	]
	zone = "us-east4-c"

In the GCP console for your project, under `VM Instances`, you will see two VMs created. You can see this in your shell with the command:
```
gcloud compute instances list
```
The output should be

```
NAME           ZONE        MACHINE_TYPE   PREEMPTIBLE  INTERNAL_IP  EXTERNAL_IP  STATUS
g1-controller  us-east4-c  n1-standard-2               10.0.0.2                  RUNNING
g1-login0      us-east4-c  n1-standard-2               10.0.0.3                  RUNNING
```

## Connect to the login node
To submit a GPU job, you need to login to the `login` noded. 

There are two options.

### 1 - Connect to the login node via the gcloud CLI
If you prefer shell operations, use the following instructions.

Upload the two files required to run the "hello world" GPU job. 
```
gcloud compute scp hello.*  g1-login0:~
```
Connect to the login node.
```
 gcloud compute ssh g1-login0
```

Skip the next section.

### 2 - Connect to the login node via the console

In the GCP Console, click on the "SSH" button next to the listing of the `g1-login0`.
Once you are connected, you can upload the two files required to run the "hello world" GPU job. There is a "gear" icon in the upper right of the login window created when you clicked the button. You will need to navigate to the correct folder to find them.

```
hello.cu
hello.job
```
## Compile `hello.cu`

The image used in the Slurm build uses an HPC image supported by Google Cloud. This includes the Nvidia compiler. 

To compile `hello.cu`, run:
```
nvcc hello.cu -o hello
```

## Submit the job to Slurm
Once the code is successfully compiled, it can be run on a compute node as
```
sbatch hello.job
```
You should see a positive message.
```
Submitted batch job 2
```
You can then observe if the job is in the queue.
```
squeue
```
You should see output.
```
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
                 3       gpu GPUexamp ext_jros CF       0:04      1 g1-compute-1-0
```
You can repeat `squeue` until the job is no longer listed. 

Finally, there will be output in `out.txt`.
``` 
Hello World from CPU!
Hello World from GPU! 0
Hello World from GPU! 1
```
This indicates that the code ran on the CPU and the GPU. 

Congratulations, you have run a job on the GPU partition of your Slurm cluster

## Cleaning up

In order to avoid billing charges, you should destroy the cluster. 
```
make destroy
```
