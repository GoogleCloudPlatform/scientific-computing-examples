# GCE Managed Instance Group Flexibility (MIGs)

When deploying Managed Instance Groups (MIGs) via the Beta GCE REST API
(`regionInstanceGroupManagers.insert` or `instanceGroupManagers.insert`),
configure the `instanceFlexibilityPolicy` payload listing the selected instance
shapes and ranks from your earlier requirements analysis.

Unlike bulk deployment, MIG instance flexibility requires grouping machine types
into named `instanceSelections`, where each selection defines an array of
`machineTypes` and an order of preference (`rank`). Note that zonal MIGs only
support instance flexibility when the target distribution shape is set to
`ANY_SINGLE_ZONE`.

Reference documentation and API endpoints:

-   [About instance flexibility](https://docs.cloud.google.com/compute/docs/instance-groups/about-instance-flexibility#instance_flexibility)
-   [Configure instance flexibility (REST API)](https://docs.cloud.google.com/compute/docs/instance-groups/configure-instance-flexibility#rest_1)
-   [View instance flexibility configuration](https://docs.cloud.google.com/compute/docs/instance-groups/view-instance-flexibility-configuration)
-   [Change or remove instance flexibility configuration](https://docs.cloud.google.com/compute/docs/instance-groups/change-or-remove-instance-flexibility-configuration)
-   [Regional MIG Insert REST API](https://docs.cloud.google.com/compute/docs/reference/rest/beta/regionInstanceGroupManagers/insert)

--------------------------------------------------------------------------------

## 1. Example Payload (`regionInstanceGroupManagers.insert` with `instanceFlexibilityPolicy`)

Ensure that the referenced `instanceTemplate` adheres to the **Boot Disk
Selection Rules** (e.g., configuring Gen 3+ instances with `hyperdisk-balanced`
and Gen 1 & Gen 2 with `pd-balanced`).

```json
{
  "name": "flex-mig-pool",
  "targetSize": 10,
  "instanceTemplate": "projects/<PROJECT_ID>/global/instanceTemplates/<INSTANCE_TEMPLATE_NAME>",
  "distributionPolicy": {
    "targetShape": "ANY"
  },
  "updatePolicy": {
    "instanceRedistributionType": "NONE"
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
  }
}
```

--------------------------------------------------------------------------------

## 2. Running the MIG Deployer API

Submit the MIG creation request using `curl` with an authorization bearer token
from `gcloud`:

### Regional MIG Deployment (`regionInstanceGroupManagers.insert`)

```bash
# Set environment variables
PROJECT_ID="<PROJECT_ID>"
REGION="<REGION>"

# Execute POST request to regional MIG insert REST API (beta)
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d @mig_insert_request.json \
  "https://compute.googleapis.com/compute/beta/projects/${PROJECT_ID}/regions/${REGION}/instanceGroupManagers"
```

### Zonal MIG Deployment (`instanceGroupManagers.insert`)

When deploying to a specific zone, set `distributionPolicy.targetShape` to
`ANY_SINGLE_ZONE` in the JSON payload:

```bash
# Set environment variables
PROJECT_ID="<PROJECT_ID>"
ZONE="<ZONE>"

# Execute POST request to zonal MIG insert REST API (beta)
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d @mig_insert_request.json \
  "https://compute.googleapis.com/compute/beta/projects/${PROJECT_ID}/zones/${ZONE}/instanceGroupManagers"
```

--------------------------------------------------------------------------------

## 3. Monitoring and Inspecting via REST API

Once the MIG is created, you can monitor the flexibility configuration, runtime
instance distribution, and modify policies via the REST API:

### 3.1 View Instance Flexibility Configuration

Retrieve the configured instance selections and ranks using the
`regionInstanceGroupManagers.get` method with field filtering:

```bash
curl -X GET \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://compute.googleapis.com/compute/beta/projects/${PROJECT_ID}/regions/${REGION}/instanceGroupManagers/<INSTANCE_GROUP_NAME>?fields=instanceFlexibilityPolicy.instanceSelections"
```

Sample response structure:

```json
{
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
  }
}
```

### 3.2 Monitor Runtime VM Machine Types and Distribution

To monitor which machine types from your flexibility policy are currently
deployed across the managed instances, make a POST request to
`listManagedInstances` and inspect the
`propertiesFromFlexibilityPolicy.machineType` field in the response:

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://compute.googleapis.com/compute/beta/projects/${PROJECT_ID}/regions/${REGION}/instanceGroupManagers/<INSTANCE_GROUP_NAME>/listManagedInstances"
```

Sample response structure indicating runtime allocations:

```json
{
  "managedInstances": [
    {
      "instanceStatus": "RUNNING",
      "name": "flex-mig-pool-xxxx",
      "propertiesFromFlexibilityPolicy": {
        "machineType": "c3-standard-8"
      }
    },
    {
      "instanceStatus": "RUNNING",
      "name": "flex-mig-pool-yyyy",
      "propertiesFromFlexibilityPolicy": {
        "machineType": "n2-standard-8"
      }
    }
  ]
}
```

### 3.3 Modifying or Removing Instance Flexibility Configuration

To update existing instance selections or change rankings after deployment, send
a `PATCH` request to `regionInstanceGroupManagers.patch` containing the updated
`instanceFlexibilityPolicy`. To remove flexibility entirely, send an empty
`instanceSelections` object:

```bash
curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{ "instanceFlexibilityPolicy": { "instanceSelections": {} } }' \
  "https://compute.googleapis.com/compute/beta/projects/${PROJECT_ID}/regions/${REGION}/instanceGroupManagers/<INSTANCE_GROUP_NAME>"
```
