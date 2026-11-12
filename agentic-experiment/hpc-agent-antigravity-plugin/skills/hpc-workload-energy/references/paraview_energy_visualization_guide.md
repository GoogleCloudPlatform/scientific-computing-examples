# Interactive 3D ParaView & ThinLinc Remote Visualization Guide for Energy HPC

This guide details the architectural decisions, pipeline configurations, and troubleshooting solutions for building interactive, animated 3D visualizations of **Seismic Exploration** and **Reservoir Simulation** datasets on Google Cloud Compute Engine (GCE).

---

## 1. Remote Visualization Architecture

Visualizing multi-gigabyte seismic wavefields and reservoir saturation plumes requires dedicated visualization nodes placed close to the compute and storage tiers:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Google Cloud GCE Visualization Node                             │
│                  (c2-standard-16 / c4-standard-16, us-central1-a)                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  Virtual Display (:1)          Software / GPU OpenGL                                   │
│  ┌────────────────────────┐   ┌──────────────────────────────────────────────────────┐ │
│  │   Xvfb (:1) Framebuffer│   │ ParaView GUI (--script=setup_paraview_animation.py)  │ │
│  │   1920x1080x24 bpp     │   │ - Left: Marmousi 2 Seismic (Velocity + 3D Wavefield) │ │
│  │   XFCE4 Desktop Session│   │ - Right: SPE 10 Reservoir (Permeability + Water)     │ │
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
│ Cloudflare Quick Tunnels (cloudflared): Exposes zero-external-IP VMs (--no-address)     │
│  - ThinLinc HTML5 / Client: https://<subdomain-1>.trycloudflare.com                   │
│  - 1-Click noVNC Desktop:   https://<subdomain-2>.trycloudflare.com                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. VTK Dataset Format & Conformance

### The XML VTI Pitfall
When writing custom Python scripts to export `.vti` XML files, appending raw binary data outside the root element creates invalid XML:
```text
vtkXMLDataParser: Error parsing XML in stream at line 14: junk after document element
vtkXMLImageDataReader: Error parsing input file. ReadXMLInformation aborting.
vtkStreamingDemandDrivenPipeline: No whole extent has been set in the information for output port 0
```
This triggers ParaView's modal **Output Messages** error window and prevents dataset loading.

### The Universal Standard: Legacy VTK (`.vtk` STRUCTURED_POINTS)
Standard ASCII Legacy VTK is 100% compliant across all ParaView versions, requires zero external C++ XML libraries, and eliminates parsing errors:

```text
# vtk DataFile Version 3.0
Velocity Data
ASCII
DATASET STRUCTURED_POINTS
DIMENSIONS 401 1 201
ORIGIN 0 0 0
SPACING 10.0 10.0 12.5
POINT_DATA 80601
SCALARS Velocity float 1
LOOKUP_TABLE default
<float values space-delimited>
```

### Memory Mapping & Axis Conventions
VTK's `STRUCTURED_POINTS` expects row-major indexing:
$$\text{Index} = k \cdot (N_x \cdot N_y) + j \cdot N_x + i$$
For a vertical 2D cross-section ($N_y = 1$), this reduces to $\text{Index} = k \cdot N_x + i$, where row index $k$ corresponds to depth $Z$ and column index $i$ corresponds to horizontal offset $X$. This matches NumPy's `array_2d.flatten()`.

---

## 3. Multi-Domain Physical Equal Scaling

In industry subsurface workflows, seismic exploration covers large regional surveys ($4\text{–}10\,\text{km}$), while reservoir models cover localized field developments ($0.5\text{–}1.5\,\text{km}$). Displaying both models unscaled results in a severe visual mismatch (seismic dwarfs reservoir).

### Equal Scale Specification ($4,000\,\text{m} \times 2,500\,\text{m}$)
Both domains are normalized to the exact same visual footprint:

| Parameter | Seismic Exploration (Marmousi 2) | Reservoir Simulation (SPE 10) |
| :--- | :---: | :---: |
| **Grid Dimensions ($N_x \times N_z$)** | $401 \times 201$ | $81 \times 51$ |
| **Cell Spacing ($\Delta x \times \Delta z$)** | $10.0\,\text{m} \times 12.5\,\text{m}$ | $50.0\,\text{m} \times 50.0\,\text{m}$ |
| **Physical Width ($X$)** | $(401 - 1) \times 10.0 = \mathbf{4,000.0\,\text{m}}$ | $(81 - 1) \times 50.0 = \mathbf{4,000.0\,\text{m}}$ |
| **Physical Height ($Z$)** | $(201 - 1) \times 12.5 = \mathbf{2,500.0\,\text{m}}$ | $(51 - 1) \times 50.0 = \mathbf{2,500.0\,\text{m}}$ |
| **Aspect Ratio** | $\mathbf{1.6 : 1}$ | $\mathbf{1.6 : 1}$ |
| **Viewport Coordinate Span** | $X \in [0, 4000\,\text{m}]$ | $X \in [5000, 9000\,\text{m}]$ |

A clean $1,000\,\text{m}$ horizontal gap separates the two disciplines in the 3D viewport.

---

## 4. 3D Depth Occlusion & Layer Ordering

### The Depth Occlusion Bug
When rendering two co-located planar layers (e.g. static geology + animated wavefield):
* **Camera Position:** $Y = -9,600\,\text{m}$ looking towards the origin ($Y = 0$).
* If the static background model is placed at $Y = 0\,\text{m}$ with $100\%$ opacity, and the animated layer is placed at $Y = +30\,\text{m}$, the static model sits **directly between the camera and the animation**.
* **Symptom:** When pressing Play, the animation is updating behind the opaque slab and is completely invisible from the front camera angle.

### The Fix: Foreground Translation + Translucent Backgrounds
* **Static Background Geology (Marmousi Velocity & SPE 10 Permeability):**
  * Position: $Y = 0.0\,\text{m}$
  * Opacity: $0.35$ ($35\%$ translucent context)
* **Animated Foreground Simulations (Acoustic Wavefield & Waterflood Saturation):**
  * Position: $Y = -40.0\,\text{m}$ (shifted closer to the camera at $Y = -9,600\,\text{m}$)
  * Opacity: $0.95$ ($95\%$ vivid foreground)
* **Markers:** Shot source ($\text{Red}$), Water injector ($\text{Cyan}$), and Oil producer ($\text{Green}$) placed at $Y = -40.0\,\text{m}$.

---

## 5. Automated ParaView GUI Scripting (`--script` vs `--state`)

### Why `--state=*.pvsm` Fails in Headless Automation
Opening ParaView with `--state` triggers a modal "Load State Options" dialog if file paths or session settings differ, leaving the viewport blank until user interaction.

### The `--script` Solution
Passing `--script=/path/to/script.py` executes directly within the active ParaView Qt GUI event loop:
```bash
paraview --script=/apps/energy/paraview/setup_paraview_animation.py
```
* Bypasses all state file recovery prompts.
* Automatically binds file series:
  ```python
  wave_files = [f'/apps/energy/vtk/seismic_wavefield_{i:02d}.vtk' for i in range(10)]
  wave = LegacyVTKReader(registrationName='Seismic_Wavefield_Animation', FileNames=wave_files)
  ```
* Configures animation timeline explicitly:
  ```python
  scene = GetAnimationScene()
  timeKeeper = GetTimeKeeper()
  scene.StartTime = 0.0
  scene.EndTime = 9.0
  scene.PlayMode = 'Snap To TimeSteps'
  scene.NumberOfFrames = 10
  scene.Loop = 1
  timeKeeper.Time = 0.0
  ```
