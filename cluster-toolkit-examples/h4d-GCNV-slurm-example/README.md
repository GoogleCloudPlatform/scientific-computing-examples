# GCP-Cluster-Toolkit-H4D-Slurm-GCNV 
Goolge Cloud Platform - Cluster Toolkit deployment with H4D, Slurm and Google Cloud NetApp Volumes sample

Reference:
https://cloud.google.com/netapp/volumes/docs/discover/overview
https://github.com/GoogleCloudPlatform/cluster-toolkit
PR: https://github.com/GoogleCloudPlatform/cluster-toolkit/pull/4583

As of Nov 2025, Goolge Cloud NetApp Volumes are not in the main branch yet. Here is the instruction on pulling the code:

1. Clone the Latest Cluster Toolkit 

```
git clone https://github.com/GoogleCloudPlatform/cluster-toolkit.git
```

2. Do the gh pr checkout 4583

```
cd cluster-toolkit
gh pr checkout 4583
```

Output:
```
$ gh pr checkout 4583
remote: Enumerating objects: 175, done.
remote: Counting objects: 100% (128/128), done.
remote: Compressing objects: 100% (48/48), done.
remote: Total 175 (delta 92), reused 108 (delta 80), pack-reused 47 (from 2)
Receiving objects: 100% (175/175), 65.76 KiB | 9.39 MiB/s, done.
Resolving deltas: 100% (117/117), completed with 24 local objects.
From https://github.com/GoogleCloudPlatform/cluster-toolkit
 * [new ref]             refs/pull/4583/head -> netapp-volume
Switched to branch 'netapp-volume'
```

3. Make sure the terraform version is at the latest Terraform version. The blueprint provided was tested with Terraform v1.15.0-dev on linux_amd_64.

Then one can use the cluster Toolkit ./gcluster command to deploy the cluster:

```
./gcluster deploy -w netapp-h4d.yaml
```

## Validation:

1. we see netapp file system on all the instance and it is working with Filestore deployment:
```
$ df -h
Filesystem                      Size  Used Avail Use% Mounted on
devtmpfs                        7.7G     0  7.7G   0% /dev
tmpfs                           7.7G     0  7.7G   0% /dev/shm
tmpfs                           7.7G  8.5M  7.7G   1% /run
tmpfs                           7.7G     0  7.7G   0% /sys/fs/cgroup
/dev/sda2                        50G   18G   33G  36% /
/dev/sda1                       200M  5.9M  194M   3% /boot/efi
tmpfs                           1.6G     0  1.6G   0% /run/user/0
10.149.79.4:/netappfs           2.0T  384K  2.0T   1% /netapp
10.15.25.34:/homeshare          2.5T     0  2.4T   0% /home
netapph4d-controller:/opt/apps   50G   18G   33G  36% /opt/apps
tmpfs                           1.6G     0  1.6G   0% /run/user/1911945234
```

2. Slurm is working 

```
$ sinfo
PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
h4d*         up   infinite      1   idle netapph4d-h4dnodeset-0
```

3. Test job: (Created a test file: thomas-test on Netapp)
```  
$ srun ls /netapp
thomas-test
```
```
$ srun cat /netapp/thomas-test
This is test from Thomas
```