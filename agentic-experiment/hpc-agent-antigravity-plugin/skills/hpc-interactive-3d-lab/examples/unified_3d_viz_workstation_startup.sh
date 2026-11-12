#!/bin/bash
# Unified 3D Visualization Workstation Startup Script (ParaView + VMD + noVNC)
# Runs Xvfb :1 (1920x1080x24), XFCE4, x11vnc, websockify/noVNC, ParaView 5.10, and VMD 1.9.3

set -euo pipefail

export DISPLAY=:1
mkdir -p /root/.config/ParaView
cat << 'EOF' > /root/.config/ParaView/ParaView5.10.0.ini
[General]
ShowWelcomeDialog=false
AutoConvertProperties=true
EOF

pkill -f "Xvfb :1" || true
Xvfb :1 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
sleep 2

startxfce4 &
sleep 2

x11vnc -display :1 -forever -shared -nopw -rfbport 5901 -bg
websockify --web=/usr/share/novnc/ 6080 localhost:5901 &

echo "[$(date -u)] Headless 3D desktop ready on DISPLAY=:1 (noVNC port 6080)."
