#!/usr/bin/env bash
# Build videos/overviews/<unit>.mp4: a title card, a few seconds of each
# lesson video in the unit, then a closing card. Run from the repo root.
#   tools/overview.sh unit0-asm [clip seconds]
set -euo pipefail

UNIT=${1:?usage: overview.sh <unit-id> [clip seconds]}
CLIP=${2:-5}
OUT=videos/overviews
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"

# title and closing cards for this unit
for scene in UnitIntro UnitOutro; do
  VRIG_UNIT=$UNIT .venv/bin/manimgl scenes/overview.py $scene -w --hd \
    --video_dir "$WORK" --file_name $scene >/dev/null 2>&1
done

# re-encode every piece the same way so the concat demuxer can stitch them
enc=(-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 -an
     -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1:color=black")

pieces=()
norm() { ffmpeg -nostdin -loglevel error -y "$@" "${enc[@]}" "$1x"; }

ffmpeg -nostdin -loglevel error -y -i "$WORK/UnitIntro.mp4" "${enc[@]}" "$WORK/00-intro.mp4"
pieces+=("$WORK/00-intro.mp4")

# the lesson videos, in the unit's own order, first CLIP seconds of each
i=0
for id in $(python3 -c "
import json,sys
u={x['id']:x for x in json.load(open('traces/units.json'))['units']}['$UNIT']
print(' '.join(l['id'] for l in u['lessons']))"); do
  src=$(find videos -path "*/$UNIT/$id.mp4" -o -name "RopBasics.mp4" -path "*$id*" 2>/dev/null | head -1)
  [ -z "$src" ] && src=$(find videos -name "$id.mp4" | head -1)
  if [ -z "$src" ]; then echo "skip $id (no video)"; continue; fi
  i=$((i + 1))
  ffmpeg -nostdin -loglevel error -y -t "$CLIP" -i "$src" "${enc[@]}" "$WORK/$(printf %02d $i)-$id.mp4"
  pieces+=("$WORK/$(printf %02d $i)-$id.mp4")
done

ffmpeg -nostdin -loglevel error -y -i "$WORK/UnitOutro.mp4" "${enc[@]}" "$WORK/99-outro.mp4"
pieces+=("$WORK/99-outro.mp4")

# concat demuxer wants a file list with absolute, quoted paths
list="$WORK/list.txt"
: > "$list"
for p in "${pieces[@]}"; do echo "file '$p'" >> "$list"; done

ffmpeg -nostdin -loglevel error -y -f concat -safe 0 -i "$list" -c copy "$OUT/$UNIT.mp4"
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/$UNIT.mp4")
printf 'built %s/%s.mp4  (%s clips, %.0fs)\n' "$OUT" "$UNIT" "$i" "$dur"
