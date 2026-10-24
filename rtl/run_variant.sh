#!/usr/bin/env bash
# Shared compile/run path. Generated fixtures are not RRC golden vectors: the
# transport wrapper (freq_opt) uses identity shell fixtures, time_serial (T30)
# and time_opt (T40) use structural frames from an exact integer reference of
# the accepted policy, and freq_serial (T32/T33) runs the committed rtl_matching
# vectors of F-serial (see rtl_matching_stage.py). time_opt needs its matrix row:
# --systolic-pes S (4 for T-S4P1, 8 for T-S8P1) and --pipeline-depth P (1).
# PPA target runs (T41): --clock-period-ns sets the testbench clock (10 ns by
# default), --netlist runs the final netlist of an OpenLane run instead of the
# RTL (with the Sky130 cell models of --cell-models) and --activity-vcd dumps
# the continuous run's activity window there.
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
capture=""
vcd=""
width=16
spc=1
override=0
pes=""
depth=""
period=""
netlist=""
cell_models=""
activity=""
while (($#)); do
  case "$1" in
    --vectors|--data-width|--spc|--capture|--vcd|--systolic-pes|--pipeline-depth|--clock-period-ns|--netlist|--cell-models|--activity-vcd)
      if (($# < 2)); then printf 'Missing value for %s\n' "$1" >&2; exit 2; fi
      case "$1" in
        --vectors) vector_dir="$2" ;;
        --capture) capture="$2" ;;
        --vcd) vcd="$2" ;;
        --data-width) width="$2"; override=1 ;;
        --spc) spc="$2"; override=1 ;;
        --systolic-pes) pes="$2" ;;
        --pipeline-depth) depth="$2" ;;
        --clock-period-ns) period="$2" ;;
        --netlist) netlist="$2" ;;
        --cell-models) cell_models="$2" ;;
        --activity-vcd) activity="$2" ;;
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
if [[ "$variant" == freq_serial && "$override" == 1 ]]; then
  printf 'freq_serial implements only production DATA_WIDTH=16 at SPC=1\n' >&2
  exit 2
fi
if [[ "$variant" == time_opt ]]; then
  if [[ "$override" == 1 ]]; then
    printf 'time_opt implements only production DATA_WIDTH=16 at SPC=1\n' >&2
    exit 2
  fi
  depth="${depth:-1}"
  if [[ ! "$pes" =~ ^[0-9]+$ || ! "$depth" =~ ^[0-9]+$ ]]; then
    printf 'time_opt needs its row: --systolic-pes S (4 for T-S4P1, 8 for T-S8P1), --pipeline-depth 1\n' >&2
    exit 2
  fi
  # One build directory per row, so the two rows never share a binary.
  BUILD_DIR="$BUILD_DIR/S${pes}P${depth}"
elif [[ -n "$pes" || -n "$depth" ]]; then
  printf -- '--systolic-pes and --pipeline-depth apply only to time_opt\n' >&2
  exit 2
fi
if [[ -n "$period" ]] && ! awk -v p="$period" 'BEGIN { exit !(p ~ /^[0-9]+(\.[0-9]+)?$/ && p > 0) }'; then
  printf -- '--clock-period-ns must be a positive number of ns, got %s\n' "$period" >&2
  exit 2
fi
if [[ -n "$netlist" ]]; then
  if [[ -z "$vector_dir" || -z "$cell_models" ]]; then
    printf -- '--netlist needs --vectors and --cell-models (the Sky130 Verilog models directory)\n' >&2
    exit 2
  fi
  for model in "$netlist" "$cell_models/primitives.v" "$cell_models/sky130_fd_sc_hd.v"; do
    if [[ ! -f "$model" ]]; then printf 'Missing gate-level source: %s\n' "$model" >&2; exit 1; fi
  done
  # Gate-level builds never share the RTL binary of the same row.
  BUILD_DIR="$BUILD_DIR/gl-${period:-10}ns"
elif [[ -n "$cell_models" ]]; then
  printf -- '--cell-models applies only to --netlist\n' >&2
  exit 2
fi
mkdir -p "$BUILD_DIR"
if [[ -z "$vector_dir" && ( "$variant" == time_serial || "$variant" == time_opt ) ]]; then
  vector_dir="$BUILD_DIR/fixture-canonical"
  "${PYTHON:-python3}" "$ROOT/sim/python/tests/rtl_filter_fixture.py" \
    --output "$vector_dir" --frame canonical --variant "$variant"
elif [[ -z "$vector_dir" && "$variant" == freq_serial ]]; then
  # The committed rtl_matching vectors of F-serial (T33): metadata in rtl_matching/, payloads in fxp_expected/.
  "${PYTHON:-python3}" "$ROOT/sim/python/tests/rtl_matching_stage.py" \
    --variant F-serial --output "$BUILD_DIR/matching" >/dev/null
  vector_dir="$BUILD_DIR/matching/canonical-none"
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
if [[ "$variant" == freq_serial ]]; then
  sources+=("$ROOT/rtl/common/rrc_freq_pkg.sv" "$ROOT/rtl/common/rrc_freq_engine.sv")
elif [[ "$variant" == time_opt ]]; then
  defines+=(-D TIME_OPT_DUT -D "SYSTOLIC_PES=$pes" -D "PIPELINE_DEPTH=$depth")
elif [[ "$variant" == freq_opt ]]; then
  defines+=(-D RRC_TRANSPORT_DUT)
  sources+=("$ROOT/rtl/common/rrc_stream_shell.sv")
fi
if [[ "$variant" == freq_* ]]; then defines+=(-D FREQ_DUT); fi
if [[ "$variant" == freq_serial ]]; then defines+=(-D FREQ_SERIAL_DUT); fi
if [[ -n "$period" ]]; then defines+=(-D "CLK_PERIOD_NS=$period"); fi
dut_sources=("${sources[@]}" "$ROOT/rtl/$variant/${variant}_filter.sv")
if [[ -n "$netlist" ]]; then
  # Functional cell models; the 0.1 ns flop delay keeps every register update
  # after the testbench samples at the clock edge and before its +1 ns checks.
  defines+=(-D GATE_LEVEL -D FUNCTIONAL -D "UNIT_DELAY=#0.1")
  dut_sources=("$ROOT/rtl/common/rrc_pkg.sv" "$cell_models/primitives.v" "$cell_models/sky130_fd_sc_hd.v"
               "$(realpath "$netlist")")
fi
iverilog -g2012 -Wall "${defines[@]}" -I "$vector_dir" \
  -s rrc_stream_tb -o "$BUILD_DIR/sim.out" \
  "${dut_sources[@]}" "$ROOT/rtl/tb/rrc_stream_tb.sv"
# --capture <file>: the TB writes the continuous run's captured outputs there.
plusargs=("+vector_dir=$vector_dir")
if [[ -n "$capture" ]]; then
  mkdir -p "$(dirname "$(realpath -m "$capture")")"
  plusargs+=("+capture_file=$(realpath -m "$capture")")
fi
# --vcd <file> (freq_serial): ports and engine control state over the unstalled run.
if [[ -n "$vcd" ]]; then
  if [[ "$variant" != freq_serial ]]; then printf -- '--vcd applies only to freq_serial\n' >&2; exit 2; fi
  # Both open the simulator's single VCD dump.
  if [[ -n "$activity" ]]; then printf -- '--vcd and --activity-vcd cannot be combined\n' >&2; exit 2; fi
  mkdir -p "$(dirname "$(realpath -m "$vcd")")"
  plusargs+=("+vcd_file=$(realpath -m "$vcd")")
fi
if [[ -n "$activity" ]]; then plusargs+=("+activity_vcd=$(realpath -m "$activity")"); fi
vvp "$BUILD_DIR/sim.out" "${plusargs[@]}"
