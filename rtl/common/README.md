# rtl/common — shared time/frequency

Shared parameters and streaming control for the time and frequency lanes.

Nothing domain-specific goes here: shared logic is shared, not duplicated.

## T03 design (#42)

`rrc_pkg.sv` owns the block defaults: FFT length 16, hop 8, discard prefix 8,
emit start 8, emit length 8. Emit defaults derive from the FFT/discard parameters;
frequency wrappers validate their final tuples at simulation time zero without
implementing a block engine or activating alternate schedules.
Data width 16 and SPC 1 are interface defaults,
and width/SPC remain module parameters. Production `W_common=16` and
`F_data=F_coeff=14` (`Q2.14`) are already mandated by contract #16, not a future
width-selection decision. Widths such as 8 and 12 exercise diagnostic transport
fixtures, not production formats. T03 has no fractional arithmetic; the
numerical acceptance (T21) and the frozen production coefficient export (T22)
came later.

T30 (#47) adds the time-domain numeric policy to the package: `RRC_TAPS`,
`FRAC_BITS`, `W_PRODUCT=32`, `W_ACC_TIME=35`, the `Q2.14` coefficient table
(`RRC_COEFS`, read through `rrc_coef(k)`) and the single RNE/saturating output
cast `time_output_cast`. The table holds the Q2.14 integers listed in
`fxp-policy-16.md`, and `test_rtl_time_serial.py` checks it against the frozen
T22 export (`sim/vectors/fxp_expected/rrc8_q2.14_coefficients.json`). The
serial filter (T30) and the optimized rows T-S4P1/T-S8P1 (T40) share these
definitions, so their arithmetic stays bit-exact by construction.

`rrc_stream_shell.sv` replaces the inactive toolchain placeholder with a
one-stage elastic **transport-only** register. Only the test-only wrapper
`sim/python/tests/transport/transport_filter.sv` still uses it (the body of
`freq_opt` until T42); `time_serial` replaced it with the T30 filter,
`freq_serial` with the T32 engine, `time_opt` with the T40 filter and `freq_opt`
with the T42 engine rows.
It forwards each accepted `{Q,I}` beat unchanged, with no FIR or FFT arithmetic.
The packed bus is `[SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0]`, with I in the low
bits, Q in the high bits, and lane 0 first.

The shell accepts input when its output register is empty or its pending output
can be consumed. Backpressure holds the payload and valid flag; an idle source
allows a pending output to drain once, then clears valid.
`rrc_reset_sync.sv` asserts asynchronously and releases through two flip-flops.
Each wrapper instantiates it once and distributes `rst_sync_n` to the shell and
future F3 state; the shell consumes that reset, without a second synchronizer.
No stream transfer occurs during reset. The `async_reg` annotation documents
tool-dependent intent, not physical preservation or placement guarantees.

The interface and the scoped choice to retire placeholders in T03 rather than
F3 are recorded in `docs/contracts/rtl-streaming-17.md`. Actual filter datapaths
replace transport in F3; do not use this shell for filter matching or PPA.
The combinational backward-ready path enables same-cycle replacement in this
single entry; it is not a prescription to chain it through every future stage.
F3 chooses ready-path cuts/skid buffering using its actual timing and PPA needs.

## Learning for review

- `SPC` describes bus width, not initiation interval. This shell measures II=1;
  the future serial time filter requires II=8.
- An accepted input and a consumed output are separate events. Bubbles must not
  re-emit a stale register, and stalls must not overwrite a pending payload.
- SV part-selects need explicit signed casts before arithmetic; transporting
  packed bits itself is not arithmetic. The TB casts I/Q separately when
  sign-extending the records used for exact comparison.
- Compile the package before its consumers. Simulation, lint, and OpenLane
  source lists use that order. Simulation compiles package, reset synchronizer,
  shell, wrapper, then TB; OpenLane includes DUT/shared RTL only, never TB
  metadata or vectors.

## Frequency engine (T32, #49; T42, #53)

`rrc_freq_pkg.sv` holds the frozen production-A frequency arithmetic: the
twiddle and `H[k]` tables (generated from `sim/python/fxp.py`; `H[k]` is read
through a bit-reversed address), the container widths and the two shared
narrowing functions (RNE shift by F, and the final cast with saturation).
`rrc_freq_engine.sv` is the `U`-parameterized engine of the frequency lane:
`U` butterfly lanes, each with its own complex multiplier. `U=1` is the serial
baseline wrapped by `rtl/freq_serial/`; `U=4` and `U=8` are the F-U4 and F-U8
rows wrapped by `rtl/freq_opt/` (T42). Any other `U` stops at elaboration. All
rows share this one source instead of copies, and they are bit-exact with each
other (see `rtl/freq_opt/README.md`). They are listed after
`rrc_pkg.sv`/`rrc_reset_sync.sv` in every source list; `rrc_stream_shell.sv` is
no longer used by `freq_serial` or `freq_opt`. `rrc_freq_pkg` repeats `FFT_LEN` and `DATA_WIDTH` (the
Yosys of OpenLane cannot cross-reference packages); the engine checks them against
`rrc_pkg`. See `rtl/freq_serial/README.md`.

## Physical-target boundary

Serial main targets are SLOW 10 MHz (100 ns), with FAST 100 MHz (10 ns)
secondary; optimized main targets are FAST, with SLOW secondary. Prepare both
targets per architecture, run main goals first, and prioritize secondary runs
using measured real-filter pilot capacity. A SLOW pass cannot fulfill a failed
FAST goal; preparing twelve runs does not promise all twelve will finish.

The T03 OpenLane JSON skeletons retain `CLOCK_PERIOD=10.0` as setup, not
main-target validation or PPA rows. The TB's 10 ns simulation clock likewise
proves no physical timing. Real target-specific configurations/runs belong to
#52 (time) and #54 (frequency), real serial matching to #48/#50, and comparable
PPA evidence to #55. See ADR-0006 for the accepted target/evidence rules.

Run `bash rtl/run.sh` from the root. See `rtl/tb/README.md` for test cases,
commands, evidence and integration limitations.
