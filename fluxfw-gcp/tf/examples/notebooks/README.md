# Flux Framework Notebook Example

This example demostrates how to deploy a [Jupyter notebook](https://jupyter.org/try-jupyter/lab/) in a flux allocation on GCP. Several
example notebooks are provided that illustrate using the [flux-framework Python API](https://flux-framework.readthedocs.io/projects/flux-core/en/latest/python/index.html) to interact
with flux programatically in a Jupyter context.

## Deployment

Initialize the deployment with the command:

```bash
terraform init
```

Make a copy of the `notebooks.tfvars.example` file:

```bash
cp notebooks.tfvars.example notebooks.tfvars
```

Modify the notebooks.tfvars to specify the desired configuration. For example you may want more than
one login node, you probably want more than one compute node, you may want a different machine_type, 
and/or you may want to add another node pool, etc.

Note that many of the module variables receive their values from the remote state of other components.

Deploy the cluster with the command:

```bash
terraform apply -var-file notebooks.tfvars
```

## Setup

### Node Allocation

Once the `terraform apply` command completes you can log into your cluster using the command:

```bash
gcloud compute ssh nb-login-001
```

Check the state of the cluster with the command:

```bash
flux resource list
```

When the cluster is ready you will see output that looks like:

```bash
     STATE PROPERTIES NNODES   NCORES    NGPUS NODELIST
      free x86-64,e2       1        2        0 nb-login-001
      free t2a,arm64       8      128        0 nb-compute-a-[001-008]
 allocated                 0        0        0
      down                 0        0        0
```

Now you can create an allocation for your work using the command:

```bash
flux alloc -N4 --requires=arm64
```

Flux will allocate four nodes and give you a new shell on one of them.

### Jupyter Installation

There are multiple ways to install the software required to run Jupyter notebooks. In this tutorial you
will install it via the `Miniconda` [conda](https://docs.conda.io/en/latest/) installer.

Download the latest version of `Miniconda`. There are versions for multiple processor architectures including
x86_64 and aarch64 (ARM). This tutorial is using instances running on ARM processors.

```bash
curl -L https://repo.anaconda.com/miniconda/Miniconda-latest-Linux-x86_64.sh -o Miniconda-latest-aarch64.sh
```

Install `conda` and then use it to install `jupyter-lab`

```bash
chmod a+x Miniconda-latest-aarch64.sh
./Miniconda-latest-aarch64.sh
```

Press `enter` to review the Conda license agreement. If it is acceptable type "yes" to proceed with 
the installation.

```bash
conda install jupyter-lab
```

## Operation

Two steps are required to run notebooks with JupyterLab. First you need to start the `jupyter-lab` server and then create an [ssh tunnel](https://www.ssh.com/academy/ssh/tunneling) so that you can access the interface via a web browser.

If you haven't done so already activate the `conda` environment:

```bash
conda activate
```

You will need the IP address of the node in your allocation where your flux shell is running. Execute the following
command to get the correct address:

```bash
ip a | grep '/32' | awk '{print($2)}' | cut -d'/' -f1
```

You will also need remember the flux cluster username that the OS Login mechanism assigned you:

```bash
echo $USER
```

Now you can start the JupyterLab server. Starting the server is accomplished with the command:

```bash
jupyter-lab --no-browser
```

which will produce output similar to:

```bash
[I 2022-12-09 17:10:17.505 ServerApp] jupyterlab | extension was successfully linked.
[I 2022-12-09 17:10:17.514 ServerApp] nbclassic | extension was successfully linked.
[I 2022-12-09 17:10:17.905 ServerApp] notebook_shim | extension was successfully linked.
[I 2022-12-09 17:10:17.979 ServerApp] notebook_shim | extension was successfully loaded.
[I 2022-12-09 17:10:17.980 LabApp] JupyterLab extension loaded from /home/ext_wkh_google_com/arm64/miniconda3/lib/python3.9/site-packages/jupyterlab
[I 2022-12-09 17:10:17.980 LabApp] JupyterLab application directory is /home/ext_wkh_google_com/arm64/miniconda3/share/jupyter/lab
[I 2022-12-09 17:10:17.984 ServerApp] jupyterlab | extension was successfully loaded.
[I 2022-12-09 17:10:17.990 ServerApp] nbclassic | extension was successfully loaded.
[I 2022-12-09 17:10:17.991 ServerApp] Serving notebooks from local directory: /home/ext_wkh_google_com
[I 2022-12-09 17:10:17.991 ServerApp] Jupyter Server 1.18.1 is running at:
[I 2022-12-09 17:10:17.991 ServerApp] http://localhost:8888/lab?token=50f3a3052239dba85b4fa15e02c8162e9409931c4a45df96
[I 2022-12-09 17:10:17.991 ServerApp]  or http://127.0.0.1:8888/lab?token=50f3a3052239dba85b4fa15e02c8162e9409931c4a45df96
[I 2022-12-09 17:10:17.991 ServerApp] Use Control-C to stop this server and shut down all kernels (twice to skip confirmation).
[C 2022-12-09 17:10:18.067 ServerApp] 
    
    To access the server, open this file in a browser:
        file:///home/a_user_name/.local/share/jupyter/runtime/jpserver-39720-open.html
    Or copy and paste one of these URLs:
        http://localhost:8888/lab?token=50f3a3052239dba85b4fa15e02c8162e9409931c4a45df96
     or http://127.0.0.1:8888/lab?token=50f3a3052239dba85b4fa15e02c8162e9409931c4a45df96
```

Note that the jupyter server is listening on the localhost interface of the node where your flux shell is running.
To access the interface from a web browser on your local machine you will create an `ssh tunnel` that forwards a
connection made to a port on your local machine to the node in your allocation where the jupyter server is running.

Open a terminal on your local machine. Before you create the tunnel copy some notebooks that demonstrate the
flux Python API to your cluster:

```bash
gcloud compute scp *.ipynb nb-login-001:~ --zone us-central1-a
```

Use this command to setup the ssh tunnel from your local machine to your server host:

```bash
export FLUX_CLUSTER_USERNAME=# The flux cluster username you retrieved earlier #
export JUPYTER_SERVER_IP=# The ip address of the node in your allocation where the jupyter server is listening #

gcloud compute ssh nb-login-001 --zone us-central1-a -- -L 8888:localhost:8888 -t ssh -L 8888:localhost:8888 ${FLUX_CLUSTER_USERNAME}@${JUPYTER_SERVER_IP}
```

When the tunnel is established you can access the jupyter lab server running in your allocation via a 
web browser on your local machine. Just paste either of the `http` URLs from the output juypter-lab
start up output into a local web browser and press `enter`. You should see output that looks like

![JupyterLab](./images/jupyterlab-interface.png)

You can double click on any of the .ipynb files to experiment with various aspects of the flux Python API, or
you can use the File menu to create a new notebook for your own work.
