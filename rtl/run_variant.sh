#!/usr/bin/env bash
# Shared compile/run path. Generated fixtures are not RRC golden vectors: the
# transport wrappers use identity shell fixtures, and time_serial (T30) uses
# structural frames from an exact integer reference of the accepted policy.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
variant="${1:?variant is required}"
shift
case "$variant" in
  time_serial|freq_serial|time_opt|freq_opt) ;;
  *) printf 'Unknown variant: %s\n' "$variant" >&2; exit 2 ;;
esac
BUILD_DIR="$ROOT/.build/rtl/$variant"
vector_dir=""
width=16
spc=1
override=0
while (($#)); do
  case "$1" in
    --vectors|--data-width|--spc)
      if (($# < 2)); then printf 'Missing value for %s\n' "$1" >&2; exit 2; fi
      case "$1" in
        --vectors) vector_dir="$2" ;;
        --data-width) width="$2"; override=1 ;;
        --spc) spc="$2"; override=1 ;;
      esac
      shift 2 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
if [[ -n "$vector_dir" && "$override" == 1 ]]; then
  printf 'The manifest owns DATA_WIDTH/SPC; --vectors cannot use width/SPC overrides\n' >&2
  exit 2
fi
if [[ "$variant" == time_serial && ( "$width" != 16 || "$spc" != 1 ) ]]; then
  printf 'time_serial implements only production DATA_WIDTH=16 at SPC=1\n' >&2
  exit 2
fi
mkdir -p "$BUILD_DIR"
if [[ -z "$vector_dir" && "$variant" == time_serial ]]; then
  vector_dir="$BUILD_DIR/fixture-canonical"
  "${PYTHON:-python3}" "$ROOT/sim/python/tests/rtl_filter_fixture.py" \
    --output "$vector_dir" --frame canonical
elif [[ -z "$vector_dir" ]]; then
  vector_dir="$BUILD_DIR/fixture-w${width}-spc${spc}"
  "${PYTHON:-python3}" "$ROOT/sim/python/tests/rtl_shell_fixture.py" \
    --output "$vector_dir" --data-width "$width" --spc "$spc"
fi
vector_dir=$(realpath "$vector_dir")
for name in vector_manifest.svh input.hex expected.hex; do
  if [[ ! -f "$vector_dir/$name" || ! -f "$vector_dir/$name.sha256" ]]; then
    printf 'Missing vector file or checksum: %s/%s\n' "$vector_dir" "$name" >&2
    exit 1
  fi
done
bash "$ROOT/scripts/check-vectors.sh" "$vector_dir"
defines=(-D "DUT_MODULE=${variant}_filter")
sources=("$ROOT/rtl/common/rrc_pkg.sv" "$ROOT/rtl/common/rrc_reset_sync.sv")
if [[ "$variant" != time_serial ]]; then
  defines+=(-D RRC_TRANSPORT_DUT)
  sources+=("$ROOT/rtl/common/rrc_stream_shell.sv")
fi
if [[ "$variant" == freq_* ]]; then defines+=(-D FREQ_DUT); fi
iverilog -g2012 -Wall "${defines[@]}" -I "$vector_dir" \
  -s rrc_stream_tb -o "$BUILD_DIR/sim.out" \
  "${sources[@]}" "$ROOT/rtl/$variant/${variant}_filter.sv" "$ROOT/rtl/tb/rrc_stream_tb.sv"
vvp "$BUILD_DIR/sim.out" "+vector_dir=$vector_dir"
