FROM gcr.io/deeplearning-platform-release/workbench-container:latest

RUN apt-get -qq update \
  && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y \
    jq \
  && apt-get -qq clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip install -q flask
