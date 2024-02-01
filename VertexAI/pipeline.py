import os
import sys
import google.cloud.aiplatform as aip
from datetime import datetime

TIMESTAMP = datetime.now().strftime("%Y%m%d%H%M%S")
BUCKET_URI = "gs://[your-bucket-name]"  # @param {type:"string"}
REGION = "us-central1"
MACHINE_TYPE = "n1-standard"


aip.init(project=PROJECT_ID, staging_bucket=BUCKET_URI)

! gsutil mb -l $REGION $BUCKET_URI

if os.getenv("IS_TESTING_TRAIN_GPU"):
    TRAIN_GPU, TRAIN_NGPU = (
        aip.gapic.AcceleratorType.NVIDIA_TESLA_K80,
        int(os.getenv("IS_TESTING_TRAIN_GPU")),
    )
else:
    TRAIN_GPU, TRAIN_NGPU = (None, None)

if os.getenv("IS_TESTING_DEPLOY_GPU"):
    DEPLOY_GPU, DEPLOY_NGPU = (
        aip.gapic.AcceleratorType.NVIDIA_TESLA_K80,
        int(os.getenv("IS_TESTING_DEPLOY_GPU")),
    )
else:
    DEPLOY_GPU, DEPLOY_NGPU = (None, None)

TRAIN_VERSION = "scikit-learn-cpu.0-23"
DEPLOY_VERSION = "sklearn-cpu.0-23"

TRAIN_IMAGE = "{}-docker.pkg.dev/vertex-ai/training/{}:latest".format(
    REGION.split("-")[0], TRAIN_VERSION
)
DEPLOY_IMAGE = "{}-docker.pkg.dev/vertex-ai/prediction/{}:latest".format(
    REGION.split("-")[0], DEPLOY_VERSION
)

