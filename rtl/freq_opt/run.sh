#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BUILD_DIR="$ROOT/.build/rtl/freq_opt"
mkdir -p "$BUILD_DIR"
cd "$ROOT"

iverilog -g2012 -Wall \
  -D DUT_MODULE=freq_opt_filter \
  -s rrc_placeholder_tb \
  -o "$BUILD_DIR/sim.out" \
  rtl/common/rrc_stream_placeholder.sv \
  rtl/freq_opt/freq_opt_filter.sv \
  rtl/tb/rrc_placeholder_tb.sv
vvp "$BUILD_DIR/sim.out"
