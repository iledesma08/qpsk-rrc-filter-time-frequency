# openlane — PPA target runs

OpenLane 2 Classic configurations and the pipeline that turns them into the
PPA target runs of the six-architecture matrix
(`docs/contracts/ppa-matrix-18.md`). T41 (#52) ran the time lane: three rows,
each at its main and its secondary target.

| Row | RTL | Main target | Secondary target |
| --- | --- | --- | --- |
| `T-serial` | `rtl/time_serial/time_serial_filter.sv` | SLOW 10 MHz | FAST 100 MHz |
| `T-S4P1` | `rtl/time_opt/time_opt_filter.sv`, `SYSTOLIC_PES=4`, `PIPELINE_DEPTH=1` | FAST 100 MHz | SLOW 10 MHz |
| `T-S8P1` | `rtl/time_opt/time_opt_filter.sv`, `SYSTOLIC_PES=8`, `PIPELINE_DEPTH=1` | FAST 100 MHz | SLOW 10 MHz |

The frequency lane (T43, #54) can reuse the pipeline by adding its rows to
`ppa_runs.json`.

| File | Role |
| --- | --- |
| `<variant>/config.json` | One config per top-level variant: the DUT sources, the main target (`CLOCK_PERIOD` and its SDC) and relative sizing at `FP_CORE_UTIL` 55 |
| `sdc/sky130_10MHz.sdc`, `sdc/sky130_100MHz.sdc` | The SDC template of each target; identical except the period |
| `ppa_runs.json` | The run table: rows (config, synthesis parameters, main target, serial reference), targets, sizing, signoff corners and activity workload |
| `scripts/annotated_power.tcl` | OpenSTA after the flow: unannotated power, power with the run's activity, and the pin list for the coverage |
| `sim/python/tests/ppa_stage.py` | The pipeline: `run`, `collect`, `unrun`, `rows` |
| `sim/python/tests/ppa_activity.py` | Turns the gate-level activity window into SAIF |

## Running

Needs the OpenLane 2.3.10 checkout of `docs/contracts/openlane-env-19.md`
(`~/openlane2`, Nix, volare PDK) and Icarus. From the repository root:

```bash
python3 sim/python/tests/ppa_stage.py run --row T-S8P1 --target FAST     # flow, in .build/ppa/T-S8P1/fast
python3 sim/python/tests/ppa_stage.py collect --row T-S8P1 --target FAST # gate level, activity, power, evidence
python3 sim/python/tests/ppa_stage.py unrun --row T-serial --target FAST --reason "..."
python3 sim/python/tests/ppa_stage.py rows                               # rows.json/rows.csv with the deltas
python -m pytest sim/python/tests/test_ppa_time.py -v
```

- **Order.** Run one target at a time. Parallel runs share the CPUs and
  distort the recorded runtimes. `run` deletes and redoes
  `.build/ppa/<row>/<target>/`, and `collect` needs that run's `run.json`.
- **Options.** `--openlane-dir` points somewhere other than `~/openlane2`;
  `--keep-vcd` keeps the gate-level VCD after the SAIF is written.
- **Running a config directly** (`openlane ... openlane/time_opt/config.json`)
  runs its main target. For `time_opt` without `SYNTH_PARAMETERS` that
  elaborates the RTL default, `S=8`.

## How a target run works

### Only the clock changes

A target run is the row's config plus four `-c` overrides: `CLOCK_PERIOD`, the
PnR and signoff SDC and, for `time_opt`, `SYNTH_PARAMETERS` (`SYSTOLIC_PES`,
`PIPELINE_DEPTH`). That gives one source, one `DESIGN_NAME` and one row per
synthesis.

The two SDC files differ only in `create_clock -period`, which a test checks.
Between the two targets of a row the RTL, synthesis parameters, flow, PDK and
sizing rule stay the same, and synthesis, placement and routing are redone at
each target (ppa-matrix-18, Measurement Conditions and Clock Policy).

### Sizing

Each config asks for relative sizing at 55 % core utilization. `run` first runs
the flow up to `OpenROAD.Floorplan` and reads the sized die. A side under the
200x200 um floor of the small-design PDN lesson (openlane-env-19) gets an
absolute die of `max(sized, 200)` per side. The evidence records the sized die,
whether the floor applied, and the final die, core and utilization.

### Timing signoff

A run meets its target when setup and hold slack are non-negative at the three
typical corners, `nom/min/max_tt_025C_1v80`. OpenLane's own checkers gate the
same corners for sky130 (`TIMING_VIOLATION_CORNERS = ["*tt*"]`).

- **fmax** comes from the worst setup slack at those corners:
  `1000 / (CLOCK_PERIOD - WS)` MHz.
- **The ss and ff corners** are recorded per corner as diagnostics and do not
  gate. No `P=1` prototype of T40 reached 100 MHz at ss, and every row of both
  lanes has to use the same rule.
- **Power** is reported at `nom_tt_025C_1v80`.

### Gates

A run is `passed` when the flow completes and three gates hold:

- **Timing:** met at the target, as above.
- **Physical signoff:** zero DRC errors (magic, KLayout and detailed routing)
  and zero LVS errors.
- **Gate-level vector matching:** the final netlist passes the shared
  testbench at the run's period.

A run that misses a gate is `failed`, with its reasons. A target run that was
not executed is `unrun`, with the reason. Every run stays in the table,
whatever its status.

### Antenna: recorded, not gated

⚠️ This deviates from ppa-matrix-18, whose Ranking Rule includes antenna in
physical signoff. The lane owner approved the deviation on 2026-10-18 and left
antenna to the T41 timing review (@AndresCesana, owner of T44 #55).

Every run still records its post-route antenna check:
- the count of violating nets in the row;
- each net with its layer, partial and required area and ratio in
  `evidence_manifest.json`;
- OpenLane's `antenna_summary.rpt`.

The flow is the Classic default: `GRT_ANTENNA_ITERS` 3, `GRT_ANTENNA_MARGIN`
10 %. That repair works on the global-routing estimate, detailed routing then
lengthens some nets, and no repair runs after detailed routing. Stronger
uniform repair did not converge on scratch runs:

| Trial | Result |
| --- | --- |
| Margin 20 | One net left in `T-serial` SLOW |
| Margin 50, all six runs | Cleared `T-serial` SLOW and reduced `T-serial` FAST (3 to 1) and `T-S8P1` SLOW (3 to 2); `T-S4P1` SLOW and `T-S8P1` FAST went from 0 to 1 net and `T-S4P1` FAST from 1 to 2 |
| Margin 80 | Two nets left in `T-S8P1` SLOW, with 774 diodes |
| Heuristic diode insertion | 2.5-3.4k diodes (+12-13 % cell area), one net left in `T-S8P1` SLOW |

### Activity and annotated power

OpenLane's `power.rpt` never reads activity, so power is measured again after
the flow.

**The simulation.** The final netlist (`final/nl`) runs on `rrc_stream_tb.sv`
with the Sky130 functional cell models, at the run's period, on the canonical
frame of the row's `rtl_matching` vectors (`rtl/tb/README.md`). That one
simulation gives three things:
- **Gate-level vector matching:** the continuous, mid-traffic-reset and robust
  runs pass, and the captured outputs hash to the expected codes.
- **The row's identity:** the measured `II` is `8/S`.
- **The activity window:** the continuous run, from its first cycle to the
  negedge after its last output. It holds whole cycles, every input and output
  of the frame, and no reset.

**From VCD to power.** `ppa_activity.py` streams the window into SAIF
(`activity.saif.gz`): per pin, the time at 0, 1 and X and the transition count.
`annotated_power.tcl` reads it with OpenSTA `read_saif` at the power corner,
with the same netlist, SPEF, liberty and SDC as OpenLane's post-PnR STA.

The VCD is not read directly because OpenSTA 2.6.0 measures a VCD from time 0,
so the reset before the window would count as idle time, and `read_vcd` has no
window option. As a cross-check, the same window rewritten to start at time 0
is read with `read_vcd`. Both reads must give the same power, and OpenSTA's
`Annotated <n> pin activities` must equal the pins in the SAIF.

**Coverage** is annotated pins over every netlist pin and port. It leaves out
the liberty internal pins of the flops (`IQ`, `IQ_N`): they are not netlist
ports, so no simulation can annotate them. Power counts as `annotated` from
95 % coverage with an agreeing cross-check, and as `partially-annotated`
otherwise. The same script first reproduces OpenLane's unannotated power, which
stays in the evidence for comparison.

### Throughput, energy and deltas

- **Throughput** is `f / II` valid outputs per second (`SPC = 1`), with the
  `II` measured on the netlist.
- **Energy per valid output** is the annotated total power divided by that
  throughput. The total includes the core and the clock tree; this design has
  no pad or macro power.
- **Deltas.** `rows` compares each optimized row with `T-serial` at the same
  target only. A pair is `comparable` when both runs passed every gate with
  the same OpenLane version, PDK and SDC, and `not-comparable` with the reason
  otherwise.
  - Each delta is candidate minus serial, as an absolute value and as a
    percentage. Higher throughput is better; lower cell area and lower energy
    per output are better.
  - The energy delta also needs annotated activity on both sides.
  - The Pareto ranking and the delivery claim belong to T44 (#55).

### Evidence

Per run, in `sim/python/artifacts/t41-time-ppa/<row>/<slow|fast>/`:

- **`evidence_manifest.json`** records:
  - the run command and its overrides;
  - sizing, wall time and peak memory;
  - timing per corner and the signoff counts, including the antenna nets;
  - the gate-level result and the activity window;
  - power and coverage;
  - the hashes of the DUT sources, the SDC and the config;
  - the run's normalized row.
- **OpenLane files of the contract:**
  - `resolved.json`;
  - `final/metrics.json` and `metrics.csv`, or `last-state/metrics.json` when
    the flow ends with deferred errors (see Learning);
  - `openroad-stapostpnr/summary.rpt`;
  - the per-corner `max/min/checks/power.rpt`.
- **D1, compressed reports.** `max.rpt` and `min.rpt` are committed byte for
  byte, gzip-compressed (`max.rpt.gz`). The manifest keeps the SHA-256 of each
  uncompressed report. Uncompressed they are 4-7 MB per corner, about 540 MB
  for the six runs; compressed, about 30 MB. This deviation was approved by
  the lane owner on 2026-10-18. openlane-env-19 still lists the uncompressed
  names.
- **The post-route antenna check:**
  `openroad-checkantennas/antenna_summary.rpt`.
- **Power:**
  - `power/` holds the unannotated, annotated and cross-check reports and the
    `run.tcl` that produced them;
  - `activity.saif.gz` holds the activity.

The OpenLane logs sit next to the evidence and stay out of git (`*.log`).
`rows.json` and `rows.csv` hold the normalized rows with the deltas.

## Results (T41)

All six target runs use the RTL of the T31/T40 vector matching (equal source
hashes) and the default Classic flow. Power is at `nom_tt_025C_1v80` with
annotated activity: 100 % pin coverage in every run, with an agreeing
cross-check. Throughput is `f / II` at the target clock, which a run that
misses timing does not reach.

| Run | Role | Status | Worst tt setup WS (ns) | fmax tt (MHz) | Cell area (um²) | Util | II | Throughput (MS/s) | Power (mW) | Energy/output (nJ) | Antenna nets |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T-serial SLOW | main | passed | +87.614 | 80.7 | 47,035.1 | 0.494 | 8 | 1.25 | 0.550 | 0.440 | 3 |
| T-serial FAST | secondary | failed: timing | -0.858 | 92.1 | 49,990.4 | 0.525 | 8 | 12.5 | 5.879 | 0.470 | 3 |
| T-S4P1 SLOW | secondary | passed | +87.957 | 83.0 | 67,811.3 | 0.510 | 2 | 5 | 0.947 | 0.189 | 0 |
| T-S4P1 FAST | main | failed: timing | -0.560 | 94.7 | 71,702.5 | 0.539 | 2 | 50 | 9.722 | 0.194 | 1 |
| T-S8P1 SLOW | secondary | passed | +88.980 | 90.7 | 69,870.8 | 0.493 | 1 | 10 | 0.868 | 0.087 | 3 |
| T-S8P1 FAST | main | passed | +0.023 | 100.2 | 72,927.4 | 0.514 | 1 | 100 | 8.878 | 0.089 | 0 |

Every run has zero DRC and zero LVS errors, and every gate-level run matched
the canonical frame with `II = 8/S` and the declared latency.

### Main goals

- **`T-serial` SLOW: met**, with about 88 ns of setup slack.
- **`T-S8P1` FAST: met**, by +0.023 ns at the worst typical corner.
- **`T-S4P1` FAST: failed**, by -0.56 ns (about 94.7 MHz). It stays a failed
  main goal: the DoD of #52 lets only the DUT list, top, factors, die and
  clock change per row, so neither the RTL nor the flow was tuned for it.
  - **Cause.** All 60 violating paths start at the `slot` counter. About
    1.5 ns of each is the fanout tree that counter drives to select the
    operands of the four PEs, ahead of the 35-bit add and the cast. `T-S8P1`
    has a single slot and no slot multiplexer.
  - **Scratch trials.** A uniform `SYNTH_STRATEGY "DELAY 0"` closed it
    (+0.60 ns) at +55 % cell area; `RUN_POST_GRT_RESIZER_TIMING` gained only
    0.11 ns.

### Other observations

- **Timing.** `T-serial` misses FAST by 0.86 ns. Hold is met in every run,
  with at least +0.345 ns.
- **Antenna.** Four runs keep one to three residual nets, with ratios up to
  1.72. Every net is on met1 except one met3 net in `T-serial` SLOW, whose
  1.00 is 401.68/400 rounded.
- **Synthesis.** At Yosys's ALUMACC pass the serial filter keeps two
  multipliers and both systolic rows keep eight (four distinct constant
  products per component), as #51 found.
- **Sizing.** No sized die was under the 200x200 um floor.

### Comparisons

Both SLOW pairs are `comparable` in `rows.json`. The FAST pairs are
`not-comparable` because `T-serial` FAST misses timing.

| SLOW pair, candidate minus `T-serial` | Throughput | Cell area | Energy per output |
| --- | ---: | ---: | ---: |
| `T-S4P1` | +3.75 MS/s (+300 %) | +20,776 um² (+44.2 %) | -0.250 nJ (-56.9 %) |
| `T-S8P1` | +8.75 MS/s (+700 %) | +22,836 um² (+48.6 %) | -0.353 nJ (-80.3 %) |

Both pairs depend on the antenna deviation. Under the ppa-matrix-18 rule,
`T-serial` SLOW and `T-S8P1` SLOW would fail on antenna, and without a passing
serial reference neither pair would be comparable.

## Runtime and capacity

Every run used one machine: WSL with 4 CPUs and 7.8 GiB.

- **Pilot.** The pilot was `T-S8P1` FAST, the largest row at the tighter
  target. It took 18.8 min plus a 50 s floorplan pre-pass. Two more runs with
  identical inputs gave identical metrics in 13.4 and 19.6 min, so runtime
  varies by about ±30 % here.
- **Memory.** OpenLane's step statistics round peak memory to "1GiB"; `time -v`
  measured 1.5 GiB for the largest process.
- **Rounds.** All six runs were executed three times:
  1. with the default flow;
  2. with the antenna margin 50 trial;
  3. with the default flow again, for the final evidence.
- **Final round.** It reproduced the first round's timing, area, power and
  antenna counts. It took 69 min of flow (8 to 17 min per run) plus 4 min of
  floorplan pre-passes.
- **Gate-level simulations.** They take 25 to 183 s each. Their window VCDs
  are 56 to 286 MB and are not kept.

## Learning

- **OpenLane only globs inside the design directory.**
  `dir::../../rtl/<variant>/*.sv` fails with "not located any path readable to
  OpenLane", while a named file outside it is fine. The time configs now name
  their filter source; the frequency configs still use the glob (T43).
- **A flow that ends with deferred errors writes no `final/`.** Setup
  violations at the typical corners are such an error. Every step still runs,
  including DRC and LVS. The last step's `state_out.json` holds the metrics and
  views. The evidence keeps those metrics as `last-state/metrics.json`, never
  under the contract's `final/` paths.
- **OpenLane's unannotated power underestimates the datapath.** Its default
  activity barely reaches the combinational logic. `T-S8P1` FAST reports
  4.91 mW without activity, 6 uW of it combinational, against 8.88 mW with the
  gate-level window, 3.34 mW of it combinational.
- **OpenSTA 2.6.0 activity details.**
  - `read_vcd` averages over the time from 0.
  - `read_saif` reads only entries inside `(NET ...)` sections, so the SAIF
    lists each cell's ports there, and prints no count.
  - `get_pins` also lists the liberty internal pins `IQ`/`IQ_N` of each flop.
  - Escaped netlist names such as `\x_q[9]` are not valid SAIF identifiers
    and are left out. They are nets, while OpenSTA annotates pins, so coverage
    does not drop.
- **S=4 closes worse than S=8 at FAST.** The slot multiplexer sits on the
  product path. After routing the worst typical slack is -0.56 ns for `S=4`
  and +0.02 ns for `S=8`, in the same order as the T40 pre-route margins
  (+0.37/+0.58 ns).
- **The serial filter is not small.** Two generic 16x16 multipliers, an
  8x32-bit history with its multiplexers and the 35-bit accumulators take
  47-50k um², against 68-73k um² for the systolic rows.
- **Antenna repair works on estimates.** The global-routing repair cannot see
  a net that detailed routing later stretches. A larger margin buys more
  diodes, not certainty.
- **The flow is deterministic here.** Runs with the same inputs gave identical
  metrics; only the runtime moved.
- **`STA-0441`.** The SDC template's `set_input_delay ... [all_inputs]` also
  hits the clock port. OpenSTA warns and ignores that one delay.
