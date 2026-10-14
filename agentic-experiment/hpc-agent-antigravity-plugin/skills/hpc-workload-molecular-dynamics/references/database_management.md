# Reference Database Staging & Caching Runbook

## 1. Problem Statement
Protein structure prediction (AlphaFold, ColabFold, OpenFold) relies on massive sequence databases (UniRef30, BFD, PDB70, MGnify) exceeding 3.5 TB. Fetching these over NFS during inference causes major I/O bottlenecks.

## 2. Recommended Caching Pattern
1. **Primary Master Copy**: Keep the uncompressed databases in a regional Google Cloud Storage bucket (e.g. `gs://org-alphafold-databases/`).
2. **Local SSD Tier**: On cluster node startup or batch initialization, sync the database subset to local NVMe RAID-0 `/scratch`:
   ```bash
   mkdir -p /scratch/db
   gsutil -m rsync -r gs://org-alphafold-databases/uniref30/ /scratch/db/uniref30/
   ```
3. **ColabFold Direct MMseqs2**: Use GPU-accelerated MMseqs2 indexing on the local NVMe cache for sub-minute MSA construction.
