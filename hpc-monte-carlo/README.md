# Monte Carlo Simulations for Value at Risk

## Before you get started
Make sure you have a project to work in.

* It must have a billing ID to support the costs of the resources used.

If you don't have a project, the instructions to create the are here:

https://cloud.google.com/resource-manager/docs/creating-managing-projects


## Basic getting started

1. Clone the repo
  > `git clone https://github.com/GoogleCloudPlatform/scientific-computing-examples.git`
1. Change to the directory: 
  > `cd scientific-computing-examples/hpc-monte-carlo`
3. Initialize Terraform
  > `terraform init`
4. Apply the terraform:
  > `terraform apply -var="project=my_project_id"  --auto-approve -var="user_email=my_email@email.com" --auto-approve`
  where `my_project_id` is the id of your project created and my_email@email.com is the email used to authenticate to Google Cloud.
5. Activate the local Python environment created by Terraform:
  > `source .fsi/bin/activate`
6. Run the Python code to start the Batch jobs
  > `python3 batch.py --config_file batch.yaml --create_job`


You can view the job `Running` in the Google Cloud Console:
  > `https://console.cloud.google.com/batch/jobs`

When the job is complete it will indicate `Succeeded`. You can then proceed to the next section.

## Visualize the output

1. Go to the Vertex AI Workbench Notebooks instances in the Google Cloud Console:
  > https://console.cloud.google.com/vertex-ai/workbench/user-managed
2. Open JupyterLab 
  > Click on `OPEN JUPYTERLAB` link
3. Clone the repository discussed in the previous steps
  > Click on the Git icon

  > Select `Clone a Repository`

  > Enter `https://github.com/GoogleCloudPlatform/scientific-computing-examples.git`

4. Navigate to the directory with the notebook
  > `scientific-copmputing -> hpc-monte-carlo`
5. Open the notebook
  > Click on `FSI_MonteCarlo.ipynb`

6. Follow the instructions in the notebook.

