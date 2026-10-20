---
trigger: always_on
description: "Mandatory credential, project, and region initialization before running GCP or HPC commands."
---

# Mandatory Session Initialization: Credentials, Project & Region

For every new conversation when using the `hpc-agent-antigravity` plugin:

1. **Mandatory First Turn Prompt**:
   Before performing any task, invoking any tool, or running any command, you **MUST** prompt the user:
   - **GCP Credential / Account**: Which credential or Google account should be used for this session?
   - **Target GCP Project ID**: Which GCP Project ID are we working on?
   - **Target GCP Region**: Which GCP region (e.g., `us-central1`, `us-east4`, `europe-west4`) should be targeted?

2. **Strict Execution Gate**:
   - Do **NOT** run any `gcloud`, `ghpc`, `terraform`, quota check, VM availability test, or remote SSH command until the user confirms their credential, target GCP project, and target region.
   - Once provided, verify or configure the active context (e.g., `gcloud config set project <PROJECT_ID>`, `gcloud config set account <ACCOUNT>`, and `gcloud config set compute/region <REGION>`) so all subsequent commands target the desired environment.
