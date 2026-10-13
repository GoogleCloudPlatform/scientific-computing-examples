#!/usr/bin/env bash
# Provision a Browser-Accessible ParaView + XFCE4 + noVNC Remote Visualization Node
# Usage: sudo bash paraview_remote_viz_setup.sh [--case-dir /scratch/openfoam/motorBike]

set -euo pipefail

CASE_DIR="${1:-/scratch/openfoam/motorBike}"
VIZ_DIR="/scratch/visualizations"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts"

echo "=== 1. Installing Headless Desktop, ParaView & noVNC Stack ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  xvfb xfce4 xfce4-goodies x11vnc novnc python3-websockify \
  paraview paraview-python xdotool imagemagick

echo "=== 2. Configuring ParaView INI (Disabling Modal Welcome Dialog) ==="
mkdir -p /root/.config/ParaView/Macros "$VIZ_DIR"
cat << 'EOF' > /root/.config/ParaView/ParaView5.10.0.ini
[General]
GeneralSettings.ShowWelcomeDialog=false
EOF

echo "=== 3. Generating Pre-Baked VTK Scripts & 4 Animated CFD Macros ==="
if [[ -f "${SCRIPT_DIR}/paraview_cae_visualizer.py" ]]; then
  python3 "${SCRIPT_DIR}/paraview_cae_visualizer.py" \
    --case-dir "$CASE_DIR" \
    --output-dir "$VIZ_DIR" \
    --macros-dir /root/.config/ParaView/Macros \
    --config-dir /root/.config/ParaView
fi

echo "=== 4. Starting 1920x1080 Virtual X11 Display (:1), XFCE4, x11vnc & noVNC ==="
pkill -9 -x Xvfb 2>/dev/null || true
Xvfb :1 -screen 0 1920x1080x24 +iglx > /var/log/xvfb.log 2>&1 &
sleep 2

DISPLAY=:1 startxfce4 > /var/log/xfce4.log 2>&1 &
sleep 3

x11vnc -display :1 -forever -shared -nopw -rfbport 5901 > /var/log/x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc/ 6080 localhost:5901 > /var/log/novnc.log 2>&1 &

echo "=== 5. Pre-Baking Fast Binary VTK Caches (if OpenFOAM case exists) ==="
if [[ -f "${CASE_DIR}/motorBike.foam" && -f "${VIZ_DIR}/prebake_fast_vtk.py" ]]; then
  DISPLAY=:1 PYTHONPATH=/usr/lib/python3/dist-packages pvpython "${VIZ_DIR}/prebake_fast_vtk.py"
fi

echo "=== 6. Launching ParaView on Display :1 ==="
DISPLAY=:1 paraview > /var/log/paraview.log 2>&1 &
sleep 5
# Trigger Macro 1 (3D Velocity StreamTubes) via top menu bar
DISPLAY=:1 xdotool mousemove 252 60 click 1
sleep 1
DISPLAY=:1 xdotool mousemove 270 195 click 1

echo "=== ParaView Remote Visualization Ready on Port 6080 (/vnc.html?autoconnect=true&resize=remote) ==="
