#!/bin/bash
# ==============================================================================
# Remote 3D Reservoir Visualization: ResInsight + XFCE Window Manager on Google Cloud
# Configures Native ResInsight v2026.09.1, Xvfb (:1), Full XFCE4 (xfwm4), ThinLinc, noVNC
# ==============================================================================
set -e

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y xvfb xfce4 xfce4-goodies xfwm4 xfce4-panel xfdesktop4 \
    xfce4-session dbus-x11 xfce4-terminal libglu1-mesa libgl1-mesa-glx libgl1-mesa-dri \
    mesa-utils libxrender1 libxcursor1 libxft2 libxinerama1 libxrandr2 libxi6 libxtst6 \
    libxcomposite1 libxdamage1 libxfixes3 libxkbcommon-x11-0 libxcb-xinerama0 \
    libfontconfig1 libdbus-1-3 libxcb-cursor0 libxkbfile1 imagemagick scrot \
    curl wget unzip nginx novnc websockify x11vnc jq nfs-common

# 1. Create Virtual Display and XFCE Session with Window Manager (xfwm4)
useradd -m -s /bin/bash -G sudo,adm hpcuser || true
echo "hpcuser:GoogleHPC2026!" | chpasswd

cat << 'EOSERVICE' > /etc/systemd/system/xvfb.service
[Unit]
Description=X Virtual Framebuffer Display :1 (1920x1080x24)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/Xvfb :1 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EOSERVICE' > /etc/systemd/system/xfce4-session.service
[Unit]
Description=XFCE4 Desktop Session and xfwm4 Window Manager on Display :1
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
User=hpcuser
WorkingDirectory=/home/hpcuser
Environment=DISPLAY=:1
Environment=HOME=/home/hpcuser
Environment=USER=hpcuser
Environment=XDG_CURRENT_DESKTOP=XFCE
Environment=XDG_SESSION_TYPE=x11
ExecStart=/usr/bin/dbus-run-session -- /usr/bin/xfce4-session
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOSERVICE

systemctl daemon-reload
systemctl enable --now xvfb.service xfce4-session.service

# 2. Install ThinLinc Server (v4.21.0)
mkdir -p /tmp/thinlinc-install
cd /tmp/thinlinc-install
wget -q "https://www.cendio.com/downloads/server/tl-4.21.0-server.zip" -O tl-server.zip
unzip -q tl-server.zip
apt-get install -y ./tl-*-server/packages/thinlinc-server_*.deb
/opt/thinlinc/sbin/tl-setup -s || true
sed -i 's/^default_wm=.*/default_wm=xfce4-session/' /opt/thinlinc/etc/conf.d/vsmagent.hconf || true
systemctl enable --now vsmagent vsmserver tlwebaccess

# 3. Install Native Ceetron/OPM ResInsight
mkdir -p /opt/resinsight /tmp/resinsight-install
cd /tmp/resinsight-install
wget -q "https://github.com/OPM/ResInsight/releases/download/v2026.09.1/ResInsight-Ubuntu_24.04_gcc-v2026.09.1.zip" -O resinsight.zip
unzip -q resinsight.zip -d /opt/resinsight/
REAL_BIN=$(find /opt/resinsight -type f -name "ResInsight" | head -n 1)
chmod +x "$REAL_BIN"
ln -sf "$REAL_BIN" /usr/local/bin/resinsight

# 4. Launch ResInsight inside the XFCE Window Manager Frame
# DISPLAY=:1 resinsight --size 1800 950 --case /path/to/case.EGRID
