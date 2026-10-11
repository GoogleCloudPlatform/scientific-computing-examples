import subprocess
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def run_gcloud_command(args: list[str]) -> str:
    """
    Executes a gcloud command against GCP cloud projects and APIs.
    
    Args:
        args: A list of string arguments for the gcloud command. 
              For example, to run `gcloud compute instances list`, 
              pass ["compute", "instances", "list"].
              
    Returns:
        The standard output of the command if successful, or the error message if it fails.
    """
    try:
        cmd = ["gcloud"] + args
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error executing gcloud command (exit code {e.returncode}):\n{e.stderr}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

def deploy_cluster(blueprint_path: str, deployment_dir: str = "./deployments") -> str:
    """Deploys an HPC cluster using the Google Cloud HPC Toolkit (ghpc).
    
    Args:
        blueprint_path: The file path to the YAML blueprint (e.g., 'app/skills/hpc-clusterbuilder/examples/hpc-slurm.yaml').
        deployment_dir: The directory where the Terraform files should be generated.
        
    Returns:
        A string containing the output of the deployment process or an error message.
    """
    try:
        # Step 1: Generate the Terraform using ghpc
        ghpc_cmd = ["ghpc", "create", blueprint_path, "--vars", f"deployment_name=hpc-agent-deploy", "-w", deployment_dir]
        ghpc_result = subprocess.run(ghpc_cmd, capture_output=True, text=True, check=False)
        
        if ghpc_result.returncode != 0:
            return f"Failed to generate blueprint: {ghpc_result.stderr}"
            
        # Step 2: Apply the Terraform
        tf_dir = os.path.join(deployment_dir, "hpc-agent-deploy", "primary")
        if not os.path.exists(tf_dir):
            return f"Terraform directory not found at {tf_dir}. ghpc output: {ghpc_result.stdout}"
            
        subprocess.run(["terraform", "-chdir=" + tf_dir, "init"], check=True, capture_output=True)
        tf_result = subprocess.run(["terraform", "-chdir=" + tf_dir, "apply", "-auto-approve"], capture_output=True, text=True, check=False)
        
        if tf_result.returncode == 0:
            return f"Cluster deployed successfully!\n{tf_result.stdout}"
        else:
            return f"Cluster deployment failed:\n{tf_result.stderr}"
    except Exception as e:
        return f"Error deploying cluster: {str(e)}"


def destroy_cluster(deployment_dir: str = "./deployments/hpc-agent-deploy/primary") -> str:
    """Tears down an existing HPC cluster using Terraform.
    
    Args:
        deployment_dir: The path to the primary Terraform directory.
        
    Returns:
        A string containing the result of the destroy operation.
    """
    try:
        if not os.path.exists(deployment_dir):
            return f"Deployment directory {deployment_dir} does not exist."
            
        tf_result = subprocess.run(["terraform", "-chdir=" + deployment_dir, "destroy", "-auto-approve"], capture_output=True, text=True, check=False)
        
        if tf_result.returncode == 0:
            return f"Cluster destroyed successfully!\n{tf_result.stdout}"
        else:
            return f"Cluster destruction failed:\n{tf_result.stderr}"
    except Exception as e:
        return f"Error destroying cluster: {str(e)}"


def get_cluster_status(login_node_name: str, zone: str) -> str:
    """Checks the status of the Slurm cluster nodes using sinfo.
    
    Args:
        login_node_name: The GCP instance name of the Slurm login node.
        zone: The GCP zone where the login node resides.
        
    Returns:
        A string containing the sinfo output.
    """
    try:
        cmd = ["gcloud", "compute", "ssh", login_node_name, "--zone", zone, "--command", "sinfo"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return f"Cluster Status (sinfo):\n{result.stdout}"
        return f"Failed to get cluster status:\n{result.stderr}"
    except Exception as e:
        return f"Error connecting to cluster: {str(e)}"


def submit_slurm_job(login_node_name: str, zone: str, job_script_path: str) -> str:
    """Submits a job to the Slurm cluster using sbatch.
    
    Args:
        login_node_name: The GCP instance name of the Slurm login node.
        zone: The GCP zone where the login node resides.
        job_script_path: The absolute path to the batch script on the login node.
        
    Returns:
        A string containing the sbatch output (typically includes the Job ID).
    """
    try:
        cmd = ["gcloud", "compute", "ssh", login_node_name, "--zone", zone, "--command", f"sbatch {job_script_path}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return f"Job submitted successfully:\n{result.stdout}"
        return f"Failed to submit job:\n{result.stderr}"
    except Exception as e:
        return f"Error submitting job: {str(e)}"


def get_job_status(login_node_name: str, zone: str, job_id: str) -> str:
    """Gets the status of a specific Slurm job using squeue or sacct.
    
    Args:
        login_node_name: The GCP instance name of the Slurm login node.
        zone: The GCP zone where the login node resides.
        job_id: The ID of the Slurm job.
        
    Returns:
        A string containing the job status.
    """
    try:
        cmd = ["gcloud", "compute", "ssh", login_node_name, "--zone", zone, "--command", f"squeue -j {job_id} || sacct -j {job_id}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return f"Job Status:\n{result.stdout}"
        return f"Failed to retrieve job status:\n{result.stderr}"
    except Exception as e:
        return f"Error retrieving job status: {str(e)}"


def check_vm_availability(machine_type: str, zone: str, project_id: Optional[str] = None) -> str:
    """Checks if a specific machine type is available in a GCP zone using a dry-run instance creation.
    
    Args:
        machine_type: The GCP machine type (e.g., 'a2-highgpu-1g').
        zone: The GCP zone (e.g., 'us-central1-a').
        project_id: Optional GCP project ID. Defaults to current active config.
        
    Returns:
        A string indicating if the capacity is available or if there is an error/quota limit.
    """
    try:
        cmd = [
            "gcloud", "compute", "instances", "create", "capacity-check-temp",
            "--machine-type", machine_type,
            "--zone", zone,
            "--dry-run",
            "--format=json"
        ]
        if project_id:
            cmd.extend(["--project", project_id])
            
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            return f"Success: Machine type {machine_type} is available in {zone}."
        elif "QUOTA_EXCEEDED" in result.stderr:
            return f"Quota Exceeded for {machine_type} in {zone}:\n{result.stderr}"
        elif "ZONE_RESOURCE_POOL_EXHAUSTED" in result.stderr or "does not have enough resources" in result.stderr:
            return f"Stockout: Google Cloud does not currently have capacity for {machine_type} in {zone}."
        else:
            return f"Availability check returned an error:\n{result.stderr}"
    except Exception as e:
        return f"Error checking availability: {str(e)}"

def run_shell_command(command: str) -> str:
    """Executes a generic shell command (e.g. for validation scripts or reading files)."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
        return f"Error (exit code {result.returncode}):\n{result.stderr}"
    except Exception as e:
        return f"Error executing command: {str(e)}"
