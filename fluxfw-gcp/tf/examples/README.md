# fluxfw-gcp Examples

This directory contains a collection of examples of deploying and using the flux-framework on GCP.
Each of the examples deploy on a _foundation_ of network, iam, and storage components defined in the
[foundation]() directory.

## Usage

Before you deploy an example the foundation they depend on must be deployed. The documentation in 
the [foundation README]() describes how to deploy the foundation.

For the impatient the simplest foundation deployment is realized with the command:

```bash
cd foundation
make
```

Once the foundation is deployed you can visit any of the example directories and follow the steps
in the their README documentation to deploy the example.

_Note_ the foundation only needs to be deployed once. Any of the examples, or a collection of them,
can be deployed simultaneously on the foundation.
