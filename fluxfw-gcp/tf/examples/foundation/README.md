# fluxfwgcp Foundation

This directory contains the Terraform configurations for the GCP [network](), [IAM](), and [storage]()
components necessary to deploy various flux-framework examples.

## Initialiation

Before you can deploy the foundation you must get the Terraform modules it requires:

```bash
make init
```

This need only be done once before your initial foundation deployment.

## Usage

Use the `make` command to deploy the foundation on the _default_ network:

```bash
make
```

To create a non-default network and use that to deploy the foundation:

```bash
make network_type=zonal
```

You can change the name of the network and/or Cloud Filestore instance deployed by the foundation by
from the command line:

```bash
make network_type=zonal network_name=my-special-network storage_name=my-own-filestore
```

or you can edit the `Makefile` and make the changes there.

To tear down the foundation use the command:

```bash
make clean
```

_Note_ if you specify alternate names on the command line you will need to supply those same names to the 
`clean` command:

```bash
make clean network_name=my-special-network storage_name=my-own-filestore
```
