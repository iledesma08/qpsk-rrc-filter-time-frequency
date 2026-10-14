#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

for variant in time_serial freq_serial time_opt freq_opt; do
  # freq_serial implements only production DATA_WIDTH=16 at SPC=1 and has its own
  # fixture, so diagnostic width/SPC/vector arguments do not apply to it.
  if [[ "$variant" == freq_serial && $# -gt 0 ]]; then
    printf 'skipping freq_serial: it implements only production DATA_WIDTH=16 at SPC=1\n'
    continue
  fi
  bash "$ROOT/rtl/$variant/run.sh" "$@"
done
