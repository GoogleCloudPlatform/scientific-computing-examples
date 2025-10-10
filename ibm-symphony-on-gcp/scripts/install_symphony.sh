#!/bin/bash

# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
set -o pipefail
set -x

export sym_installer=$1
export sym_fixpack=$2
export sym_entitlement=$3
export symphony_install_dir=$4
export sym_source_bucket=$5

##### Update some packages

yum install -y \
  bc \
  gettext \
  bind-utils \
  net-tools \
  libnsl \
  openssl \
  ed \
  dejavu-serif-fonts \
  findutils \
  sudo \
  vim \
  zip \
  diffutils \
  iproute \
  procps \
  jq \
  glibc-locale-source \
  glibc-langpack-en \
  && yum clean all && rm -rf /var/cache/yum

# Add egoadmin user & configure

useradd -G wheel -m egoadmin && echo egoadmin:Admin | chpasswd && echo "egoadmin ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers.d/symphony-cluster-admins
touch /var/run/utmp && chmod 664 /var/run/utmp && chown root:utmp /var/run/utmp
echo LC_ALL=en_US.UTF-8 > /etc/locale.conf && \
  LC_ALL=en_US.UTF-8 localedef -v -c -i en_US -f UTF-8 en_US.UTF-8 | true
echo "egoadmin soft nproc  65536" >> /etc/security/limits.conf && \
echo "egoadmin hard nproc  65536" >> /etc/security/limits.conf && \
echo "egoadmin soft nofile 65536" >> /etc/security/limits.conf && \
echo "egoadmin hard nofile 65536" >> /etc/security/limits.conf
 
# Get installers, etc

/usr/bin/gsutil cp gs://${sym_source_bucket}/${sym_installer} /tmp
/usr/bin/gsutil cp gs://${sym_source_bucket}/${sym_entitlement} /tmp
/usr/bin/gsutil cp gs://${sym_source_bucket}/${sym_fixpack} /tmp

##### Run installer

cd /tmp
mkdir -p ${symphony_install_dir}
export ENV EGO_TOP=${symphony_install_dir} CLUSTERADMIN=egoadmin IBM_SPECTRUM_SYMPHONY_LICENSE_ACCEPT=Y SIMPLIFIEDWEM=N DISABLESSL=Y
mv /tmp/${sym_entitlement} ${EGO_TOP}
chmod a+x ${sym_installer}
./${sym_installer} --prefix ${EGO_TOP} --quiet 

##### Install fixpack

export SYM_FIXPACK_TAR=${sym_fixpack}
export SYM_FIXPACK_PATH=/tmp/${SYM_FIXPACK_TAR}
export SYM_FIXPACK_NAME=`basename $SYM_FIXPACK_TAR .tar.gz`
export SYM_FIXPACK_DIR=/opt/ibm/${SYM_FIXPACK_NAME}

mkdir -p ${SYM_FIXPACK_DIR}
chmod 770 ${SYM_FIXPACK_DIR}
tar -xf ${SYM_FIXPACK_PATH} -C ${SYM_FIXPACK_DIR}
chmod u+r ${SYM_FIXPACK_DIR}/*
chmod a+x ${SYM_FIXPACK_DIR}/*.sh

cd ${SYM_FIXPACK_DIR}

su -s /bin/bash $CLUSTERADMIN -c "source $EGO_TOP/profile.platform && ${SYM_FIXPACK_DIR}/sym-7.3.2.sh -c -i"

source $EGO_TOP/profile.platform
${SYM_FIXPACK_DIR}/symrpm-7.3.2.sh -c -i

cd 

rm -rf $EGO_TOP/patch/backup/*
rm -rf ${SYM_FIXPACK_DIR}
rm -f ${SYM_FIXPACK_PATH}

##### Update configuration

cd ${EGO_TOP}

sed -i "s|BINARY_TYPE=\"fail\"|BINARY_TYPE=\"linux-x86_64\"|g" kernel/conf/profile.ego && \
  sed -i "s|BINARY_TYPE=\"fail\"|BINARY_TYPE=\"linux-x86_64\"|g" jre/profile.jre && \
  sed -i "s|BINARY_TYPE=\"fail\"|BINARY_TYPE=\"linux-x86_64\"|g" soam/conf/profile.soam && \
  sed -i -e "s|AUTOMATIC|MANUAL|g" eservice/esc/conf/services/plc_service.xml && \
  sed -i -e "s|AUTOMATIC|MANUAL|g" eservice/esc/conf/services/purger_service.xml && \
  sed -i -e "s|AUTOMATIC|MANUAL|g" eservice/esc/conf/services/wsg.xml && \
  sed -i -e "s|AUTOMATIC|MANUAL|g" eservice/esc/conf/services/rsa.xml && \
  sed -i -e "s|MANUAL|AUTOMATIC|g" eservice/esc/conf/services/symrest.xml

  echo "EGO_DYNAMIC_HOST_TIMEOUT=10m" >> kernel/conf/ego.conf && \
    echo "EGO_DYNAMIC_HOST_WAIT_TIME=1" >> kernel/conf/ego.conf && \
    #echo "EGO_RESOURCE_UPDATE_INTERVAL=1" >> kernel/conf/ego.conf && \
    #echo "EGO_ENABLE_RG_UPDATE_MEMBERSHIP=Y" >> kernel/conf/ego.conf && \
    #echo "EGO_RG_UPDATE_MEMBERSHIP_INTERVAL=10" >> kernel/conf/ego.conf && \
    echo "EGO_DISABLE_ROOT_REX=Y" >> kernel/conf/ego.conf && \
    echo "EGO_ELIM_RUNAS_CLUSTER_ADMIN=Y" >> kernel/conf/ego.conf && \
    echo "EGO_LIM_IS_IN_CONTAINER=Y" >> kernel/conf/ego.conf && \
    echo "EGO_GET_CONF=LIM" >> kernel/conf/ego.conf