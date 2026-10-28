  I have executed the HPC Storage Quota Reporter skill ( storage_quota_skill ) for regions  us-central1  (Iowa),  us-east4  (N.
  Virginia), and  us-west1  (Oregon) with a target deployment of 10 TB per region.

  The full report has been compiled into the artifact:
  📄 storage_quota_report.md

  ### Summary of Storage Analysis ( us-central1 ,  us-east4 ,  us-west1 )

  1. Filestore Zonal (NFS High-Performance):
      • Capacity & Headroom: Easily accommodates your 10 TB target in all three regions (10 TB is the entry capacity for Zonal High-
      Scale). Quota headroom is 100 TB in  us-central1  and 50 TB in  us-east4 / us-west1 .
      • Best Fit: Shared application stacks ( /apps ), Spack/Conda module repos, shared home directories.
  2. Filestore Basic / Regional:
      • Capacity & Headroom: Accommodates 10 TB with standard quota headroom (100 TB in  us-central1 , 50 TB in  us-east4 / us-west1
      ).
      • Best Fit: High-availability multi-zone persistent datasets.
  3. Managed Lustre:
      • Capacity & Headroom: Quota headroom of 100 TB ( us-central1 ) and 50 TB ( us-east4 / us-west1 ).
      • Cluster Provisioning Note: Managed Lustre has a minimum cluster size of 12 TB (slightly above the 10 TB target).
      • Best Fit: Ultra-high throughput scratch space ( /scratch ), parallel I/O, checkpointing, and IOPS-heavy HPC runs.
