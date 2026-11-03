# rtl/time_opt — time-domain filter, optimized version

T40 (#51) rows `T-S4P1` and `T-S8P1` of the base matrix
(`docs/contracts/ppa-matrix-18.md`): `S=4` or `S=8` tap PEs at pipeline depth
`P=1`, `SPC=1`, `II = 8/S` (2 and 1). Both rows come from one source,
`time_opt_filter.sv`, and differ only in the `SYSTOLIC_PES` parameter. Run the
structural canonical frame on both rows from the repository root:

```bash
bash rtl/time_opt/run.sh                        # T-S4P1 then T-S8P1
bash rtl/time_opt/run.sh --systolic-pes 4       # one row
python -m pytest sim/python/tests/test_rtl_time_opt.py -v
```

Vector matching against the committed `rtl_matching` vectors (canonical and
the three `sys_corners`, see [Vector matching](#vector-matching)):

```bash
python sim/python/tests/rtl_matching_stage.py --variant T-S8P1
bash rtl/time_opt/run.sh --systolic-pes 8 --pipeline-depth 1 \
  --vectors .build/rtl/matching/T-S8P1/canonical-none
python -m pytest sim/python/tests/test_rtl_time_opt_matching.py -v
# Evidence: run every frame of a row with capture
python sim/python/tests/rtl_matching_stage.py --variant T-S4P1 \
  --evidence-dir sim/python/artifacts/t40-time-opt-matching/T-S4P1
python sim/python/tests/rtl_matching_stage.py --variant T-S8P1 \
  --evidence-dir sim/python/artifacts/t40-time-opt-matching/T-S8P1
```

## Design

The serial filter (T30) keeps the last eight samples and walks one MAC over
them. This filter keeps the *sums* instead of the samples: each accepted sample
is broadcast to every tap, each tap adds its product to the sum the next tap
left one sample earlier, and the finished sum falls out of tap 0. That is the
transposed form of the FIR, folded onto `S` processing elements (Parhi's
systolic design B1: broadcast input, moving results, fixed weights).

- **State:** `x_reg` holds the accepted `x[n]` (packed `{Q,I}`) and
  `partial_*[k]` holds `s[k]`, the sum of taps `k..7` that the next sample still
  needs, for `k = 1..7`, I and Q, each 35 bits. Nothing else is stored.
- **Taps:** tap `k` computes `s[k] = c[k]*x[n] + s[k+1]` (tap 7 has no
  `s[8]`), and tap 0 closes `y[n] = c[0]*x[n] + s[1]`.
- **Schedule:** tap `k = t*S + p` runs in slot `t` on PE `p`, so the eight taps
  take `8/S` slots. For `S=4`:

  | Slot | PE 0 | PE 1 | PE 2 | PE 3 |
  | --- | --- | --- | --- | --- |
  | 0 | `y = c0*x + s1` | `s1 = c1*x + s2` | `s2 = c2*x + s3` | `s3 = c3*x + s4` |
  | 1 | `s4 = c4*x + s5` | `s5 = c5*x + s6` | `s6 = c6*x + s7` | `s7 = c7*x` |

  `S=8` runs the whole table in one slot. Slots run in ascending order, so every
  tap reads the `s[k+1]` of the previous sample before this sample overwrites
  it. Block assignment (`k = p*M + t`) breaks that order and fails the tests.
- **Throughput and latency:** the next sample is accepted on the edge of the
  last slot, so `II = 8/S`. The accept edge loads `x_reg` and the next edge
  runs slot 0 and loads the output, so the first output appears 2 cycles after
  its input for both rows (`latency_cycles=2`, asserted by the TB) with one
  output per accepted input (`latency_samples=0`).
- **Output and backpressure:** a two-entry output buffer. Slot 0 runs only
  while an entry is free. Under a sink stall both entries fill and the next
  sample waits at slot 0 with `ready_o` low. Under continuous traffic one
  result enters and one leaves per cycle, so `S=8` keeps `II=1`. With a single
  output register, `ready_o` would have to depend on `ready_i` to reach `II=1`.
- **Control paths:** `ready_o` and `valid_o` come only from registers (`busy`,
  the slot counter, the buffer flags), so neither depends combinationally on
  `valid_i` or `ready_i`. The state advances only on an accepted input, so
  bubbles and stalls change nothing.
- **Reset:** one `rrc_reset_sync` instance; every register (sample, partial
  sums, slot counter, both output entries) uses the synchronized reset.
- **Coefficients:** the same `rrc_pkg` table and cast as T30. Each tap has
  one constant product of `x_reg`, and a PE selects products, never
  coefficients: a coefficient multiplexer would turn the constant multipliers
  into generic ones. Taps with the same coefficient (`c[k] = c[7-k]`) give
  identical products that synthesis may merge. In the #51 synthesis check both
  rows kept 8 multipliers, four distinct constant products per component; every
  T41 target run confirms it at Yosys's ALUMACC pass (`openlane/README.md`).
- **Parameters:** only `SYSTOLIC_PES` 4 or 8 with `PIPELINE_DEPTH` 1, production
  `DATA_WIDTH=16` and `SPC=1` elaborate. Anything else stops at elaboration
  (`S=1`/`S=2` and `P=2` are extension rows). The datapath is written for any
  `S` that divides 8. The `S=1` and `S=2` schedules were checked on the scratch
  prototype of the #51 analysis; an extension row needs the guard relaxed and
  its own matching. The module defaults (`S=8`, `P=1`) only let lint and the
  OpenLane source list elaborate; every run sets both. `CAST_REGISTER` (0 by
  default, which is the base rows) is 0 or 1; see
  [the registered-cast variant](#proposed-variant-t-s4p1-c-registered-cast).

Numerics are the accepted time policy (`docs/contracts/fxp-policy-16.md`):
Q2.14 data and coefficients, 32-bit products, a 35-bit accumulator and one RNE
plus saturation cast after the full sum. The one difference from T30 is the
order of the additions: each output adds its eight products as `k = 7..0`
instead of `0..7`. The *Time accumulation-order clarification* of
`fxp-policy-16.md` (#51) records why this is exact. Every partial sum of any
subset of products fits the 35-bit accumulator
(`2^15 * sum|c| = 990248960 < 2^34`, checked at elaboration as in T30), and
integer addition without overflow does not depend on the order. The P=1 cut
therefore keeps the same rounding and saturation (open item of
`ppa-matrix-18.md`).

## Proposed variant T-S4P1-C (registered cast)

`T-S4P1` misses FAST 100 MHz after routing by -0.56 ns (T41,
`openlane/README.md`). Its critical path runs in one cycle from the `slot`
counter through the operand selection of the four PEs, the 35-bit tap-0 add,
the RNE/saturating cast and the output buffer into `sample_o`. `T-S4P1-C`
(#55) is a proposal, not a base row of `ppa-matrix-18.md`: the same source
with `CAST_REGISTER=1`, which cuts that path after the add.

- **What is registered:** `y_acc_i`/`y_acc_q` take the full-precision 35-bit
  `y[n]` of tap 0 on the slot-0 edge, with a valid flag `y_valid`. The cast
  reads that register one edge later, and its Q2.14 result goes into the
  two-entry output buffer on that edge. The slot-0 path now ends at a register
  after the add, like the paths into `partial_*[k]` already did. The cast and
  the buffer get a cycle that starts at a register.
- **Unchanged:** the sums, the single cast after the full sum, the widths, the
  schedule, `II = 8/S` and the streaming interface. The outputs are bit-exact
  with `T-S4P1` and `T-serial` on every frame.
- **Latency:** the accept edge loads `x_reg`, the slot-0 edge loads `y_acc` and
  the next edge loads the output, so the first output appears 3 cycles after
  its input (`latency_cycles=3`, `latency_samples=0`). The TB asserts it. The
  F3 manifests declare it (`rtl_matching/T-S4P1-C`).
- **Backpressure:** slot 0 runs only while `y_acc` is empty or its result
  moves into the buffer on the same edge (`!y_valid || !out_full`). `y_acc`
  moves only while an entry is free. Under a sink stall the filter therefore
  holds three results (the cast register and both buffer entries), the next
  sample waits at slot 0 with `ready_o` low, and nothing is lost or
  duplicated. Under continuous traffic the result in `y_acc` moves into the
  buffer on the same edge that the next `y[n]` enters it, so the II stays
  `8/S`.
- **Control paths:** `ready_o` and `valid_o` still come only from registers
  (`busy`, `slot`, `y_valid`, the buffer flags).
- **Reset:** `y_acc` and `y_valid` use the synchronized reset like every other
  register.
- **Cost:** 71 more flops (2 x 35 bits plus the flag) and one cycle of latency.
- **Base rows:** with `CAST_REGISTER=0` the generate block elaborates the
  T40 expressions unchanged. The runner names the parameter only when
  `--cast-register` is given, so the base rows build and report as before.

Running it (structural fixture, vector matching and evidence):

```bash
bash rtl/time_opt/run.sh --systolic-pes 4 --pipeline-depth 1 --cast-register 1
python sim/python/tests/rtl_matching_stage.py --variant T-S4P1-C \
  --evidence-dir sim/python/artifacts/t40-time-opt-matching/T-S4P1-C
```

`test_rtl_time_opt.py` runs every structural check on `T-S4P1-C` too, with
latency 3 and three stored results under the sink stall. It also checks the
cast register under reset, the `CAST_REGISTER` elaboration guard and the
runner's `--cast-register` checks. `test_rtl_time_opt_matching.py` matches its
four frames and refuses a run that drops the register: that run has the
latency of `T-S4P1`. Evidence:
`sim/python/artifacts/t40-time-opt-matching/T-S4P1-C/evidence_manifest.json`.
It has 4/4 frames PASS, 8220 compared codes, latency 3 and `II` 2, with
captures equal to the `T-serial` ones.

FAST 100 MHz result. This is a proposal run: `T-S4P1` with
`CAST_REGISTER=1`, under the same conditions as the T41 run (same config, SDC,
sizing rule, default Classic flow). It is not in `openlane/ppa_runs.json`. Its
evidence, collected with `ppa_stage.py` like a T41 row, is
`sim/python/artifacts/t41-time-ppa/T-S4P1-C/fast/evidence_manifest.json`. The
`T-S8P1-C` FAST run (+1.858 ns, 83,911.7 um², not collected) is in
`sim/python/artifacts/timing-closure/time/T-S8P1-C-fast/`, and the summary of
#91 is `docs/research/timing-closure-summary.md`.

| Run | Worst tt setup WS (ns) | fmax tt (MHz) | Cell area (um²) | Util | Power (mW) | Energy/output (nJ) | Antenna nets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `T-S4P1` FAST (T41) | -0.560 | 94.7 | 71,702.5 | 0.539 | 9.722 | 0.194 | 1 |
| `T-S4P1-C` FAST | +1.556 | 118.4 | 78,380.2 (+9.3 %) | 0.562 | 10.202 (+4.9 %) | 0.204 | 1 |

- **Timing:** met at all three tt corners (TNS 0). Hold is met (+0.354 ns),
  DRC and LVS are 0, and the flow writes `final/`.
- **Critical path:** it now runs from `x_reg` through the constant products
  and the 35-bit add into a partial sum (`s[4]`) or `y_acc`. That is 7.2 ns of
  logic after 1.0 ns of clock-to-Q and fanout. The cast path
  (`y_acc` to the output buffer) has at least +4.96 ns of slack, and the
  `slot` paths +6.5 ns.
- **Gate level:** the final netlist matches the canonical frame (2055 codes,
  latency 3, `II` 2).
- **Power:** at `nom_tt` with SAIF activity at 100 % coverage.
- **ss corner:** a diagnostic only. It improves from -10.45 to -6.28 ns but
  is still not met.
- **Area:** besides the 71 flops, the resizer adds repair buffers (536
  against 386).

## Why this architecture

Recorded from the #51 analysis. It ran scratch prototypes, not this file,
through OpenLane up to CTS (pre-route, 50% utilization, the repository's
100 MHz SDC). Those numbers are indicative and are not PPA evidence.

- **Direct form with an adder tree (Parhi F).** It keeps T30's sample history,
  so it is the closest to the serial filter. Its critical path grows with `S`
  (multiplier, tree, cast). On the prototypes it missed 10 ns at the typical
  corner on both rows (worst slack about -2.3 to -2.8 ns). The transposed form
  closed with +0.5 ns (`S=4`) and +1.8 ns (`S=8`). The prototype areas were
  close: transposed 74k/80k um², direct 59k/88k um² for `S=4`/`S=8`.
- **Classic systolic array (Parhi W1/W2/R1/R2), with the input registered
  through the PEs.** If it advances only on accepted samples, `y[n]` needs
  later samples to come out, which means more than seven flush zeros and an
  amendment of `rtl-streaming-17.md`. If it advances every cycle, a bubble
  enters as a zero sample. Neither fits the contract.
- **Results that stay in place (Parhi B2).** Every PE sees all eight
  coefficients and needs eight accumulators, so it is dominated by B1.
- **Slow corner.** At the slow corner (`nom_ss_100C_1v60`) no prototype reached
  100 MHz with `P=1` (transposed about 55/62 MHz, direct about 40/42 MHz).
  Registering the cast gained less than 1 ns at the typical corner on these
  pre-route prototypes, so the base rows do not have it. After routing it is
  what closes `T-S4P1` at FAST (the proposed variant above). T41 signs off at
  the typical corners and reports ss as a diagnostic (`openlane/README.md`).
- **This file through the same flow.** Both rows closed 10 ns at the typical
  corner, with worst slack +0.37 ns (`S=4`) and +0.58 ns (`S=8`) and post-CTS
  areas of 74k and 75k um². That is less margin than the `S=8` prototype had,
  and routing parasitics are not included yet. The critical path still runs
  from `x_reg` through a constant multiplier, the tap-0 add and the cast into
  the output register.

## Verification (structural)

`test_rtl_time_opt.py` runs every check on both rows:

- the five T30 structural frames from `rtl_filter_fixture.py` (canonical, the
  impulse, RNE ties, saturation, 64 arbitrary codes) against the exact integer
  reference, continuous (latency 2, `II = 8/S`) and robust (bubbles, stalls, a
  mid-traffic reset);
- byte-identical captures from T-serial, T-S4P1 and T-S8P1 on the RNE-tie,
  saturation and arbitrary frames, the only ones that exercise the cast;
- a 40-cycle sink stall that fills both output entries, holds the output
  stable, accepts no fourth sample, and resumes at `II = 8/S` with no loss or
  duplicate;
- no combinational path from `valid_i` or `ready_i` to the outputs;
- synchronized reset release, and a reset that clears nonzero partial sums
  in the middle of a computation;
- elaboration rejects `SYSTOLIC_PES` 1, 2, 3 and 16, `PIPELINE_DEPTH` 0 and 2,
  width 8 and `SPC` 2;
- the runner rejects width/`SPC` overrides, a run without its row, the row
  options on other variants, and `--vectors`/`--capture` without a row;
- the default `bash rtl/time_opt/run.sh` covers both rows.

A scratch run of eleven mutants failed `test_rtl_time_opt.py` every time:

- block tap assignment and a backwards slot counter;
- removing RNE or saturation, or changing one coefficient (179 to 178);
- running slot 0 without a free output entry, or a single output entry;
- `ready_o` depending on `ready_i`;
- partial sums kept through reset;
- accepting on `ready_o` without `valid_i`;
- tap 7 adding its own stale sum.

## Vector matching

- **Metadata:** `gen_vectors.py --stage rtl_matching --variant T-S4P1` (and
  `T-S8P1`) writes `sim/vectors/rtl_matching/<row>/<set>/<case>/`. Each
  manifest declares `rtl_variant: time_opt` and
  `rtl_parameters: {SYSTOLIC_PES, PIPELINE_DEPTH}`, the row of this source. It
  also declares `SPC=1`, `latency_samples=0`, `latency_cycles=2`, 7 flush zeros
  and 2055 accepted and raw samples.
  - It binds the same `fxp_expected` payloads as `T-serial`: the three
    variants share the expected codes.
  - The `.svh` keeps the T03 localparams. The row lives only in the JSON and
    never uses the legacy name `S`.
- **Running a row:** `rtl_matching_stage.py` turns `rtl_parameters` into
  `--systolic-pes`/`--pipeline-depth`. The TB prints the row the instance
  elaborated.
- **Evidence:** `sim/python/artifacts/t40-time-opt-matching/<row>/evidence_manifest.json`.
  - 4/4 frames PASS per row: 8220 compared codes, latency 2, `II` 2 (T-S4P1)
    and 1 (T-S8P1).
  - It records the row, the expected `II`, the generator revision of the
    metadata, the simulator and the hashes of the RTL, TB and runner at run
    time.
  - The two rows give identical outputs and latency, so the evidence also
    requires the elaborated row to equal `rtl_parameters` and the measured
    `II` to be `8/S`. Otherwise a run of one row could be filed as the other.
  - Every continuous run captures its outputs. Their SHA-256 equals the bound
    `expected_time.hex` and the T-serial capture of the same frame (T31
    evidence), so the three variants are bit-exact on every frame.
  - The per-frame logs next to it are git-ignored and attached to the PR.

`test_rtl_time_opt_matching.py` covers:

- the 8 row/frame runs;
- a wrong declared latency (1 or 3) failing the unstalled run;
- a run without its row being refused;
- evidence refused when the runner elaborates the other row;
- the committed evidence and the cross-variant capture hashes.

## Learning

- **Folding saves different things in each form.** The transposed form
  multiplies one sample by all eight coefficients in every slot. With constant
  coefficients, folding it from `S=8` to `S=4` saves adders but not
  multipliers, so the two rows have similar area and `S=8` has twice the
  throughput. The direct form saves multipliers when folded but pays with a
  longer path.
- **The cost of the transposed form is registers.** Fourteen 35-bit partial
  sums replace eight 32-bit samples, and they change on every sample. Expect
  more flop area and clock power than the serial filter; T41 measures it.
- **Two rows with identical outputs need another signal to tell runs apart.**
  `II` is that signal here.
- **The accumulation order is a contract detail.** The ascending order of
  fxp-policy-16 is the FXP model's. Any parallel time datapath reassociates the
  sum, and the 35-bit bound is what makes that exact.
- **Icarus 11 loses the signedness of a package function result inside a
  product** (`x * rrc_pkg::rrc_coef(k)` turns unsigned). The coefficient
  therefore goes through a signed signal first, as in T30.
- **A constant full-scale input can zero a partial sum,** because
  `c[1] + c[2] = 0`. A test probe for "partial sums in use" must pick a tap
  where that cannot happen.

## Scope limits

These are functional results.

- **Physical runs:** FAST 100 MHz timing, the per-row OpenLane runs (one
  `DESIGN_NAME`, `SYNTH_PARAMETERS` per row), synthesis, activity and signoff
  are T41 (#52): `openlane/README.md` and `sim/python/artifacts/t41-time-ppa/`.
  The comparable PPA evidence belongs to #55.
- **The two PPA items of the #51 DoD,** the throughput/area/energy deltas
  against the same-domain serial row and the "improves at least one axis"
  claim, are delivered by those tasks.
- **`openlane/time_opt/config.json`** lists the sources and the FAST main
  target; without `SYNTH_PARAMETERS` its defaults elaborate T-S8P1. The run
  table `openlane/ppa_runs.json` gives each row its parameters.
- **`docs/block-diagram.md` §2** draws the time datapath as a sample history
  (the serial and direct form). The transposed form of these rows is described
  here; updating the diagram belongs to its owner (T52).
