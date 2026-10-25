#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# One row when --lanes is given; otherwise both base rows of T42: F-U4 (U=4) and
# F-U8 (U=8), on their committed rtl_matching vectors. Existing vectors and
# captures belong to one row, so they need it explicitly.
row=0
single=0
for argument in "$@"; do
  case "$argument" in
    --lanes) row=1 ;;
    --vectors|--capture) single=1 ;;
  esac
done
if ((row)); then
  exec bash "$ROOT/rtl/run_variant.sh" freq_opt "$@"
fi
if ((single)); then
  printf -- '--vectors and --capture need --lanes: one row per run\n' >&2
  exit 2
fi
for lanes in 4 8; do
  bash "$ROOT/rtl/run_variant.sh" freq_opt --lanes "$lanes" "$@"
done
