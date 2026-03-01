#!/bin/bash

# This file is to setup the Thinlinc master to react to localhost request via GCP IAP tunnel setup.

# install VirtualGL
wget https://github.com/VirtualGL/virtualgl/releases/download/3.1.4/virtualgl_3.1.4_amd64.deb
sudo dpkg -i virtualgl_3.1.4_amd64.deb 

# Install Thinlinc Server
wget https://www.cendio.com/downloads/server/tl-4.20.0-server.zip
unzip -o tl-4.20.0-server.zip
sudo apt install ./tl-4.20.0-server/packages/thinlinc-server_4.20.0-4392_amd64.deb -y
echo "Generating ThinLinc setup answers file..."
OUTPUT_FILE="/tmp/ANSWER-FILE"
cat << 'EOF' > "$OUTPUT_FILE"
# ThinLinc tl-setup answers file
#
# Edit this file to suit your systems and run:
#  /opt/thinlinc/sbin/tl-setup -a THIS-FILE
# Accept the end user license agreement
accept-eula=yes
# Configure as master or agent
server-type=master
# How should old Hiveconf files be handled?
migrate-conf=ignore
# Install required libraries and binaries?
install-required-libs=yes
# Install NFS client packages?
install-nfs=no
# Install OpenSSH server?
install-sshd=no
# Install GTK+ and PyGObject packages?
install-gtk=yes
# Install python-ldap packages?
install-python-ldap=no
# How to determine externally reachable hostname
agent-hostname-choice=ip
# Externally reachable hostname (only used if manual)
#manual-agent-hostname=<hostname>
# Send administrative messages to:
email-address=thomashk@thomashk.altostrat.com
# Password for tlwebadm (generate with "/opt/thinlinc/sbin/tl-gen-auth"):
tlwebadm-password=
# Set up the thinlocal printing queue?
setup-thinlocal=no
# Set up the nearest printing queue?
setup-nearest=no
# Configure the local firewall for OpenSSH service?
setup-firewall-ssh=no
# Configure the local firewall for ThinLinc Web Access service?
setup-firewall-tlwebaccess=no
# Configure the local firewall for ThinLinc Web Administration service?
setup-firewall-tlwebadm=no
# Configure the local firewall for ThinLinc master service?
setup-firewall-tlmaster=no
# Configure the local firewall for ThinLinc agent service?
setup-firewall-tlagent=no
# Set up SELinux policy module?
setup-selinux=no
# Set up AppArmor configuration?
setup-apparmor=no
# What should tl-setup do when it encounters a question without a matching answer in the answer file?
missing-answer=abort
EOF
echo "Done! File saved as $OUTPUT_FILE"
sudo chmod 600 "$OUTPUT_FILE"
sudo /opt/thinlinc/sbin/tl-setup -a "$OUTPUT_FILE"
TARGET_HOST="localhost"
CONF_FILE="/opt/thinlinc/etc/conf.d/vsmagent.hconf"
echo "Updating $CONF_FILE to use $TARGET_HOST..."
sudo sed -i \
    -e "s/^master_hostname=.*/master_hostname=$TARGET_HOST/" \
    -e "s/^agent_hostname=.*/agent_hostname=$TARGET_HOST/" \
    "$CONF_FILE"
echo "Update complete. Current configuration:"
sudo grep -E "master_hostname=|agent_hostname=" "$CONF_FILE"
sudo systemctl restart vsmagent
