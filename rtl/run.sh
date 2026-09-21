#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

for variant in time_serial freq_serial time_opt freq_opt; do
  bash "$ROOT/rtl/$variant/run.sh"
done
