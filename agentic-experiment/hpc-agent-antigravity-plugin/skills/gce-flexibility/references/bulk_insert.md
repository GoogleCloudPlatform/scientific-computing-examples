# GCE Bulk Insert Instance Flexibility (`bulkInsert`)

When deploying via the Beta GCE REST API (`instances.bulkInsert` for zonal or
`regionInstances.bulkInsert` for regional), configure the
`instanceFlexibilityPolicy` payload listing the selected instance shapes in
priority order from your earlier requirements analysis.

> [!IMPORTANT] Within `instanceSelections`, you must use the plural
> **`machineTypes`** array (e.g., `"machineTypes": ["c3-standard-8"]`)
> containing bare machine type names. Passing full or partial URLs in this field
> will result in an immediate `INTERNAL_ERROR`.

## 1. Operational Robustness & Policy Configurations

To improve operational robustness during bulk provisioning, include:

-   **`namePattern`**: Generates sequential hostnames automatically (e.g.,
    `"namePattern": "flex-vm-###"` creates `flex-vm-001`, `flex-vm-002`, etc.).
-   **`minCount`**: Sets a minimum provisioning threshold. If Compute Engine
    cannot create at least `minCount` VMs due to stock or quota limits, the
    operation cleanly rolls back rather than leaving an unusable partial
    deployment.
-   **`locationPolicy`** *(Regional only)*: Controls zone distribution across
    the region using `"targetShape": "BALANCED"` (even spread) or
    `"ANY_SINGLE_ZONE"` (single zone with most capacity).

Reference API endpoints:

-   [Zonal bulkInsert REST API](https://cloud.google.com/compute/docs/reference/rest/beta/instances/bulkInsert)
-   [Regional bulkInsert REST API](https://cloud.google.com/compute/docs/reference/rest/beta/regionInstances/bulkInsert)

--------------------------------------------------------------------------------

## 2. Example Payload (`bulkInsert` with `instanceFlexibilityPolicy`)

Ensure your boot disk configuration adheres to the **Boot Disk Selection
Rules**:

-   **Gen 3+ Instances (e.g., C3, C3D, C4, N4)**: Configure boot disk with
    `hyperdisk-balanced`.
-   **Gen 1 & Gen 2 Instances (e.g., N1, N2, N2D, C2, C2D, E2, T2D, T2A)**:
    Configure boot disk with `pd-balanced`.

```json
{
  "count": 10,
  "minCount": 8,
  "namePattern": "flex-vm-###",
  "locationPolicy": {
    "targetShape": "BALANCED"
  },
  "instanceFlexibilityPolicy": {
    "instanceSelections": {
      "gen3-preferred": {
        "machineTypes": [
          "c3-standard-8",
          "c3d-standard-8"
        ],
        "rank": 0
      },
      "gen2-fallback": {
        "machineTypes": [
          "n2-standard-8",
          "n2d-standard-8"
        ],
        "rank": 1
      }
    }
  },
  "instanceProperties": {
    "disks": [
      {
        "boot": true,
        "autoDelete": true,
        "initializeParams": {
          "sourceImage": "projects/debian-cloud/global/images/family/debian-12",
          "diskType": "hyperdisk-balanced",
          "diskSizeGb": "50"
        }
      }
    ],
    "networkInterfaces": [
      {
        "network": "projects/<PROJECT_ID>/global/networks/<VPC_NAME>",
        "subnetwork": "projects/<PROJECT_ID>/regions/<REGION>/subnetworks/<SUBNET_NAME>"
      }
    ]
  }
}
```

--------------------------------------------------------------------------------

## 3. Running the Bulk Deployer API

Submit the bulk creation request using `curl` with an authorization bearer token
from `gcloud`. Depending on whether deploying to a specific zone or across a
region, use the Beta (`beta`) zonal or regional REST API endpoint:

### Zonal Bulk Deployment (`instances.bulkInsert`)

When deploying to a specific zone, omit the `locationPolicy` field from the JSON
payload:

```bash
# Set environment variables
PROJECT_ID="<PROJECT_ID>"
ZONE="<ZONE>"

# Execute POST request to zonal bulkInsert REST API (beta)
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d @bulk_insert_request.json \
  "https://compute.googleapis.com/compute/beta/projects/${PROJECT_ID}/zones/${ZONE}/instances/bulkInsert"
```

### Regional Bulk Deployment (`regionInstances.bulkInsert`)

```bash
# Set environment variables
PROJECT_ID="<PROJECT_ID>"
REGION="<REGION>"

# Execute POST request to regional bulkInsert REST API (beta)
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d @bulk_insert_request.json \
  "https://compute.googleapis.com/compute/beta/projects/${PROJECT_ID}/regions/${REGION}/instances/bulkInsert"
```

--------------------------------------------------------------------------------

## 4. Monitoring the Operation and Inspecting Created VMs

### 4.1 Track Operation Status

Both endpoints return a long-running Compute Engine `Operation` resource. Track
operation status until `DONE` using `gcloud`:

```bash
# For zonal operations
gcloud compute operations describe <OPERATION_ID> --zone="${ZONE}" --format="json(status,progress,error)"

# For regional operations
gcloud compute operations describe <OPERATION_ID> --region="${REGION}" --format="json(status,progress,error)"
```

### 4.2 Verify Runtime Allocated Machine Types and Zones

Once the operation completes successfully, inspect which flexible machine types
and zones Compute Engine assigned to the newly provisioned VMs by querying the
instance list with a filter on your `namePattern`:

```bash
gcloud compute instances list \
  --filter="name ~ ^flex-vm-.*" \
  --format="table(name,zone,machineType,status)"
```

Sample output showing runtime machine type allocation across zones:

```
NAME         ZONE           MACHINE_TYPE   STATUS
flex-vm-001  us-central1-a  c3-standard-8  RUNNING
flex-vm-002  us-central1-b  c3d-standard-8 RUNNING
flex-vm-003  us-central1-a  n2-standard-8  RUNNING
```
