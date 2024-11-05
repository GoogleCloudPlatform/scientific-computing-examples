# OpenRadioss Simulation and Visualization

[OpenRadioss](https://openradioss.org/) is publicly available FEA software for simulation of impact, shock and highly dynamic events. OpenRadioss primarily uses the same input format and source code as the commercial software Altair® Radioss® that is widely used in industry. In this demonstration you will run OpenRadioss across multiple cores and nodes in Slurm-based HPC system deployed via [Cluster Toolkit](https://cloud.google.com/cluster-toolkit/docs/overview). Your demo will use one of OpenRadioss's example models, the ["Yaris Impact Model in LS-DYNA® format"](https://openradioss.atlassian.net/wiki/spaces/OPENRADIOSS/pages/30539777/Yaris+Impact+Model+in+LS-DYNA+format) model. To make the demonstration more interesting you will use [Paraview](https://www.paraview.org/) to visualize the result of the simulation. The visualization will be served from a compute node with an attached GPU in the HPC system you deploy. For those who use [LS-Prepost](https://lsdyna.ansys.com/knowledge-base/ls-prepost/) for visualization, this demo includes [Vortex-Radioss](https://github.com/Vortex-CAE/Vortex-Radioss) library. This library is an open-source Python CAE tool that enables the reading of Radioss Animation files, Radioss Time-History files, and the conversion of Radioss Animation files into LS-Dyna's D3plot format.

The demonstration will leverage a number of techniques illustrated in various Apptainer [examples](../../examples/) and is based on work done at [CIQ](https://ciq.com/blog/integrating-site-specific-mpi-with-an-openfoam-official-apptainer-image-on-slurm-managed-hpc-environments/) and [OpenRadioss community](https://ciq.com/blog/running-camry-impact-model-in-ls-dyna-format-using-openradioss-and-apptainer/).

In particular you will build an [OpenMPI](https://www.open-mpi.org/) container configured for [PMIx](https://pmix.github.io/) and use that in combination with the standard [OpenRadioss container](https://github.com/OpenRadioss/OpenRadioss/tree/main/Apptainer) to create a custom PMIx enabled OpenRadioss container you will use to run the parallel simulation portion of the demo.

<video controls>
    <source src="./images/surfacevideo.mp4" type="video/mp4">
</video>

### Before you begin
This demonstration assumes you have access to an [Artifact Registry](https://cloud.google.com/artifact-registry) repository and that you have set up the Apptainer custom build step. See [this section](../../README.md#before-you-begin) for details.

## Containers

You will use [Cloud Build](https://cloud.google.com/build?hl=en) to build four containers as part of this demonstration
- [ompi4-pmix](./resources/ompi4-pmix.def) which packages OpenMPI built with Slurm PMIx support enabled
- [openradioss](./resources/openradioss.yaml) OpenRadioss, commit: dd81219ac16c01f13f917b812f420d9d7aa641bd, tag: latest-20240729
- [openradioss-pmix](./resources/openradioss-pmix.def) OpenRadioss repackaged to use the Slurm PMIx enabled OpenMPI runtime
- [paraview](./resources/paraview.yaml) ParaView 5.12.0 EGL version.
-[vortex-radioss](./resources/vortex-radioss.yaml) Vortex-Radioss, AnimToD3plot conversion package

All of the Apptainer definition files and Cloud Build configurations are in the [resources](./resources/) directory. Change to that directory now
```bash
cd resources
```

If you are in a hurry you can build all the containers at once using the command
```bash
gcloud builds submit --config=containers.yaml .
```

Go back to the parent directory
```bash
cd ..
```

Now you can skip to the [HPC System Deployment](#hpc-system-deployment) section of this demostration.

### OpenRadioss && OpenMPI

One of the goals of this demo is to illustrate using OpenMPI in a self-contained manner without relying on the HPC system's MPI runtime(s). This approach simplifies running containerized MPI codes, by eliminating the need to to complex _bind mounts_ from the compute nodes into the container(s), and makes the solution more portable since it independent of the MPI runtime(s) installed on the HPC system. The [ompi4-pmix.def](./resources/ompi4-pmix.def) container definition adds the `--with-slurm` and `--with-pmi` flags to a standard OpenMPI build. The resulting runtime binaries will support the use of [PMI](https://www.mcs.anl.gov/papers/P1760.pdf) to do the necessary _wire-up_ at the beginning of an MPI computation.

All of the Apptainer definition files and Cloud Build configurations are in the [resources](./resources/) directory. Change to that directory now
```bash
cd resources
```

The command
```bash
gcloud builds submit --config=ompi4-pmix.yaml .
```

builds the PMI-enabled OpenMPI runtime container and stores it in Artifact Registry.

Next you build the OpenRadioss. You will use this container as part of a _multi-stage_ build which substitutes the `ompi4-pmix` OpenMPI 
runtime for the version installed as part of the standard OpenRadioss build. The [openradioss.yaml](./resources/openradioss.yaml) uses `git` to clone the OpenRadioss source and then builds the runtime in a [Rocky Linux](https://rockylinux.org/) based container.

Build this interim container with the command
```bash
gcloud builds submit --config=openradioss.yaml .
```

Now you are ready to combine the PMIx-enabled OpenMPI runtime with the OpenRadioss runtime. The [openradioss-pmix.def](./resources/openradioss-pmix.def) container definition uses a _multi-stage_ build to assemble the container from the `ompi4-pmix` and `openradioss` containers. The build first pulls in the PMIx-enabled OpenMPI container
```
Bootstrap: oras
From: {{ LOCATION }}/{{ PROJECT_ID }}/{{ REPO }}/ompi4-pmix:{{ OMPI4_PMIX_VERSION }}
Stage: mpi
```

Next the OpenRadioss container is loaded and the PMIx-enabled OpenMPI runtime is copied over from the OpenMPI container
```
Bootstrap: oras
From: {{ LOCATION }}/{{ PROJECT_ID }}/{{ REPO }}/openradioss:{{ OPENRADIOSS_VERSION }}
Stage: runtime

%files from mpi
    /opt/openmpi /opt/openmpi4-pmix

%post
    rm -rf /opt/openmpi
    mv /opt/openmpi4-pmix /opt/openmpi
```

[Note the use of Apptainer definition file templating to make the container definition configurable]

Finally the `slurm` package is installed and some environment variable instantiation is configured and the container is ready to go.

You build it using the command
```bash
gcloud builds submit --config=openradioss-pmix.yaml .
```

### ParaView

Build Kitware official [ParaView Server for Headless Machines](https://www.paraview.org/download/) v5.12.0 EGL version container.
```bash
gcloud builds submit --config=paraview.yaml .
```

Go back to the parent directory
```bash
cd ..
```

### Vortex-Radioss

Build Vortex-Radioss container.

```bash
gcloud builds submit --config=vortex-radioss.yaml .
```

Go back to the parent directory
```bash
cd ..
```


## HPC System Deployment

Use the [OpenRadioss blueprint](./hpc/openradioss-demo.yaml) in the `hpc` directory as the basis for your HPC system. It is conifgured to deploy two partitions. 
- A `compute` partition that will dynamically allocate up to 10 [compute-optimized](https://cloud.google.com/compute/docs/compute-optimized-machines#c2_machine_types) C2-Standard-60 instances.
- A `gpu` that will dynamically allocate up to 4 [general-purpose](https://cloud.google.com/compute/docs/general-purpose-machines#n1_machines) N1-STANDARD-8 instances.

Change directories to the `hpc` directory
```bash
cd hpc
```

Now you can create the deployment artifacts with the command

```bash
gcluster create openradioss-demo.yaml --vars project_id=$(gcloud config get core/project) --skip-validators=test_tf_version_for_slurm
```

You should see output that looks like

```
To deploy your infrastructure run:

glucster deploy openradiossdemo

Find instructions for cleanly destroying infrastructure and advanced manual
deployment instructions at:

openradiossdemo/instructions.txt
```

Per the instructions, bring up your HPC system with the command
```bash
gcluster deploy openradiossdemo --auto-approve
```

Go back to the parent directory
```bash
cd ..
```

## Login node

SSH via IAP tunnel with the command
```bash
gcloud compute ssh \
  $(gcloud compute instances list --filter="NAME ~ login" --format="value(NAME)") \
  --tunnel-through-iap
```

## Simulation

This demonstration uses one of the models from OpenRadioss official website(https://openradioss.org/models/).

Download Yaris Impact Model in LS-DYNA® format from CCSA and OpenRadioss launch file.
```bash
wget -q https://media.ccsa.gmu.edu/model/2010-toyota-yaris-detailed-v2j.zip
unzip 2010-toyota-yaris-detailed-v2j.zip
cd 2010-toyota-yaris-detailed-v2j
wget -q -O YarisOpenRadioss.key https://openradioss.atlassian.net/wiki/download/attachments/30539777/YarisOpenRadioss.key?api=v2
```

Go back to the parent directory
```bash
cd ..
```

Now create a `job.sh` file that specifies the compute environment for the simulation and all the tasks to be carried out as part of the simultion.

```bash
cat << EOF > job.sh
#!/bin/bash
#SBATCH --partition=compute
#SBATCH --nodes=3
#SBATCH --ntasks-per-node=30

cd ~/2010-toyota-yaris-detailed-v2j

openradioss starter_linux64_gf -i YarisOpenRadioss.key -np 90

export PMIX_MCA_gds=hash
srun --mpi=pmix apptainer run --sharens ~/bin/openradioss engine_linux64_gf_ompi -i YarisOpenRadioss_0001.rad
EOF
```

Set up access to the Artifact Registry repository

```bash
export REGISTRY_URL=#ARTIFACT REGISTRY URL# e.g. oras://us-docker.pkg.dev
export REPOSITORY_URL=#ARTIFACT REGISTRY REPOSITORY URL# e.g. oras://us-docker.pkg.dev/myproject/sifs
```

```bash
apptainer registry login \
--username=oauth2accesstoken \
--password=$(gcloud auth print-access-token) \ 
${REGISTORY_URL}
```

Pull the `openradioss-pmix` container and put it in `~/bin`
```bash
apptainer pull ${REPOSITORY_URL}/openradioss-pmix:latest
mkdir ~/bin
mv openradioss-pmix_latest.sif ~/bin/openradioss
```

Now you are ready to actually run the simultion with the command
```bash
sbatch job.sh
```

The HPC system will spin up 3 nodes and then begin running the simulation. Even with 90 cores it will take some time to complete the simulation. Once the nodes are up and the job is running you can watch its progress by tailing the slurm-`N`.out file
```bash
tail -f slurm-N.out
```
[where `N` is the Slurm job id of the simulation]

## Visualization

### Vortex-Radioss & LS-PrePost

Set up access to the Artifact Registry repository

```bash
export REGISTRY_URL=#ARTIFACT REGISTRY URL# e.g. oras://us-docker.pkg.dev
export REPOSITORY_URL=#ARTIFACT REGISTRY REPOSITORY URL# e.g. oras://us-docker.pkg.dev/myproject/sifs
```

```bash
apptainer registry login \
--username=oauth2accesstoken \
--password=$(gcloud auth print-access-token) \ 
${REGISTRY_URL}
```

Pull the `vortex-radioss` container and put it in `~/bin`
```bash
apptainer pull ${REPOSITORY_URL}/vortex-radioss:latest
mkdir ~/bin
mv vortex-radioss_latest.sif ~/bin/vortex-radioss
```

Change directories to the `$HOME` directory
```bash
cd
```

Convert ANIM format files to D3plot format files.
```bash
vortex-radioss
>>> from vortex_radioss.animtod3plot.Anim_to_D3plot import readAndConvert
>>> readAndConvert("2010-toyota-yaris-detailed-v2j/YarisOpenRadioss")
```
Exit container with `Ctrl + d` 


Create archirve with d3plot files
```bash
tar zcvf data.tgz 2010-toyota-yaris-detailed-v2j/YarisOpenRadioss.d3plot*
```

Download data from login node to local computer to visualize data with LS-PrePost.
```bash
gcloud compute scp $(gcloud compute instances list --filter="NAME ~ login" --format="value(NAME)"):~/data.tgz . --tunnel-through-iap
```

Open extracted file with LS-PrePost

<img src=./images/lsprepost.png alt="Open File" width=1024 />

### ParaView

Convert OpenRadioss ANIM format to VTK format
```bash
seq -f YarisOpenRadiossA%03g 021 | xargs -I{} sh -c '~/bin/openradioss anim_to_vtk_linux64_gf "$1" > "$1.vtk"' -- {}
```

#### Server

Now create a `vis.sh` file that specifies the compute environment for the visualization and to start ParaView server.

```bash
cat << EOF > vis.sh
#!/bin/bash
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --gpus-per-node=1

cd ~/2010-toyota-yaris-detailed-v2j
apptainer run --nv ~/bin/paraview pvserver
EOF
```

Set up access to the Artifact Registry repository

```bash
export REGISTRY_URL=#ARTIFACT REGISTRY URL# e.g. oras://us-docker.pkg.dev
export REPOSITORY_URL=#ARTIFACT REGISTRY REPOSITORY URL# e.g. oras://us-docker.pkg.dev/myproject/sifs
```

```bash
apptainer registry login \
--username=oauth2accesstoken \
--password=$(gcloud auth print-access-token) \ 
${REGISTRY_URL}
```

Pull the `paraview` container and put it in `~/bin`
```bash
apptainer pull ${REPOSITORY_URL}/paraview:latest
mkdir ~/bin
mv paraview_latest.sif ~/bin/paraview
```

Now you are ready to actually run the ParaView server with the command
```bash
sbatch vis.sh
```

You should see output similar to
```
Waiting for client...
Connection URL: cs://openradios-gpunodeset-0:11111
Accepting connection(s): openradios-gpunodeset-0:11111
```

#### Client

On a workstation, create an `ssh tunnel` using the command
```
gcloud compute start-iap-tunnel openradios-gpunodeset-0 11111 \
    --local-host-port=localhost:11111
```

Now start the `paraview` client that you downloaded. The first time you start it the client may take a few minutes to come up. Eventually you should
see the ParaView UI:

<img src=./images/pvui.png alt="Paraview UI" width=1024 />

To connect to the ParaView server, choose `Connect` from the `File menu`

<img src=./images/empty-connection-chooser.png alt="Empty Connection Configuration" width=512 />

Now click `Add Server` and configure a server named _ofdemo_ that uses the ssh tunnel you created earlier

<img src=./images/connection-config.png alt="Configure Connection" width=512 />

Click `Configure` and the new server configuration should be available. Choose it and click `Connect`

<img src=./images/connection-chooser.png alt="Chose Connection" width=512 />

The new connection will appear in the `Pipeline Browser`

<img src=./images/openradiossdemo-connected.png alt="Server Connected" width=256 />

Now you are ready to select the simulation results you want to visualize. Choose `Open` from the `File` menu.

<img src=./images/openradiossdemo-file.png alt="Open File" width=512 />

Click `Apply` and VTK will render in the `RenderView1`

<img src=./images/openradiossdemo-yaris.png alt="Open File" width=1024 />


For more details, please see work done at [CIQ](https://ciq.com/blog/google-cloud-hpc-toolkit-and-rocky-linux-8-hpc-vm-image/).

ParaView is a powerful visualizaton tool but a complete exploration of its capabilities is beyond the scope of this demonstration. We do, however, encourage you to dive into the documentation and tutorial material available online to learn more.

## Teardown

To bring down your HPC system use the command
```bash
gcluster destroy openradiossdemo
```
