# High-Performance Storage Architecture on Google Cloud

This document outlines storage design patterns for HPC workloads following the deprecation of Parallelstore.

## 1. Storage Tier Comparison

| Storage Tier | Technology | Best For | Throughput / IOPS | Protocol | Typical Mount |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Hot Scratch** | Local NVMe SSD (RAID-0) / Hyperdisk Balanced | Intermediate solver temp files, OpenFOAM processor directories, checkpoint buffers | >2.4M IOPS, up to 10 GB/s per VM | POSIX (ext4/xfs) | `/scratch` |
| **Shared Warm** | Filestore High Scale / Enterprise | Shared application binaries, Spack store, multi-node homedirs, datasets | Up to 26 GB/s, 700k IOPS | NFSv3 / NFSv4 | `/apps`, `/home` |
| **Parallel File** | Managed Lustre (DDN EXAScaler) | High-throughput parallel shared I/O across hundreds of compute nodes | Up to hundreds of GB/s, millions of IOPS | Lustre Client | `/lustre` |
| **Object Cold** | Cloud Storage (GCS) + GCS FUSE | Long-term reference datasets, raw mesh geometry, final results archive | Scales with bucket egress, sub-second cached access | HTTP API / FUSE POSIX | `/gcs`, `gs://` |

## 2. Local SSD RAID-0 Configuration for Compute Nodes

To maximize solver I/O and prevent NFS bottlenecks during intensive write cycles (e.g. transient CFD timesteps or MD trajectory dumps), configure attached NVMe SSDs into a striped RAID-0 array via node startup scripts.

Filtering specifically on `/dev/disk/by-id/google-local-nvme-ssd-*` and `/dev/disk/by-id/google-local-ssd-*` ensures only local ephemeral NVMe SSDs are included and prevents accidentally formatting attached secondary Hyperdisk or Persistent Disk volumes:

```bash
#!/bin/bash
# Assemble all attached NVMe Local SSDs into a high-speed RAID-0 scratch filesystem safely.
# Avoids destroying attached Hyperdisk or Persistent Disk NVMe devices.
local_ssd_devices=$(ls /dev/disk/by-id/google-local-nvme-ssd-* /dev/disk/by-id/google-local-ssd-* 2>/dev/null || true)

if [ -n "$local_ssd_devices" ]; then
    num_devices=$(echo "$local_ssd_devices" | wc -w)
    echo "Found $num_devices Local SSD devices. Building RAID-0 /dev/md0..."
    mdadm --create /dev/md0 --level=0 --raid-devices="$num_devices" $local_ssd_devices
    mkfs.xfs -f /dev/md0
    mkdir -p /scratch
    mount -o noatime,nodiratime,logbufs=8,logbsize=256k,largeio,inode64,allocsize=64M /dev/md0 /scratch
    chmod 777 /scratch
fi
```

## 3. Filestore Tuning for HPC Clusters

When mounting Filestore High Scale over NFS across dozens or hundreds of compute nodes, apply the following mount parameters in `/etc/fstab` to avoid RPC bottlenecks:

```text
<FILESTORE_IP>:/nfsshare  /apps  nfs  rw,hard,rsize=1048576,wsize=1048576,timeo=600,retrans=2,noatime,nodiratime,_netdev  0 0
```
