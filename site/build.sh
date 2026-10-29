#!/usr/bin/env bash
# Full site build: index + thread pages (uv) then the search-page bundle (esbuild).
# usage: site/build.sh [out dir]   default /home/s/code/vrg-archive-data/site-r1/dist
set -euo pipefail
cd "$(dirname "$0")"
(cd web && npm ci --silent)
uv run vrg-site build ${1:+--out "$1"}
