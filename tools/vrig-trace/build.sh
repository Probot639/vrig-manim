#!/usr/bin/env bash
# Bundle entry.ts against a 0xVRIG source tree.
#   tools/vrig-trace/build.sh /path/to/0xVRIG-main
# Needs esbuild somewhere. Set ESBUILD if it isn't on PATH.
set -euo pipefail

VRIG=${1:?usage: build.sh /path/to/0xVRIG}
HERE=$(cd "$(dirname "$0")" && pwd)
ESBUILD=${ESBUILD:-esbuild}

# entry.ts imports through VRIG's @/ alias, so point esbuild at VRIG's tsconfig
# entry.ts -> vrig-trace.mjs, every <name>-entry.ts -> vrig-<name>.mjs
pairs=(entry:vrig-trace)
for f in "$HERE"/*-entry.ts; do
  n=$(basename "$f" -entry.ts)
  pairs+=("$n-entry:vrig-$n")
done
for pair in "${pairs[@]}"; do
  "$ESBUILD" "$HERE/${pair%%:*}.ts" --bundle --platform=node --format=esm \
    --tsconfig="$VRIG/tsconfig.json" --log-level=warning \
    --outfile="$HERE/dist/${pair##*:}.mjs"
  echo "built $HERE/dist/${pair##*:}.mjs"
done
