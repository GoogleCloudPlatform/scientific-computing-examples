#!/bin/bash 

# Copyright 2022 Google LLC
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

dnf update -y
dnf clean all

dnf group install -y "Development Tools"

dnf config-manager --set-enabled powertools
dnf install -y epel-release

dnf install -y \
include(packages.txt)dnl

ifdef(`X86_64', `include(nvidia_downloads.txt)')dnl

useradd -M -r -s /bin/false -c "flux-framework identity" flux

cd /usr/share

git clone -b v0.44.0 https://github.com/flux-framework/flux-core.git
git clone -b v0.25.0 https://github.com/flux-framework/flux-sched.git
git clone -b v0.8.0 https://github.com/flux-framework/flux-security.git

cd /usr/share/flux-security

./autogen.sh
./configure --prefix=/usr/local

make
make install

cd /usr/share/flux-core

./autogen.sh

PKG_CONFIG_PATH=$(pkg-config --variable pc_path pkg-config)
PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH
PKG_CONFIG_PATH=${PKG_CONFIG_PATH} ./configure --prefix=/usr/local --with-flux-security

make -j 8
make install

cd /usr/share/flux-sched

./autogen.sh
./configure --prefix=/usr/local

make
make install

chmod u+s /usr/local/libexec/flux/flux-imp

cp /usr/share/flux-core/etc/flux.service /usr/lib/systemd/system

echo "FLUXMANAGER:/usr/local/etc/flux/imp /usr/local/etc/flux/imp nfs defaults,hard,intr,_netdev 0 0" >> /etc/fstab
echo "FLUXMANAGER:/usr/local/etc/flux/security /usr/local/etc/flux/security nfs defaults,hard,intr,_netdev 0 0" >> /etc/fstab
echo "FLUXMANAGER:/usr/local/etc/flux/system /usr/local/etc/flux/system nfs defaults,hard,intr,_netdev 0 0" >> /etc/fstab
echo "FLUXMANAGER:/etc/munge /etc/munge nfs defaults,hard,intr,_netdev 0 0" >> /etc/fstab

mkdir -p /etc/flux/compute/conf.d

cat << "CONFIG_FLUX_NFS" > /etc/flux/compute/conf.d/01-flux-nfs.sh
#!/bin/bash

fluxmgr=$(curl "http://metadata.google.internal/computeMetadata/v1/instance/attributes/flux-manager" -H "Metadata-Flavor: Google")

if [[ "X${fluxmgr}" != "X" ]]; then
    sed -i s/FLUXMANAGER/$(ping -c 1 ${fluxmgr} | egrep -i ^ping | cut -d' ' -f 2)/g /etc/fstab
    mount -a
fi
CONFIG_FLUX_NFS

cat << "CONFIG_HOME_NFS" > /etc/flux/compute/conf.d/02-home-nfs.sh
#!/bin/bash

nfsmounts=$(curl "http://metadata.google.internal/computeMetadata/v1/instance/attributes/nfs-mounts" -H "Metadata-Flavor: Google")

if [[ "X${nfsmounts}" != "X" ]]; then
    bash -c "sudo echo $(echo $nfsmounts | jq -r '.share') $(echo $nfsmounts | jq -r '.mountpoint') nfs defaults,hard,intr,_netdev 0 0 >> /etc/fstab"
    mount -a
fi
CONFIG_HOME_NFS

ifdef(`X86_64', `include(config_gpus.txt)')dnl

cat << "CONFIG_HOSTBASED_AUTH" > /etc/flux/compute/conf.d/04-hostbased-auth.sh
#!/bin/bash

cd /etc/ssh

login_node_specs=$(curl "http://metadata.google.internal/computeMetadata/v1/instance/attributes/login-node-specs" -H "Metadata-Flavor: Google")

for s in $(echo $login_node_specs | jq -c '.[]')
do 
    np=$(echo $s | jq -r '.name_prefix')
    for i in $(seq $(echo $s | jq -r '.instances'))
    do 
        nm=$(printf "%s-%03d\n" $np $i)

        while [[ -z "$(ping $nm -c1 2>&1 | grep 'packets transmitted')" ]]; do sleep 2; done

        ip=$(ping -c1 $nm | grep -i ^ping | cut -d' ' -f3 | tr -d '()')
        
        while [[ -z "$(ssh-keyscan -T 60 -t rsa $ip 2> /dev/null)" ]]; do sleep 2; done

        ssh-keyscan -t rsa $ip >> ssh_known_hosts
        echo $ip >> shosts.equiv
    done
done

fluxmgr=$(curl "http://metadata.google.internal/computeMetadata/v1/instance/attributes/flux-manager" -H "Metadata-Flavor: Google")

while [[ -z "$(ping $fluxmgr -c1 2>&1 | grep 'packets transmitted')" ]]; do sleep 2; done

ip=$(ping -c1 $fluxmgr | grep -i ^ping | cut -d' ' -f3 | tr -d '()')

while [[ -z "$(ssh-keyscan -T 60 -t rsa $ip 2> /dev/null)" ]]; do sleep 2; done

ssh-keyscan -t rsa $ip >> ssh_known_hosts
echo $ip >> shosts.equiv

sed -i 's/#HostbasedAuthentication no/HostbasedAuthentication yes/g' /etc/ssh/sshd_config
sed -i 's/#IgnoreRhosts yes/IgnoreRhosts no/g' /etc/ssh/sshd_config

systemctl restart sshd
CONFIG_HOSTBASED_AUTH

cat << "RUN_BOOT_SCRIPT" > /etc/flux/compute/conf.d/99-boot-script.sh
#!/bin/bash

curl -f "http://metadata.google.internal/computeMetadata/v1/instance/attributes/boot-script" -H "Metadata-Flavor: Google" --output /var/tmp/boot-script.sh
if [ "$?" == "0" ]; then
    . /var/tmp/boot-script.sh
fi

RUN_BOOT_SCRIPT

cat << "COMPUTE_FIRST_BOOT" > /etc/flux/compute/first-boot.sh
#!/bin/bash

for cs in $(ls /etc/flux/compute/conf.d/*.sh | sort -n); do . $cs; done

systemctl enable --now flux
COMPUTE_FIRST_BOOT
chmod u+x,go-rwx /etc/flux/compute/first-boot.sh

cat << "FIRST_BOOT_UNIT" > /etc/systemd/system/flux-config-compute.service
[Unit]
Wants=systemd-hostnamed
After=systemd-hostnamed
Wants=network-online.target
After=network-online.target
ConditionPathExists=!/var/lib/flux-compute-configured

[Service]
Type=oneshot
ExecStartPre=/bin/bash -c 'while [[ "$(hostname)" =~ "packer" ]]; do sleep 1; done'
ExecStart=/etc/flux/compute/first-boot.sh
ExecStartPost=/usr/bin/touch /var/lib/flux-compute-configured
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
FIRST_BOOT_UNIT

systemctl enable flux-config-compute.service
