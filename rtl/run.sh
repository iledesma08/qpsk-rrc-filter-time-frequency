#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

for variant in time_serial freq_serial time_opt freq_opt; do
  # The filters (T30, T32, T40) implement only production DATA_WIDTH=16 at SPC=1
  # and have their own fixtures, so diagnostic width/SPC/vector arguments do not
  # apply to them.
  if [[ "$variant" != freq_opt && $# -gt 0 ]]; then
    printf 'skipping %s: it implements only production DATA_WIDTH=16 at SPC=1\n' "$variant"
    continue
  fi
  bash "$ROOT/rtl/$variant/run.sh" "$@"
done
