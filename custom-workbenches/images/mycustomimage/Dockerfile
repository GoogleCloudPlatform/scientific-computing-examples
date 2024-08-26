FROM gcr.io/deeplearning-platform-release/workbench-container:latest

RUN ( umask 0227 && echo "jupyter ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/jupyter )

RUN apt-get -qq update \
  && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y \
    jq \
  && apt-get -qq clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip install -q flask
