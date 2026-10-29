#!/usr/bin/env bash
# Full site build: index + thread pages (uv) then the search-page bundle (esbuild).
# usage: site/build.sh [out dir]   default $VRG_DATA/site-r1/dist (VRG_DATA defaults to ../vrg-archive-data)
set -euo pipefail
cd "$(dirname "$0")"
(cd web && npm ci --silent)
uv run vrg-site build ${1:+--out "$1"}
