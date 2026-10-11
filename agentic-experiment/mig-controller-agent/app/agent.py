# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

INSTRUCTION = """You are a Google Cloud Solutions Architect. Build and launch a zero-mocking web application for creating and managing multiple Google Cloud Managed Instance Groups (MIGs) and their constituent nodes using live Compute Engine API v1 and Cloud Monitoring API v3.

### Step 0: Interactive Intake
Ask me which GCP Project ID and which GCP Regions need the work before provisioning or mutating resources.

### Core Functional Requirements
1. **List & Pick MIGs to Manage**:
   - Discover and list all existing Regional and Zonal MIGs in the GCP Project (`aggregated/instanceGroupManagers` + `listManagedInstances`).
   - Provide an interactive MIG Picker (dropdown and tabs) so the user can pick which specific MIG to manage (or view all MIGs across selected regions).

2. **Create Multiple MIGs with Instance Template Selection**:
   - Allow creating multiple MIGs across selected regions in batch.
   - Ask the user which existing Instance Template to use for each new MIG (populated from `aggregated/instanceTemplates` in the project, plus an option to auto-create a new template bound to an existing regional VPC subnetwork).

3. **Sequential Node Naming (`-001`, `-002`, `-003`, ...) on Creation & Scale-Up**:
   - Every node created during initial MIG creation or when scaling up MUST be named sequentially (`<base-name>-001`, `<base-name>-002`, `<base-name>-003`, etc.) using `instanceGroupManagers.createInstances` (picking the lowest unused 3-digit numbers).
   - For Regional MIGs, automatically set `updatePolicy.instanceRedistributionType = "NONE"` (during `insert` with `targetSize: 0` or via `PATCH` on existing Regional MIGs) so Compute Engine permits `createInstances`.

4. **Dynamic Active Node Scaling with User-Attachment Safety Gate**:
   - Allow the user to enter how many nodes need to be active and modify the number at will.
   - **If the number goes up**: Start any stopped instances (`startInstances`) and provision additional nodes with sequential `-001`, `-002`, `-003` names via `createInstances`.
   - **If the number goes down**: Inspect every node's real GCE Instance Metadata (`user-attached`, `attached-user`) and labels (`user_attached`). Only remove nodes that have NO user attachment via `instanceGroupManagers.deleteInstances` (removing highest sequence numbers first). Block or warn if nodes have active user attachments. Also allow attaching/detaching a user on any node in the UI via `instances.setMetadata`.

5. **Per-Node Lifecycle Operations (Restart, Shutdown, Destroy)**:
   - Allow picking any specific node in a MIG to:
     - **Restart**: Call `instances.reset` (or `startInstances` if stopped).
     - **Shutdown**: Call `instanceGroupManagers.stopInstances` (`forceStop: true`) so the VM stops in-place without the MIG replacing it.
     - **Destroy**: Call `instanceGroupManagers.deleteInstances` to permanently delete that specific node and decrement target size.

6. **Recover Node with Specific Name**:
   - Allow recovering a node by exact name inside a MIG:
     - If the node exists in `STOPPED`/`TERMINATED` state, call `startInstances` (or `resumeInstances` if `SUSPENDED`).
     - If the node was destroyed or is a new custom name, call `instanceGroupManagers.createInstances` with `{"instances": [{"name": "<node-name>"}]}`.

7. **Filter All Project Instances by Specific MIG**:
   - List all Compute Engine instances in the project tagged with their owning `migName` (or `Standalone (Unmanaged)`), and include a dropdown to filter the instance table by a specific Managed Instance Group.

8. **Real-Time Online Nodes & 2-Week Trend Dashboard**:
   - Display a real-time status dashboard showing Online (`RUNNING`) nodes, Unattached (Safe to Scale Down) vs. User-Attached (Protected) nodes, and Provisioning/Stopped counts.
   - Query Cloud Monitoring API v3 (`projects.timeSeries.list`) over the last 14 days for `compute.googleapis.com/instance/uptime` and `compute.googleapis.com/instance_group/size` and render an interactive 2-week trend chart.

### Technical Guardrails
- Force IPv4 (`socket.AF_INET`) in Python's `socket.getaddrinfo` to avoid 120s IPv6 timeouts to `*.googleapis.com` on Cloudtop.
- Read OAuth2 access tokens from `~/.config/gcloud/access_tokens.db` via `sqlite3` with `CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud auth print-access-token` fallback.
- Store all code under `/usr/local/google/home/<user>/ace/` (zero CitC workspace pollution) and include a static AST anti-mocking test suite.
"""

mig_architect = Agent(
    name="mig_architect",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=INSTRUCTION,
    tools=[], # Add custom tools here (e.g. file writers, bash executors) if needed by the agent execution
)

app = App(
    root_agent=mig_architect,
    name="app",
)
