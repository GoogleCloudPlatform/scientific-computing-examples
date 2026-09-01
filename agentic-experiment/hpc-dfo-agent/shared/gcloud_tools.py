from google.adk.tools import FunctionTool
import subprocess

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
        # Prepend 'gcloud' to the arguments and add --format=json by default if suitable, 
        # but for flexibility we'll just run what's provided.
        cmd = ["gcloud"] + args
        
        # Using check=True to raise CalledProcessError on non-zero exit status
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error executing gcloud command (exit code {e.returncode}):\n{e.stderr}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

# Register the function as an ADK tool
gcloud_tool = FunctionTool(func=run_gcloud_command)