#!/usr/bin/env bash
# ==============================================================================
# High-Performance Animated GIF Compiler for VMD Molecular Trajectories
# Uses two-pass FFmpeg differential palette extraction and Bayer dithering
# ==============================================================================
set -euo pipefail

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -i, --input-dir DIR      Directory containing VMD frame_*.png snapshots (required)"
    echo "  -o, --output-gif FILE    Path for compiled animated GIF (default: ./vmd_trajectory.gif)"
    echo "  -f, --fps NUM            Frames per second (default: 10)"
    echo "  -w, --width NUM          Target width in pixels, height scaled proportionally (default: 800)"
    echo "  -s, --hold-start SEC     Seconds to hold on initial virgin conformation (default: 1.0)"
    echo "  -e, --hold-end SEC       Seconds to hold on final trajectory conformation (default: 1.5)"
    echo "  -h, --help               Display this help message"
    exit 1
}

INPUT_DIR=""
OUTPUT_GIF="./vmd_trajectory.gif"
FPS=10
WIDTH=800
HOLD_START=1.0
HOLD_END=1.5

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--input-dir) INPUT_DIR="$2"; shift 2 ;;
        -o|--output-gif) OUTPUT_GIF="$2"; shift 2 ;;
        -f|--fps) FPS="$2"; shift 2 ;;
        -w|--width) WIDTH="$2"; shift 2 ;;
        -s|--hold-start) HOLD_START="$2"; shift 2 ;;
        -e|--hold-end) HOLD_END="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "[!] Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$INPUT_DIR" || ! -d "$INPUT_DIR" ]]; then
    echo "[!] Error: Input snapshot directory not specified or does not exist."
    usage
fi

FRAMES=($(find "$INPUT_DIR" -maxdepth 1 -type f -name "frame_*.png" | sort -V))
NUM_FRAMES=${#FRAMES[@]}

if [[ $NUM_FRAMES -eq 0 ]]; then
    echo "[!] Error: No frame_*.png images found in $INPUT_DIR"
    exit 1
fi

echo "================================================================================"
echo "⚡ COMPILING VMD TRAJECTORY ANIMATION"
echo "Frames Source:   $INPUT_DIR ($NUM_FRAMES frames)"
echo "Output GIF:      $OUTPUT_GIF"
echo "Frame Rate:      $FPS fps (width: ${WIDTH}px)"
echo "Hold Pacing:     ${HOLD_START}s start | ${HOLD_END}s end"
echo "================================================================================"

MANIFEST="$INPUT_DIR/ffmpeg_manifest.txt"
FRAME_DUR=$(awk -v fps="$FPS" 'BEGIN { printf "%.4f", 1.0/fps }')

START_COUNT=$(awk -v h="$HOLD_START" -v fps="$FPS" 'BEGIN { printf "%d", int(h*fps) }')
END_COUNT=$(awk -v h="$HOLD_END" -v fps="$FPS" 'BEGIN { printf "%d", int(h*fps) }')

rm -f "$MANIFEST"
# Initial frame hold
for ((i=0; i<START_COUNT; i++)); do
    echo "file '${FRAMES[0]}'" >> "$MANIFEST"
    echo "duration $FRAME_DUR" >> "$MANIFEST"
done

# Trajectory sequence
for frame in "${FRAMES[@]}"; do
    echo "file '$frame'" >> "$MANIFEST"
    echo "duration $FRAME_DUR" >> "$MANIFEST"
done

# Final frame hold
for ((i=0; i<END_COUNT; i++)); do
    echo "file '${FRAMES[-1]}'" >> "$MANIFEST"
    echo "duration $FRAME_DUR" >> "$MANIFEST"
done

# Concat demuxer requirement
echo "file '${FRAMES[-1]}'" >> "$MANIFEST"

PALETTE="$INPUT_DIR/palette.png"
mkdir -p "$(dirname "$OUTPUT_GIF")"

echo "[*] Pass 1: Extracting differential statistics color palette..."
ffmpeg -y -f concat -safe 0 -i "$MANIFEST" \
    -vf "scale=${WIDTH}:-1:flags=lanczos,palettegen=stats_mode=diff:max_colors=256" \
    "$PALETTE"

echo "[*] Pass 2: Rendering optimized GIF with Bayer scale 3 dithering..."
ffmpeg -y -f concat -safe 0 -i "$MANIFEST" -i "$PALETTE" \
    -filter_complex "[0:v]scale=${WIDTH}:-1:flags=lanczos[s];[s][1:v]paletteuse=dither=bayer:bayer_scale=3" \
    -loop 0 "$OUTPUT_GIF"

GIF_SIZE_KB=$(du -k "$OUTPUT_GIF" | cut -f1)
echo "================================================================================"
echo "⚡ VMD ANIMATION COMPILED: $OUTPUT_GIF (${GIF_SIZE_KB} KB)"
echo "================================================================================"
