#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# One row when --systolic-pes is given; otherwise both base rows of T40:
# T-S4P1 (S=4) and T-S8P1 (S=8), both at P=1, on the generated fixture.
# Existing vectors and captures belong to one row, so they need it explicitly.
row=0
single=0
for argument in "$@"; do
  case "$argument" in
    --systolic-pes) row=1 ;;
    --vectors|--capture) single=1 ;;
  esac
done
if ((row)); then
  exec bash "$ROOT/rtl/run_variant.sh" time_opt "$@"
fi
if ((single)); then
  printf -- '--vectors and --capture need --systolic-pes: one row per run\n' >&2
  exit 2
fi
for pes in 4 8; do
  bash "$ROOT/rtl/run_variant.sh" time_opt --systolic-pes "$pes" --pipeline-depth 1 "$@"
done
