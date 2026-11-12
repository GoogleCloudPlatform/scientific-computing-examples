#!/bin/bash
# ==============================================================================
# Google Cloud HPC: 3D Energy Simulation Remote Visualization Node Startup Script
# Configures: ParaView GUI + ThinLinc Server + noVNC Web Desktop + Cloudflare Tunnels
# Symmetrically displays Seismic Exploration (Marmousi 2) & Reservoir Simulation (SPE 10)
# ==============================================================================
set -x
exec > >(tee -a /var/log/startup-energy-viz.log /dev/ttyS0) 2>&1

echo "=== STARTING ENERGY PARAVIEW VIZ SETUP ==="
date

# 1. Update OS and install base GUI & scientific packages
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y xvfb xfce4 xfce4-terminal paraview python3-paraview python3-pip \
    python3-numpy python3-scipy python3-matplotlib curl wget unzip nginx novnc websockify x11vnc jq openssl

systemctl stop paraview-gui cloudflared-thinlinc cloudflared-novnc || true

# 2. Configure ThinLinc Remote Desktop Server (v4.21.0)
echo "=== CONFIGURING THINLINC SERVER ==="
if [ ! -d /opt/thinlinc ]; then
    mkdir -p /tmp/thinlinc-install
    cd /tmp/thinlinc-install
    wget -q "https://www.cendio.com/downloads/server/tl-4.21.0-server.zip" -O tl-server.zip
    unzip -q tl-server.zip
    apt-get install -y ./tl-*-server/packages/thinlinc-server_*.deb
fi

# Generate SSL certificate for ThinLinc Web Access (Port 300)
mkdir -p /opt/thinlinc/etc/tlwebaccess /opt/thinlinc/etc/certs
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /opt/thinlinc/etc/tlwebaccess/server.key \
  -out /opt/thinlinc/etc/tlwebaccess/server.crt \
  -subj "/CN=energy-paraview-viz/O=GoogleHPC"
chmod 600 /opt/thinlinc/etc/tlwebaccess/server.key
chmod 644 /opt/thinlinc/etc/tlwebaccess/server.crt

# Complete ThinLinc configuration guards
sed -i 's/^setup_completed=.*/setup_completed=4.21.0/' /opt/thinlinc/etc/conf.d/vsm.hconf || true
sed -i 's/^default_wm=.*/default_wm=xfce4-session/' /opt/thinlinc/etc/conf.d/vsmagent.hconf || true
/opt/thinlinc/bin/tlctl conf set /vsm/setup_completed "4.21.0" || true

useradd -m -s /bin/bash -G sudo,adm hpcuser || true
echo "hpcuser:GoogleHPC2026!" | chpasswd
echo "root:GoogleHPC2026!" | chpasswd

systemctl daemon-reload
systemctl enable vsmagent vsmserver tlwebaccess
systemctl restart vsmagent vsmserver tlwebaccess || true

# 3. Create Energy HPC Data & Legacy VTK Export Pipeline
rm -rf /apps/energy/vtk/* /apps/energy/paraview/*
mkdir -p /apps/energy/{scripts,data,vtk,paraview,results} /scratch/visualizations /home/hpcuser/Desktop /root/Desktop
chmod -R 777 /apps /scratch

# Deploy the Python visualization and pipeline generator
cat << 'EOF_PV_PIPELINE' > /apps/energy/scripts/paraview_energy_pipeline.py
import os
import glob
import numpy as np
from scipy.ndimage import gaussian_filter

def write_vtk_structured_points(filename, array_2d, dx, dy, dz, scalar_name):
    nz, nx = array_2d.shape
    with open(filename, "w") as f:
        f.write("# vtk DataFile Version 3.0\n")
        f.write(f"{scalar_name} Data\n")
        f.write("ASCII\n")
        f.write("DATASET STRUCTURED_POINTS\n")
        f.write(f"DIMENSIONS {nx} 1 {nz}\n")
        f.write("ORIGIN 0 0 0\n")
        f.write(f"SPACING {dx} {dy} {dz}\n")
        f.write(f"POINT_DATA {nx * nz}\n")
        f.write(f"SCALARS {scalar_name} float 1\n")
        f.write("LOOKUP_TABLE default\n")
        flat = array_2d.astype(np.float32).flatten()
        for i in range(0, len(flat), 8):
            f.write(" ".join(f"{val:.2f}" for val in flat[i:i+8]) + "\n")
    print(f"[+] Written Legacy VTK: {filename} ({nx}x{nz})")

# Generate 4000m x 2500m Seismic Exploration Datasets
nx_s, nz_s = 401, 201
dx_s, dz_s = 10.0, 12.5
x_s = np.linspace(0, 4000.0, nx_s)
z_s = np.linspace(0, 2500.0, nz_s)
X_s, Z_s = np.meshgrid(x_s, z_s)

v = 1500.0 + 0.8 * Z_s
v[Z_s < 300.0] = 1500.0
fold = 80.0 * np.sin(2.0 * np.pi * X_s / 1500.0) * np.exp(-((Z_s - 800.0) / 400.0)**2)
v[(Z_s + fold > 500.0) & (Z_s + fold <= 900.0)] = 2200.0 + 0.3 * (Z_s[(Z_s + fold > 500.0) & (Z_s + fold <= 900.0)] - 500.0)
v[(Z_s + fold > 900.0) & (Z_s + fold <= 1400.0)] = 2800.0 + 0.4 * (Z_s[(Z_s + fold > 900.0) & (Z_s + fold <= 1400.0)] - 900.0)
v[(Z_s + fold > 1400.0)] = 3300.0 + 0.2 * (Z_s[(Z_s + fold > 1400.0)] - 1400.0)
v[((X_s - 2000.0)**2 / (600.0**2) + (Z_s - 1300.0)**2 / (350.0**2)) <= 1.0] = 4500.0
v[((X_s - 1200.0)**2 / (250.0**2) + (Z_s - 1100.0)**2 / (120.0**2)) <= 1.0] = 1750.0
v[(X_s > (0.5 * Z_s + 600.0)) & (Z_s > 600.0)] *= 1.08
v[Z_s < 300.0] = 1500.0
write_vtk_structured_points("/apps/energy/vtk/marmousi_velocity.vtk", v, dx=dx_s, dy=10.0, dz=dz_s, scalar_name="Velocity")

time_steps = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]
sx, sz = 2000.0, 350.0
for idx, ts in enumerate(time_steps):
    r = np.sqrt((X_s - sx)**2 + (Z_s - sz)**2)
    r_target = 2200.0 * ts
    pulse = np.exp(-((r - r_target) / 120.0)**2) * np.sin(2.0 * np.pi * 15.0 * (r - r_target) / 2200.0)
    salt_dist = np.sqrt((X_s - 2000.0)**2 + (Z_s - 1300.0)**2)
    if ts >= 0.45:
        salt_refl = 0.5 * np.exp(-((salt_dist - (2200.0 * (ts - 0.45))) / 90.0)**2)
        pulse += salt_refl
    write_vtk_structured_points(f"/apps/energy/vtk/seismic_wavefield_{idx:02d}.vtk", pulse, dx=dx_s, dy=10.0, dz=dz_s, scalar_name="Acoustic_Pressure")

# Generate 4000m x 2500m Reservoir Simulation Datasets
nx_r, nz_r = 81, 51
dx_r, dz_r = 50.0, 50.0
x_r = np.linspace(0, 4000.0, nx_r)
z_r = np.linspace(0, 2500.0, nz_r)
X_r, Z_r = np.meshgrid(x_r, z_r)

np.random.seed(42)
noise = np.random.randn(nz_r, nx_r)
ch = gaussian_filter(noise, sigma=[3.0, 10.0])
ch = (ch - ch.min()) / (ch.max() - ch.min())
perm = 10.0 ** (1.0 + 3.5 * ch + 0.3 * np.random.randn(nz_r, nx_r))
write_vtk_structured_points("/apps/energy/vtk/reservoir_perm.vtk", perm, dx=dx_r, dy=10.0, dz=dz_r, scalar_name="Permeability_mD")

res_days = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
inj_x, inj_z = 400.0, 2100.0
prod_x, prod_z = 3600.0, 400.0

for idx, day in enumerate(res_days):
    progress = day / 1000.0
    dist_inj = np.sqrt((X_r - inj_x)**2 + (Z_r - inj_z)**2)
    sw = 0.20 + 0.60 * np.clip(1.2 * progress * (ch ** 0.5) - 0.0003 * dist_inj, 0.0, 1.0)
    sw = np.maximum(sw, 0.78 * np.exp(-(dist_inj / (1200.0 * (progress + 0.1)))**2))
    sw = np.clip(sw, 0.20, 0.80)
    write_vtk_structured_points(f"/apps/energy/vtk/reservoir_saturation_{idx:02d}.vtk", sw, dx=dx_r, dy=10.0, dz=dz_r, scalar_name="Water_Saturation")
EOF_PV_PIPELINE

python3 /apps/energy/scripts/paraview_energy_pipeline.py

# 4. Start Xvfb & XFCE4 Virtual Desktop Stack
cat << 'EOSERVICE' > /etc/systemd/system/xvfb.service
[Unit]
Description=X Virtual Framebuffer Service (Display :1)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/Xvfb :1 -screen 0 1920x1080x24
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EOSERVICE' > /etc/systemd/system/xfce4-session.service
[Unit]
Description=XFCE4 Desktop Session on Display :1
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
User=hpcuser
Environment=DISPLAY=:1
Environment=HOME=/home/hpcuser
Environment=XDG_CURRENT_DESKTOP=XFCE
Environment=XDG_SESSION_TYPE=x11
ExecStartPre=/bin/sleep 1
ExecStart=/usr/bin/xfce4-session
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EOSERVICE' > /etc/systemd/system/x11vnc.service
[Unit]
Description=x11vnc Server (Display :1 on Port 5900)
After=xfce4-session.service
Requires=xfce4-session.service

[Service]
Type=simple
User=root
ExecStartPre=/bin/sleep 1
ExecStart=/usr/bin/x11vnc -display :1 -nopw -forever -shared -rfbport 5900 -listen 0.0.0.0
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EOSERVICE' > /etc/systemd/system/novnc.service
[Unit]
Description=noVNC Websockify Bridge (Port 6080)
After=x11vnc.service
Requires=x11vnc.service

[Service]
Type=simple
User=root
ExecStartPre=/bin/sleep 1
ExecStart=/usr/bin/websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EONGINX' > /etc/nginx/sites-available/default
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {
        root /usr/share/novnc;
        index vnc.html;
    }

    location /scratch/ {
        alias /scratch/;
        autoindex on;
    }

    location /websockify {
        proxy_pass http://127.0.0.1:6080/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_buffering off;
    }
}
EONGINX

if [ -f /usr/share/novnc/vnc.html ]; then
    cp /usr/share/novnc/vnc.html /usr/share/novnc/index.html
fi

systemctl daemon-reload
systemctl enable xvfb xfce4-session x11vnc novnc nginx
systemctl restart xvfb
sleep 2
systemctl restart xfce4-session
sleep 2
systemctl restart x11vnc novnc nginx

# 5. Build ParaView Equal-Scale Scene Script with Unoccluded Animation Layers
cat << 'EOF_PV_SCRIPT' > /apps/energy/paraview/setup_paraview_animation.py
import os
import glob
from paraview.simple import *

paraview.simple._DisableFirstRenderCameraReset()
view = GetActiveViewOrCreate('RenderView')
view.ViewSize = [1920, 1080]
view.Background = [0.06, 0.09, 0.16]
view.OrientationAxesVisibility = 1

# Left Domain: Marmousi 2 Velocity at Y=0 (35% opacity), Wavefield at Y=-40 (95% opacity)
vti_vel = '/apps/energy/vtk/marmousi_velocity.vtk'
if os.path.exists(vti_vel):
    vel = LegacyVTKReader(registrationName='Marmousi_Velocity_Model', FileNames=[vti_vel])
    vel_disp = Show(vel, view)
    vel_disp.SetRepresentationType('Surface')
    ColorBy(vel_disp, ('POINTS', 'Velocity'))
    lut_vel = GetColorTransferFunction('Velocity')
    lut_vel.ApplyPreset('Turbo', True)
    vel_disp.Opacity = 0.35
    bar_vel = GetScalarBar(lut_vel, view)
    bar_vel.Title = 'Seismic Velocity (m/s)'
    bar_vel.Position = [0.03, 0.05]
    bar_vel.ScalarBarLength = 0.38

wave_files = [f'/apps/energy/vtk/seismic_wavefield_{i:02d}.vtk' for i in range(10)]
wave = LegacyVTKReader(registrationName='Seismic_Wavefield_Animation', FileNames=wave_files)
wave_t = Transform(registrationName='Wavefield_Foreground', Input=wave)
wave_t.Transform.Translate = [0.0, -40.0, 0.0]
wave_disp = Show(wave_t, view)
wave_disp.SetRepresentationType('Surface')
ColorBy(wave_disp, ('POINTS', 'Acoustic_Pressure'))
lut_wave = GetColorTransferFunction('Acoustic_Pressure')
lut_wave.ApplyPreset('Cool to Warm', True)
lut_wave.RescaleTransferFunction(-1.5, 1.5)
wave_disp.Opacity = 0.95
bar_wave = GetScalarBar(lut_wave, view)
bar_wave.Title = 'Acoustic Pressure (Pa)'
bar_wave.Position = [0.03, 0.52]
bar_wave.ScalarBarLength = 0.38

source = Sphere(registrationName='Seismic_Shot_Source')
source.Center = [2000.0, -40.0, 350.0]
source.Radius = 90.0
source_disp = Show(source, view)
source_disp.DiffuseColor = [1.0, 0.2, 0.2]

# Right Domain: SPE 10 Permeability at X=5000, Y=0 (35% opacity), Saturation at Y=-40 (95% opacity)
perm_file = '/apps/energy/vtk/reservoir_perm.vtk'
if os.path.exists(perm_file):
    perm = LegacyVTKReader(registrationName='SPE10_Permeability_Matrix', FileNames=[perm_file])
    perm_t = Transform(registrationName='Reservoir_Offset', Input=perm)
    perm_t.Transform.Translate = [5000.0, 0.0, 0.0]
    perm_disp = Show(perm_t, view)
    perm_disp.SetRepresentationType('Surface')
    ColorBy(perm_disp, ('POINTS', 'Permeability_mD'))
    lut_perm = GetColorTransferFunction('Permeability_mD')
    lut_perm.ApplyPreset('Viridis (matplotlib)', True)
    perm_disp.Opacity = 0.35
    bar_perm = GetScalarBar(lut_perm, view)
    bar_perm.Title = 'Reservoir Permeability (mD)'
    bar_perm.Position = [0.55, 0.05]
    bar_perm.ScalarBarLength = 0.38

sat_files = [f'/apps/energy/vtk/reservoir_saturation_{i:02d}.vtk' for i in range(10)]
sat = LegacyVTKReader(registrationName='Waterflood_Saturation_Animation', FileNames=sat_files)
sat_t = Transform(registrationName='Waterflood_Foreground', Input=sat)
sat_t.Transform.Translate = [5000.0, -40.0, 0.0]
sat_disp = Show(sat_t, view)
sat_disp.SetRepresentationType('Surface')
ColorBy(sat_disp, ('POINTS', 'Water_Saturation'))
lut_sat = GetColorTransferFunction('Water_Saturation')
lut_sat.ApplyPreset('Blues', True)
lut_sat.RescaleTransferFunction(0.20, 0.80)
sat_disp.Opacity = 0.95
bar_sat = GetScalarBar(lut_sat, view)
bar_sat.Title = 'Water Saturation (Sw)'
bar_sat.Position = [0.55, 0.52]
bar_sat.ScalarBarLength = 0.38

inj = Sphere(registrationName='Water_Injection_Well')
inj.Center = [5400.0, -40.0, 2100.0]
inj.Radius = 90.0
inj_disp = Show(inj, view)
inj_disp.DiffuseColor = [0.1, 0.8, 1.0]

prod = Sphere(registrationName='Oil_Production_Well')
prod.Center = [8600.0, -40.0, 400.0]
prod.Radius = 90.0
prod_disp = Show(prod, view)
prod_disp.DiffuseColor = [0.1, 1.0, 0.2]

# Setup camera and animation timeline
ResetCamera()
view.CameraPosition = [4500.0, -9600.0, 2200.0]
view.CameraFocalPoint = [4500.0, 0.0, 1250.0]
view.CameraViewUp = [0.0, 0.22, 0.97]

scene = GetAnimationScene()
timeKeeper = GetTimeKeeper()
scene.StartTime = 0.0
scene.EndTime = 9.0
scene.PlayMode = 'Snap To TimeSteps'
scene.NumberOfFrames = 10
scene.Loop = 1
timeKeeper.Time = 0.0

Render()
SaveState('/apps/energy/paraview/energy_visualization.pvsm')
SaveScreenshot('/scratch/visualizations/paraview_3d_energy_scene.png', view, ImageResolution=[1920, 1080])
EOF_PV_SCRIPT

export DISPLAY=:1
/usr/bin/pvpython /apps/energy/paraview/setup_paraview_animation.py

# 6. Configure ParaView GUI Service on Display :1
cat << 'EOSERVICE' > /etc/systemd/system/paraview-gui.service
[Unit]
Description=ParaView 3D Energy HPC GUI Application
After=xfce4-session.service
Requires=xfce4-session.service

[Service]
Type=simple
User=hpcuser
Environment=DISPLAY=:1
Environment=HOME=/home/hpcuser
ExecStartPre=/bin/sleep 2
ExecStart=/usr/bin/paraview --script=/apps/energy/paraview/setup_paraview_animation.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EODESK' > /home/hpcuser/Desktop/ParaView_Energy_HPC.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=ParaView (3D Energy HPC Animation)
Comment=Launch ParaView with 3D Seismic & Reservoir Simulation
Exec=paraview --script=/apps/energy/paraview/setup_paraview_animation.py
Icon=paraview
Path=/apps/energy/paraview
Terminal=false
StartupNotify=true
EODESK
chmod +x /home/hpcuser/Desktop/ParaView_Energy_HPC.desktop
cp /home/hpcuser/Desktop/ParaView_Energy_HPC.desktop /root/Desktop/
chown -R hpcuser:hpcuser /home/hpcuser/Desktop

systemctl daemon-reload
systemctl enable paraview-gui
systemctl restart paraview-gui

# 7. Start Cloudflare Tunnels (ThinLinc on 300, noVNC on 80)
cat << 'EOSERVICE' > /etc/systemd/system/cloudflared-thinlinc.service
[Unit]
Description=Cloudflare Tunnel for ThinLinc Web Access (Port 300)
After=network.target tlwebaccess.service

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url https://127.0.0.1:300 --no-tls-verify --no-autoupdate --logfile /var/log/cloudflared-thinlinc.log
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOSERVICE

cat << 'EOSERVICE' > /etc/systemd/system/cloudflared-novnc.service
[Unit]
Description=Cloudflare Tunnel for noVNC Web Desktop (Port 80)
After=network.target nginx.service novnc.service

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80 --no-autoupdate --logfile /var/log/cloudflared-novnc.log
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOSERVICE

systemctl daemon-reload
systemctl enable cloudflared-thinlinc cloudflared-novnc
systemctl restart cloudflared-thinlinc cloudflared-novnc

sleep 8
THINLINC_URL=$(grep -o 'https://[-a-zA-Z0-9]*\.trycloudflare\.com' /var/log/cloudflared-thinlinc.log | tail -n 1)
NOVNC_URL=$(grep -o 'https://[-a-zA-Z0-9]*\.trycloudflare\.com' /var/log/cloudflared-novnc.log | tail -n 1)

cat << EOF_URLS | tee /var/log/public-tunnel-url.txt
================================================================================
⚡ ENERGY HPC PARAVIEW 3D VIZ & THINLINC ACCESS (LIVE)
================================================================================
1. ThinLinc Web Access (HTML5 / Native Client):
   URL:      ${THINLINC_URL}
   Username: hpcuser
   Password: GoogleHPC2026!
   (Alternative: root / GoogleHPC2026!)

2. 1-Click Browser Web Desktop (noVNC / Passwordless):
   URL:      ${NOVNC_URL}/vnc.html?autoconnect=true&resize=remote

3. Running Application:
   ParaView 3D Energy HPC Visualization (Display :1)
   Dataset: Marmousi 2 Seismic Wavefield + SPE 10 Reservoir Waterflood
   State Script: /apps/energy/paraview/setup_paraview_animation.py
================================================================================
EOF_URLS

touch /var/log/energy-paraview-setup-complete
echo "=== SETUP COMPLETE ==="
cat /var/log/public-tunnel-url.txt
