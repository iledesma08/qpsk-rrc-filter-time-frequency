#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

for variant in time_serial freq_serial time_opt freq_opt; do
  # The filters (T30, T32, T40, T42) implement only production DATA_WIDTH=16 at SPC=1
  # and have their own vectors, so diagnostic width/SPC/vector arguments do not
  # apply to them.
  if [[ $# -gt 0 ]]; then
    printf 'skipping %s: it implements only production DATA_WIDTH=16 at SPC=1\n' "$variant"
    continue
  fi
  bash "$ROOT/rtl/$variant/run.sh" "$@"
done
# The test-only transport wrapper is the one DUT that takes the diagnostic
# width/SPC arguments: it checks the testbench mechanics, not a filter.
bash "$ROOT/rtl/run_variant.sh" transport "$@"
