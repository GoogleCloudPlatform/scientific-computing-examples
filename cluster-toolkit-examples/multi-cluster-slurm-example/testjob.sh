#!/bin/bash
#SBATCH --job-name=slurmtest         # Name of the job
#SBATCH --output=slurmtest_%j.out    # Standard output log (%j is replaced by the Job ID)
#SBATCH --error=slurmtest_%j.err     # Standard error log
#SBATCH --time=00:01:00              # Time limit (hh:mm:ss) - set to 1 minute
#SBATCH --ntasks=1                   # Number of tasks (processes)
#SBATCH --cpus-per-task=1            # Number of CPU cores per task

# Print the hostname of the machine executing the job
hostname