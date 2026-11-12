#!/bin/bash
# ==============================================================================
# Remote 3D Molecular Visualization: VMD + XFCE Window Manager on Google Cloud
# Configures Native VMD v1.9.3, Xvfb (:1), Full XFCE4 (xfwm4), ThinLinc, noVNC
# ==============================================================================
set -e

exec > >(tee -a /var/log/vmd_workstation_setup.log /dev/ttyS0) 2>&1

echo "================================================================================"
echo "⚡ DEPLOYING VMD MOLECULAR VISUALIZATION WORKSTATION"
echo "Host: $(hostname -f) | Date: $(date)"
echo "================================================================================"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y xvfb xfce4 xfce4-goodies xfwm4 xfce4-panel xfdesktop4 \
    xfce4-session dbus-x11 xfce4-terminal libglu1-mesa libgl1-mesa-glx libgl1-mesa-dri \
    mesa-utils libxrender1 libxcursor1 libxft2 libxinerama1 libxrandr2 libxi6 libxtst6 \
    libxcomposite1 libxdamage1 libxfixes3 libxkbcommon-x11-0 libxcb-xinerama0 \
    libfontconfig1 libdbus-1-3 libxcb-cursor0 libxkbfile1 imagemagick scrot ffmpeg \
    curl wget unzip nginx novnc websockify x11vnc jq nodejs npm netcat-openbsd

# 1. Install localtunnel for fixed public subdomain access
npm install -g localtunnel || true
LT_BIN=$(which lt || echo "/usr/local/bin/lt")

# 2. Setup User and Display Services
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

cat << 'EOSERVICE' > /etc/systemd/system/x11vnc.service
[Unit]
Description=x11vnc Server on Port 5900
After=xvfb.service xfce4-session.service
Requires=xvfb.service

[Service]
Type=simple
User=root
ExecStartPre=/bin/sh -c 'while ! xdpyinfo -display :1 >/dev/null 2>&1; do sleep 1; done'
ExecStart=/usr/bin/x11vnc -display :1 -nopw -forever -shared -rfbport 5900 -listen 0.0.0.0
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EOSERVICE' > /etc/systemd/system/novnc.service
[Unit]
Description=noVNC Websockify Bridge on Port 6080
After=x11vnc.service
Requires=x11vnc.service

[Service]
Type=simple
User=root
ExecStartPre=/bin/sh -c 'while ! nc -z 127.0.0.1 5900; do sleep 1; done'
ExecStart=/usr/bin/websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EOF' > /etc/nginx/sites-available/default
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location = / {
        return 302 /vnc.html?autoconnect=true&resize=remote;
    }

    location / {
        root /usr/share/novnc;
        index vnc.html;
    }

    location /websockify {
        proxy_pass http://127.0.0.1:6080/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
    }
}
EOF

# 3. Install VMD via Micromamba
echo "[*] Installing VMD 1.9.3..."
mkdir -p /opt/vmd_installer /opt/vmd_env
cd /opt/vmd_installer
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
./bin/micromamba create -p /opt/vmd_env -c conda-forge vmd -y
ln -sf /opt/vmd_env/bin/vmd /usr/local/bin/vmd

# 4. Ingest Simulation Results
mkdir -p /home/hpcuser/vmd_demo
cd /home/hpcuser/vmd_demo
/usr/bin/gcloud storage cp gs://norne-c4d-slurm-startup-scripts-2d8c311e/md_results/* /home/hpcuser/vmd_demo/ || true
chown -R hpcuser:hpcuser /home/hpcuser/vmd_demo

# 5. Reload & Launch All Core Services
systemctl daemon-reload
systemctl enable --now xvfb.service xfce4-session.service x11vnc.service novnc.service nginx.service
sleep 3

# 6. Launch VMD in Interactive Desktop Session
echo "[*] Launching VMD with Lysozyme Simulation on Display :1..."
su - hpcuser -c "DISPLAY=:1 /usr/local/bin/vmd -size 1800 950 /home/hpcuser/vmd_demo/lysozyme_production.gro /home/hpcuser/vmd_demo/lysozyme_production.xtc -e /home/hpcuser/vmd_demo/vmd_render_scene.tcl > /tmp/vmd_gui.log 2>&1 &"

# 7. Capture Desktop Verification Screenshot
sleep 5
DISPLAY=:1 scrot -z /tmp/bulletproof_vmd_desktop.png || DISPLAY=:1 import -window root /tmp/bulletproof_vmd_desktop.png || true

# 8. Setup Tunnels
pkill lt || true
nohup ${LT_BIN} --port 80 --subdomain vmd-molecular-wyatt > /tmp/lt.log 2>&1 &
sleep 5

TUNNEL_IP=$(curl -s https://loca.lt/mytunnelpassword || curl -s ifconfig.me || echo "35.193.207.150")

cat << EOF > /tmp/workstation_live.json
{
  "permanent_fixed_url": "https://vmd-molecular-wyatt.loca.lt/vnc.html?autoconnect=true&resize=remote",
  "cloudrun_proxy_url": "https://norne-resinsight-workstation-pts6kjuzya-uc.a.run.app/vnc.html?autoconnect=true&resize=remote",
  "tunnel_password_ip": "${TUNNEL_IP}",
  "status": "ONLINE",
  "visualizer": "VMD v1.9.3",
  "simulation": "Hen Egg-White Lysozyme (1AKI) GROMACS MD",
  "timestamp": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
}
EOF

TOKEN=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" | jq -r .access_token)

curl -s -X POST --data-binary @/tmp/workstation_live.json \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://storage.googleapis.com/upload/storage/v1/b/norne-c4d-slurm-startup-scripts-2d8c311e/o?uploadType=media&name=workstation_live.json"

if [ -f /tmp/bulletproof_vmd_desktop.png ]; then
  curl -s -X POST --data-binary @/tmp/bulletproof_vmd_desktop.png \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: image/png" \
    "https://storage.googleapis.com/upload/storage/v1/b/norne-c4d-slurm-startup-scripts-2d8c311e/o?uploadType=media&name=bulletproof_vmd_desktop.png"
fi

echo "=== VMD MOLECULAR WORKSTATION DEPLOYMENT COMPLETE ==="
