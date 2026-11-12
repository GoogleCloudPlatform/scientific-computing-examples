#!/usr/bin/env python3
"""Scientific 3D Lab helper: ParaView, VMD, WebGL (Three.js/3Dmol.js) & DVR.

Provides pure standard-library tools for:
  1. **ParaView Capability**: Generating `pvpython` pre-bake & live animation
     scripts with `DataMode='Binary'` `.vtp`/`.vti` caches, `CellDatatoPointData`
     (lowercase `to`) prior to `Decimate`, `GetTimeTrack().Enabled = 0` to
     prevent OpenFOAM `t=0` field resets, `PythonAnimationCue` camera/slice/
     isosurface animations (never `KeyFrameAnimationCue` on `Contour.Isosurfaces`),
     `ParaView5.10.0.ini` (`ShowWelcomeDialog=false`), and equal-scale multi-
     domain spatial alignment (`4000m x 2500m`, `Y = -40m` unocclusion).
  2. **VMD Capability**: Generating Visual Molecular Dynamics (`vmd -dispdev
     text -e`) Tcl scripts with `NewCartoon` secondary structure, `Licorice`
     catalytic active-site residues, `VDW` ions, transparent `QuickSurf`
     (`opacity=0.25`) solvent envelopes, `Tachyon` ray-tracing, and two-pass
     FFmpeg differential palette GIF commands (`palettegen=stats_mode=diff` +
     `paletteuse=dither=bayer:bayer_scale=3`).
  3. **WebGL (`Three.js` & `3Dmol.js`) & Binary `.bin` CAD Exporter**: Packing
     and unpacking compact `PF1B` (`<4s5I`) `float16` vertex + `uint16`/`uint32`
     indexed triangle meshes with LH centerline mirror metadata, plus generating
     `3Dmol.js` zero-size container guards (`clientWidth < 16 || clientHeight < 16`).
  4. **Live Prompt Playground, noVNC DVR & 50x Time-Warp Replay**: Validating
     50x Time-Warp stage manifests (`S0 -> Winner`) and generating Cloud Run
     Direct VPC Egress proxy commands (`--vpc-egress=all-traffic --session-affinity`).
"""

import argparse
import json
import struct
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple


PF1B_MAGIC = b"PF1B"
PF1B_HEADER_FMT = "<4s5I"


def generate_paraview_pvpython_bundle(
    case_path: str = "/var/tmp/foam_bench/case.foam",
    baked_vtp_path: str = "/var/tmp/foam_bench/car_surface_baked.vtp",
    baked_vti_path: str = "/var/tmp/foam_bench/flow_volume_baked.vti",
    equal_scale_domain: bool = False,
) -> Dict[str, str]:
  """Generates ParaView `pvpython` pre-bake/animation scripts & `ParaView5.10.0.ini`."""
  ini_config = (
      "[General]\n"
      "ShowWelcomeDialog=false\n"
      "AutoConvertProperties=true\n"
  )

  align_snippet = ""
  surface_out = "decimated"
  if equal_scale_domain:
    surface_out = "transformFilter"
    align_snippet = (
        "# Equal-Scale Multi-Domain Spatial Alignment (4000m x 2500m, Y=-40m depth)\n"
        "transformFilter = Transform(Input=decimated)\n"
        "transformFilter.Transform.Translate = [0.0, -40.0, 0.0]\n"
        "transformFilter.Transform.Scale = [1.0, 1.0, 1.0]\n"
    )

  pvpython_script = f"""# ParaView High-FPS Binary Pre-Bake & PythonAnimationCue Script
from paraview.simple import *

reader = OpenFOAMReader(FileName={case_path!r})
reader.MeshRegions = ['internalMesh', 'car_group']
reader.CellArrays = ['p', 'U', 'k', 'omega']

scene = GetAnimationScene()
time_keeper = GetTimeKeeper()
if len(time_keeper.TimestepValues) > 0:
    scene.AnimationTime = time_keeper.TimestepValues[-1]
# CRITICAL: Disable TimeKeeper track so Play() does not reset OpenFOAM to t=0
GetTimeTrack().Enabled = 0

# CRITICAL: Use CellDatatoPointData (lowercase 'to') and Triangulate BEFORE
# Decimate so pressure arrays and quad faces survive polygon reduction
c2p = CellDatatoPointData(Input=reader)
surface = ExtractSurface(Input=c2p)
tri = Triangulate(Input=surface)
decimated = Decimate(Input=tri)
decimated.TargetReduction = 0.65
{align_snippet}
SaveData({baked_vtp_path!r}, proxy={surface_out}, DataMode='Binary')

resample = ResampleToImage(Input=c2p)
resample.SamplingDimensions = [160, 80, 80]
SaveData({baked_vti_path!r}, proxy=resample, DataMode='Binary')

# Use PythonAnimationCue (NEVER KeyFrameAnimationCue on Contour.Isosurfaces)
cue = PythonAnimationCue()
cue.Script = '''
def start_cue(self): pass
def tick(self):
    from paraview.simple import GetActiveView, Render
    import math
    t = self.GetAnimationTime()
    view = GetActiveView()
    if view:
        view.CameraPosition = [
            -8.5 * math.cos(2.0 * math.pi * t),
            -8.5 * math.sin(2.0 * math.pi * t),
            3.2,
        ]
        Render()
def end_cue(self): pass
'''
scene.Cues.Append(cue)
"""
  return {
      "ParaView5.10.0.ini": ini_config,
      "paraview_prebake_and_animate.py": pvpython_script,
  }


def generate_vmd_tcl_and_ffmpeg_pipeline(
    pdb_Or_gro_path: str = "6lu7_solv_ions.gro",
    trajectory_path: str = "md_prod_noPBC.xtc",
    catalytic_resids: Sequence[int] = (41, 145),
    num_frames: int = 90,
    output_gif: str = "vmd_trajectory_3d.gif",
) -> Dict[str, str]:
  """Generates a VMD Tcl script (`NewCartoon`/`Licorice`/`QuickSurf`) and 2-pass FFmpeg GIF command."""
  if not catalytic_resids or num_frames < 1:
    raise ValueError("catalytic_resids must be non-empty and num_frames >= 1")

  struct_ext = pdb_Or_gro_path.rsplit(".", 1)[-1].lower() if "." in pdb_Or_gro_path else "gro"
  struct_type = struct_ext if struct_ext in ("gro", "pdb", "psf", "mol2") else "gro"
  traj_ext = trajectory_path.rsplit(".", 1)[-1].lower() if "." in trajectory_path else "xtc"
  traj_type = traj_ext if traj_ext in ("xtc", "dcd", "trr", "nc") else "xtc"

  resid_str = " ".join(str(int(r)) for r in catalytic_resids)
  tcl_script = f"""# VMD 1.9.3 Automated Multi-Representation & Tachyon Snapshot Script
mol new {pdb_Or_gro_path} type {struct_type} waitfor all
mol addfile {trajectory_path} type {traj_type} waitfor all

display projection Orthographic
display depthcue off
axes location Off
color Display Background black
mol delrep 0 top

# Rep 0: Protein Backbone Secondary Structure (NewCartoon colored by Structure)
mol representation NewCartoon 0.300000 10.000000 4.100000 0
mol color Structure
mol selection {{protein}}
mol material AOChalky
mol addrep top

# Rep 1: Catalytic Active Site Dyad/Triad (Licorice colored by Name)
mol representation Licorice 0.300000 12.000000 12.000000
mol color Name
mol selection {{protein and resid {resid_str}}}
mol material AOShiny
mol addrep top

# Rep 2: Counter-Ions (VDW spheres)
mol representation VDW 0.800000 12.000000
mol color Name
mol selection {{ion or resname NA CL MG ZN}}
mol material AOEdgy
mol addrep top

# Rep 3: Transparent Hydration Shell (QuickSurf opacity=0.25)
mol material Transparent
material change opacity Transparent 0.250000
mol representation QuickSurf 1.200000 0.500000 1.000000 1.000000
mol color ColorID 15
mol selection {{water and within 5.0 of protein}}
mol addrep top

# Render Orbit + Trajectory Frame Series
file mkdir frames
for {{set i 0}} {{$i < {num_frames}}} {{incr i}} {{
    animate goto $i
    rotate y by 4.0
    set fname [format "frames/frame_%04d.tga" $i]
    render TachyonInternal $fname
}}
quit
"""

  ffmpeg_two_pass_cmd = (
      f"vmd -dispdev text -e vmd_render_scene.tcl && \\\n"
      f"ffmpeg -y -framerate 24 -i frames/frame_%04d.tga \\\n"
      f"  -vf 'fps=24,scale=960:-1:flags=lanczos,palettegen=stats_mode=diff' "
      f"palette.png && \\\n"
      f"ffmpeg -y -framerate 24 -i frames/frame_%04d.tga -i palette.png \\\n"
      f"  -lavfi 'fps=24,scale=960:-1:flags=lanczos[x];"
      f"[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle' \\\n"
      f"  {output_gif}"
  )

  return {
      "vmd_render_scene.tcl": tcl_script,
      "ffmpeg_two_pass_gif.sh": ffmpeg_two_pass_cmd,
  }


def pack_pf1b_binary_cad_mesh(
    vertices: Sequence[Tuple[float, float, float]],
    groups: Sequence[Dict[str, Any]],
) -> bytes:
  """Packs a 3D mesh into the compact `PF1B` (`<4s5I`) `float16` WebGL binary format.

  Header layout (`24 bytes`, little-endian `<4s5I`):
    - `magic`: `b'PF1B'` (4 bytes)
    - `version`: `1` (uint32)
    - `num_vertices`: `N` (uint32)
    - `num_groups`: `G` (uint32)
    - `reserved0`, `reserved1`: `0, 0` (uint32)
  Followed by:
    - `N * 3` little-endian `float16` (`<e`) vertex coordinates `(x, y, z)`.
    - JSON group directory length (`uint32`) + UTF-8 JSON group metadata.
    - Per-group local triangle index arrays (`uint16` when group vertex count
      `< 65535`, otherwise `uint32`).
  """
  if not vertices:
    raise ValueError("vertices must not be empty")

  num_verts = len(vertices)
  num_groups = len(groups)
  header = struct.pack(PF1B_HEADER_FMT, PF1B_MAGIC, 1, num_verts, num_groups, 0, 0)

  vert_buf = bytearray()
  for x, y, z in vertices:
    vert_buf.extend(struct.pack("<3e", float(x), float(y), float(z)))

  group_meta: List[Dict[str, Any]] = []
  idx_buf = bytearray()
  for g in groups:
    tris: Sequence[Tuple[int, int, int]] = g.get("triangles", [])
    use_u16 = num_verts < 65535
    group_meta.append(
        {
            "name": str(g.get("name", "body")),
            "mirror_lh": bool(g.get("mirror_lh", True)),
            "num_triangles": len(tris),
            "index_type": "uint16" if use_u16 else "uint32",
        }
    )
    fmt = "<3H" if use_u16 else "<3I"
    for i0, i1, i2 in tris:
      if not (
          0 <= int(i0) < num_verts
          and 0 <= int(i1) < num_verts
          and 0 <= int(i2) < num_verts
      ):
        raise ValueError(
            f"Triangle vertex index out of bounds [0, {num_verts}): {(i0, i1, i2)}"
        )
      idx_buf.extend(struct.pack(fmt, int(i0), int(i1), int(i2)))

  meta_bytes = json.dumps(group_meta, separators=(",", ":"), sort_keys=True).encode(
      "utf-8"
  )
  meta_len_hdr = struct.pack("<I", len(meta_bytes))
  return bytes(header) + bytes(vert_buf) + meta_len_hdr + meta_bytes + bytes(idx_buf)


def unpack_pf1b_binary_cad_header(payload: bytes) -> Dict[str, Any]:
  """Unpacks and validates a `PF1B` binary CAD payload header, vertices, and indices."""
  if len(payload) < 24:
    raise ValueError("Payload shorter than 24-byte PF1B header")

  magic, version, num_verts, num_groups, _, _ = struct.unpack(
      PF1B_HEADER_FMT, payload[:24]
  )
  if magic != PF1B_MAGIC:
    raise ValueError(f"Invalid PF1B magic header: {magic!r}")

  vert_bytes_len = num_verts * 6
  offset = 24
  if len(payload) < offset + vert_bytes_len + 4:
    raise ValueError("Payload truncated inside PF1B vertex buffer")
  first_vert = struct.unpack("<3e", payload[offset : offset + 6])
  offset += vert_bytes_len
  (meta_len,) = struct.unpack("<I", payload[offset : offset + 4])
  offset += 4
  if len(payload) < offset + meta_len:
    raise ValueError("Payload truncated inside PF1B group metadata")
  groups = json.loads(payload[offset : offset + meta_len].decode("utf-8"))
  offset += meta_len

  for g in groups:
    num_tris = int(g.get("num_triangles", 0))
    idx_type = g.get("index_type", "uint16")
    tri_stride = 6 if idx_type == "uint16" else 12
    tri_fmt = "<3H" if idx_type == "uint16" else "<3I"
    if len(payload) < offset + num_tris * tri_stride:
      raise ValueError("Payload truncated inside PF1B triangle index buffer")
    if num_tris > 0:
      g["first_triangle"] = list(
          struct.unpack(tri_fmt, payload[offset : offset + tri_stride])
      )
    offset += num_tris * tri_stride

  return {
      "magic": magic.decode("ascii"),
      "version": version,
      "num_vertices": num_verts,
      "num_groups": num_groups,
      "first_vertex": [round(float(c), 4) for c in first_vert],
      "groups": groups,
      "total_bytes": len(payload),
  }


def validate_timewarp_and_novnc_config(
    stages: Sequence[Dict[str, Any]],
    cloud_run_service: str = "hpc-3d-lab-gateway",
    vpc_network: str = "hpc-viz-vpc",
) -> Dict[str, Any]:
  """Validates a 50x Time-Warp stage manifest (`S0 -> Winner`) and Cloud Run noVNC config."""
  if len(stages) < 2:
    raise ValueError("Time-Warp manifest requires at least 2 stages (S0 -> Winner)")

  monotonic_generations = True
  prev_gen = -1
  for st in stages:
    gen = int(st.get("generation", 0))
    if gen < prev_gen:
      monotonic_generations = False
    prev_gen = gen

  cloud_run_cmd = (
      f"gcloud run deploy {cloud_run_service} \\\n"
      f"  --source=. \\\n"
      f"  --network={vpc_network} \\\n"
      f"  --vpc-egress=all-traffic \\\n"
      f"  --session-affinity \\\n"
      f"  --timeout=3600"
  )

  return {
      "num_stages": len(stages),
      "start_stage_id": stages[0].get("id", "S0"),
      "winner_stage_id": stages[-1].get("id", "S_WIN"),
      "monotonic_generations": monotonic_generations,
      "dvr_modes": ["Replay History to Current Point (DVR)", "Live Mode"],
      "zoom_range_pct": [35, 3600],
      "3dmol_zero_size_guard": "clientWidth < 16 || clientHeight < 16",
      "cloud_run_deploy_cmd": cloud_run_cmd,
  }


def main(argv: Optional[Sequence[str]] = None) -> int:
  parser = argparse.ArgumentParser(
      description="Interactive 3D Lab (ParaView, VMD, WebGL, DVR) CLI."
  )
  subparsers = parser.add_subparsers(dest="cmd", required=True)

  p_pv = subparsers.add_parser(
      "paraview-bundle", help="Generate ParaView binary pre-bake & cue scripts."
  )
  p_pv.add_argument("--equal-scale", action="store_true")

  p_vmd = subparsers.add_parser(
      "vmd-bundle", help="Generate VMD Tcl & 2-pass FFmpeg GIF pipeline."
  )
  p_vmd.add_argument("--frames", type=int, default=90)

  args = parser.parse_args(argv)
  if args.cmd == "paraview-bundle":
    out = generate_paraview_pvpython_bundle(equal_scale_domain=args.equal_scale)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  if args.cmd == "vmd-bundle":
    out = generate_vmd_tcl_and_ffmpeg_pipeline(num_frames=args.frames)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  return 1


if __name__ == "__main__":
  sys.exit(main())
