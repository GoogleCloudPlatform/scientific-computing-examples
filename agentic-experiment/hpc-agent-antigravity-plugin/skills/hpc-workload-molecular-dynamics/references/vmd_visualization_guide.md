# VMD (Visual Molecular Dynamics) Remote Visualization Runbook

This guide covers the deployment, Tcl automation, representation styling, and remote workstation architecture for visualizing Molecular Dynamics (MD) trajectories on Google Cloud using **VMD (Visual Molecular Dynamics)**.

--------------------------------------------------------------------------------

## 1. Architecture Overview

Molecular Dynamics simulations generate large coordinate and trajectory files (`.gro`, `.xtc`, `.trr`, `.dcd`). Visualizing these models interactively without downloading multi-gigabyte trajectories to local machines requires high-throughput remote rendering co-located with cloud compute:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Google Cloud GCE Visualization Node                             │
│                  (c2-standard-16 / c4-standard-16, us-central1-a)                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  Virtual Display (:1)          Software / GPU OpenGL                                   │
│  ┌────────────────────────┐   ┌──────────────────────────────────────────────────────┐ │
│  │   Xvfb (:1) Framebuffer│   │ Visual Molecular Dynamics (VMD v1.9.3)               │ │
│  │   1920x1080x24 bpp     │   │ - 3D Protein Structure (Lysozyme 1AKI, Ubiquitin)    │ │
│  │   XFCE4 Desktop Session│   │ - NewCartoon Colored by Secondary Structure (STRIDE) │ │
│  │                        │   │ - Licorice Active Site Dyad (Glu35 / Asp52)          │ │
│  │                        │   │ - Semi-Transparent QuickSurf Solvent Envelope        │ │
│  │                        │   │ - Smooth Trajectory Playback & Frame Stepper         │ │
│  └────────────────────────┘   └──────────────────────────────────────────────────────┘ │
│                ▲                                        │                              │
│                │                                        ▼                              │
│  ┌────────────────────────┐             ┌────────────────────────┐                     │
│  │ ThinLinc Server (v4.21)│             │  x11vnc Server (:5900) │                     │
│  │ - tlwebaccess (:300)   │             │           ▲            │                     │
│  │ - vsmserver / vsmagent │             │           │            │                     │
│  │ - XFCE4 desktop session│             │  websockify bridge     │                     │
│  └────────────────────────┘             │  nginx reverse proxy   │                     │
│                │                        └────────────────────────┘                     │
│                │ (Port 300 HTTPS)                   │ (Port 80 HTTP)                   │
├────────────────┴────────────────────────────────────┴──────────────────────────────────┤
│ Cloud Run Direct VPC Egress / Localtunnel / Cloudflare Quick Tunnels                   │
│  - Permanent Cloud Run URL: https://norne-resinsight-workstation-<hash>.run.app        │
│  - 1-Click noVNC Desktop:   https://<subdomain>.loca.lt/vnc.html?autoconnect=true      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

--------------------------------------------------------------------------------

## 2. Core VMD CLI & Tcl Execution Modes

### A. Headless Batch Frame Rendering (`-dispdev text`)
Used in automated pipelines and Slurm batch post-processing to generate high-resolution snapshot frames without spawning an X11 window:
```bash
vmd -dispdev text -e render_snapshots.tcl
```

### B. Interactive GUI on Remote Virtual Display (`DISPLAY=:1`)
Launched inside the XFCE desktop environment for interactive 3D rotation, zooming, selection inspection, and trajectory playback:
```bash
DISPLAY=:1 vmd -size 1800 950 system.gro trajectory.xtc -e setup_scene.tcl
```

--------------------------------------------------------------------------------

## 3. Representation & Styling Best Practices

| Representation Style | Target Atoms | Recommended Color Scheme | Material | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **NewCartoon** | `protein` | `Structure` (STRIDE) | `Glossy` | Highlights secondary structure motifs: $\alpha$-helices (magenta), $\beta$-sheets (yellow), turns (cyan), coils (white). |
| **Licorice** | `resid 35 52` (active site) | `Name` (CPK element) | `Opaque` | Atom-level inspection of catalytic dyads, binding pocket residues, or hydrogen bonding networks. |
| **VDW** | `resname CL NA` | `ResType` or `ColorID` | `Glossy` | Neutralizing counterions or crystal waters. |
| **QuickSurf** | `protein` | `ColorID 8` (white/subtle) | `Transparent` | Renders molecular solvent-accessible surface with 0.25 opacity, showing internal folding through envelope. |
| **CPK** | Small molecule ligands | `Element` | `Glossy` | Distinct visualization of drug candidate ligands bound in pockets. |

--------------------------------------------------------------------------------

## 4. Key Tcl Automation Commands

```tcl
# 1. Load Structure and Trajectory
mol new "system.gro" type gro waitfor all
mol addfile "trajectory.xtc" type xtc step 1 waitfor all

# 2. Representation Pipeline
mol delrep 0 top
mol representation NewCartoon 0.3 12.0 4.1 0
mol color Structure
mol selection {protein}
mol addrep top

# 3. Highlight Catalytic Dyad
mol representation Licorice 0.3 12.0 12.0
mol color Name
mol selection {protein and (resid 35 52)}
mol addrep top

# 4. Multi-Frame Snapshot Loop
set num_frames [molinfo top get numframes]
for {set i 0} {$i < $num_frames} {incr i} {
    animate goto $i
    display update
    render snapshot [format "/tmp/snapshots/frame_%04d.png" $i]
}
quit
```

--------------------------------------------------------------------------------

## 5. Two-Pass FFmpeg Differential Palette GIF Optimization

Naive FFmpeg GIF conversion produces 30+ MB files with severe color banding on molecular surfaces. The differential two-pass encoding pattern eliminates banding while reducing file sizes by **30×–35×**:

```bash
# Pass 1: Extract differential statistics palette
ffmpeg -y -f concat -safe 0 -i manifest.txt \
  -vf "scale=800:-1:flags=lanczos,palettegen=stats_mode=diff:max_colors=256" \
  palette.png

# Pass 2: Apply palette with Bayer scale 3 dithering
ffmpeg -y -f concat -safe 0 -i manifest.txt -i palette.png \
  -filter_complex "[0:v]scale=800:-1:flags=lanczos[s];[s][1:v]paletteuse=dither=bayer:bayer_scale=3" \
  -loop 0 vmd_trajectory.gif
```
