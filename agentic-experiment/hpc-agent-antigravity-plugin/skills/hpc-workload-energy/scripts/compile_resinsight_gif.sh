#!/usr/bin/env bash
# ==============================================================================
# compile_resinsight_gif.sh
#
# High-Performance FFmpeg GIF Compiler for OPM ResInsight Simulation Snapshots
#
# Generates razor-sharp, lightweight animated GIFs from sequential ResInsight
# 3D reservoir snapshots (e.g. SOIL, SGAS, PRESSURE) using two-pass color
# palette optimization (palettegen / paletteuse with Bayer dithering) and
# customizable hold times for initial virgin and final swept states.
# ==============================================================================

set -euo pipefail

usage() {
  cat << EOF
Usage: $(basename "$0") [OPTIONS] <input_dir> <output_gif>

Arguments:
  <input_dir>    Directory containing sequentially named PNG snapshots
                 (e.g. *SOIL_00_*.png through *SOIL_64_*.png)
  <output_gif>   Path to the destination animated GIF file

Options:
  --fps <int>            Framerate for intermediate report steps (default: 10)
  --initial-hold <float> Pause duration in seconds on the initial state (default: 1.0)
  --final-hold <float>   Pause duration in seconds on the final state (default: 1.5)
  --pattern <glob>       Filename pattern filter (default: "*SOIL_*.png")
  -h, --help             Show this help message and exit

Example:
  $(basename "$0") --fps 10 --initial-hold 1.0 --final-hold 1.5 ~/snapshots norne_resinsight.gif
EOF
  exit 1
}

FPS=10
INITIAL_HOLD=1.0
FINAL_HOLD=1.5
PATTERN="*SOIL_*.png"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fps)
      FPS="$2"
      shift 2
      ;;
    --initial-hold)
      INITIAL_HOLD="$2"
      shift 2
      ;;
    --final-hold)
      FINAL_HOLD="$2"
      shift 2
      ;;
    --pattern)
      PATTERN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    -*)
      echo "[-] Unknown option: $1" >&2
      usage
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 2 ]]; do
  echo "[-] Error: Missing required arguments." >&2
  usage
fi

INPUT_DIR="$1"
OUTPUT_GIF="$2"

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "[-] Error: Input directory '$INPUT_DIR' does not exist." >&2
  exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
  echo "[-] Error: ffmpeg is not installed or not in PATH." >&2
  exit 1
fi

TMP_DIR=$(mktemp -d /tmp/resinsight_gif_XXXXXX)
trap 'rm -rf "$TMP_DIR"' EXIT

CONCAT_FILE="$TMP_DIR/frames.txt"

echo "[*] Scanning for simulation snapshots in '$INPUT_DIR' matching '$PATTERN'..."

# Use python to perform strict chronological sorting and deduplication
python3 - << PYEOF
import glob
import os
import re
import sys

input_dir = "$INPUT_DIR"
pattern = "$PATTERN"
concat_file = "$CONCAT_FILE"
fps = float("$FPS")
initial_hold = float("$INITIAL_HOLD")
final_hold = float("$FINAL_HOLD")

step_duration = round(1.0 / fps, 4)

search_path = os.path.join(input_dir, pattern)
files = glob.glob(search_path)

if not files:
    print(f"[-] Error: No files found matching {search_path}", file=sys.stderr)
    sys.exit(1)

step_files = {}
for f in files:
    m = re.search(r'SOIL_(\d+)_', os.path.basename(f))
    if m:
        step = int(m.group(1))
        # Prefer dashed dates over underscore variants if duplicate step numbers exist
        if step not in step_files or '-' in os.path.basename(f):
            step_files[step] = os.path.abspath(f)

if not step_files:
    # Fallback to sorted alphabetical order if SOIL_\d+_ pattern not matched
    sorted_files = sorted(files)
    for idx, f in enumerate(sorted_files):
        step_files[idx] = os.path.abspath(f)

sorted_steps = sorted(step_files.keys())
total_frames = len(sorted_steps)
print(f"[+] Found {total_frames} sequentially verified timesteps (Steps {sorted_steps[0]} to {sorted_steps[-1]})")

with open(concat_file, 'w') as out:
    for idx, step in enumerate(sorted_steps):
        filepath = step_files[step]
        if idx == 0:
            dur = initial_hold
        elif idx == total_frames - 1:
            dur = final_hold
        else:
            dur = step_duration
        out.write(f"file '{filepath}'\n")
        out.write(f"duration {dur}\n")
    # Concat demuxer requirement: repeat the last frame entry
    out.write(f"file '{step_files[sorted_steps[-1]]}'\n")

print(f"[+] Wrote concat manifest with {total_frames} frames to {concat_file}")
PYEOF

echo "[*] Compiling GIF via FFmpeg two-pass palette optimization..."
ffmpeg -y -f concat -safe 0 -i "$CONCAT_FILE" \
  -filter_complex "[0:v]split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
  "$OUTPUT_GIF"

ORIGINAL_SIZE=$(du -ch "$INPUT_DIR"/$PATTERN | tail -n 1 | cut -f 1)
GIF_SIZE=$(du -h "$OUTPUT_GIF" | cut -f 1)

echo "================================================================================"
echo "⚡ SUCCESS: ResInsight simulation animation GIF compiled successfully!"
echo "   Output:        $OUTPUT_GIF"
echo "   Raw Snapshots: $ORIGINAL_SIZE"
echo "   Optimized GIF: $GIF_SIZE (Two-pass diff palette + Bayer dithering)"
echo "   FPS:           $FPS (Initial hold: ${INITIAL_HOLD}s, Final hold: ${FINAL_HOLD}s)"
echo "================================================================================"
