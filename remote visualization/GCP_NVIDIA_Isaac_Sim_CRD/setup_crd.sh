#!/bin/bash

# This file is used to install the CRD for Isaac Sim Workstation

 sudo apt update && sudo apt install -y \
    build-essential \
    gdebi-core \
    mesa-utils \
    gdm3 \
    gcc-12 \
    pkg-config \
    libglvnd-dev \
    linux-headers-$(uname -r)

# Download the .deb package
wget -O /tmp/virtualgl-3.1.4.amd64.deb https://github.com/VirtualGL/virtualgl/releases/download/3.1.4/virtualgl_3.1.4_amd64.deb

# install .deb package
sudo gdebi --n /tmp/virtualgl-3.1.4.amd64.deb

# Extract the PCI BusID automatically
PCI_ID=$(nvidia-xconfig --query-gpu-info | grep "PCI BusID " | head -n 1 | cut -d':' -f2-99 | xargs)

# Configure nvidia-xconfig with that BusID
sudo nvidia-xconfig -a --allow-empty-initial-configuration --enable-all-gpus --virtual=1920x1200 --busid=$PCI_ID

# Disable HardDPMS in /etc/X11/xorg.conf
sudo sed -i '/Section "Device"/a \    Option      "HardDPMS" "false"' /etc/X11/xorg.conf

# Configure VirtualGL (Grant access to X, restrict to members of vglusers, etc.)
sudo vglserver_config +glx +s +f -t

# Set gdm3 as the default display manager
echo "/usr/sbin/gdm3" | sudo tee /etc/X11/default-display-manager

# Set the system to boot into the Graphical User Interface (GUI)
sudo systemctl set-default graphical.target

# Reload systemd and start GDM
sudo systemctl daemon-reload
sudo systemctl start gdm

#Install Chrome Remote Desktop: 
sudo apt-get update
sudo apt-get install -y xvfb
wget https://dl.google.com/linux/direct/chrome-remote-desktop_current_amd64.deb
sudo dpkg -i chrome-remote-desktop_current_amd64.deb
sudo apt --fix-broken install -y
sudo apt-get install -y xfce4 xfce4-goodies
