> HISTORICAL RESEARCH — not normative. Accepted decisions live in ppa-matrix-18.md / fxp-policy-16.md. See Resolution Status. Do not implement workload/OLS wording from this file.

# PPA Experiment Matrix Research

Research ticket: [#18](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/18)

Parent map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-21

Scope: research only. This note does not add RTL, OpenLane configuration,
vectors, or measurement scripts.

## Decision Summary

The smallest useful matrix after the serial baselines is **10 optimized
architectures plus the two serial baselines**:

| ID | Lane | Concrete factor | Role |
| --- | --- | --- | --- |
| T-serial | Time | Existing serial baseline | Reference for area, timing, and throughput |
| T-S2P1 | Time | S=2 systolic tap PEs, P=1 pipeline stage | Low-parallelism point |
| T-S4P1 | Time | S=4, P=1 | Mid-parallelism point |
| T-S8P1 | Time | S=8, P=1 | Full tap-array point |
| T-S2P2 | Time | S=2, P=2 pipeline stages | Pipeline effect at low parallelism |
| T-S4P2 | Time | S=4, P=2 | Balanced timing/area point |
| T-S8P2 | Time | S=8, P=2 | Timing-oriented full array |
| F-serial | Frequency | Existing serial baseline, treated as U=1 | Reference for area, timing, and throughput |
| F-U2 | Frequency | U=2 unfolded issue lanes | Low replication point |
| F-U4 | Frequency | U=4 | Mid replication point |
| F-U8 | Frequency | U=8 | Full radix-2 stage butterfly parallelism for FFT16 |
| F-F2 | Frequency | Two-fold reuse of the U=8 schedule | Area/throughput contrast |

This is a recommendation, not a fact imposed by OpenLane. The values are
chosen because 2, 4, and 8 are exact divisors of the eight-tap filter and give
three readable area/throughput points without turning the study into a sweep
of arbitrary RTL parameters.

### Factor definitions

`S` is the number of tap processing elements that can be active in one
time-domain issue group. The remaining tap groups are scheduled in later
cycles. The expected initiation interval for the recommended schedule is
`II = 8 / S` cycles per sample, before any interface bubbles. `S=8` is the fully
parallel tap-array case. The serial baseline is retained as the `S=1`
reference, but it is not duplicated in the factorial.

`P` is the pipeline depth used consistently in every time-lane processing
element. Recommended interpretation: `P=1` keeps the multiply/accumulate
operation in one registered arithmetic stage; `P=2` inserts a register between
the multiply and add portions. If the RTL team uses cut-set terminology
instead, it should map the same two levels to one and two registered cuts and
record that mapping with the run. `P` changes latency and critical path; it
must not silently change the sample schedule or numeric widths.

`U` is the number of frequency-domain arithmetic issue lanes used by the
FFT, frequency-bin multiply, and IFFT schedule. A scheduler handles the
remaining operations when the transform has more work than `U` lanes. `U=1`
is represented by the frequency serial baseline. The recommended FFT length
is 16, so `U=8` is the natural full-parallel butterfly point for each radix-2
stage; the frequency-bin multiplication and IFFT must still be included in
the same top-level accounting.

`F=2` means that the F-U8 logical schedule is time-multiplexed across two
issue slots using half as many physical arithmetic lanes, with the associated
registers, multiplexers, and controller included. F-F2 is deliberately one
contrast point, not a second folded sweep.

### Clock policy

Run every row first at the accepted primary target, `CLOCK_PERIOD=10 ns`
(100 MHz). If that exact RTL/configuration does not close at 100 MHz, retain
the failed primary result and repeat it at `CLOCK_PERIOD=100 ns` (10 MHz) as a
labelled fallback. Do not tune a fallback RTL separately, and do not rank a
10 MHz fallback against a 100 MHz passing result in one undifferentiated
table. A 10 MHz run is a recovery result, not evidence that the candidate met
the primary target.

## Source-Backed Facts

### Project decisions already accepted

- **Fact:** The project is an eight-coefficient, 50%-roll-off RRC filter at 2x
  oversampling with time and frequency versions. The canonical vocabulary
  defines pipeline as critical-path cuts, systolic as a PE array with rhythmic
  flow, unfolded as replicated parallel hardware, and folded as operator reuse
  that trades area for throughput. Source: repository `CONTEXT.md`.
- **Fact:** Optimization starts only after serial RTL has 100% vector matching;
  the serial versions establish the correctness and PPA reference. Source:
  [ADR 0002](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/docs/adr/0002-serial-rtl-before-optimization.md).
- **Fact:** The accepted lane techniques are time pipeline+systolic and
  frequency unfolded, with folded frequency as an area contrast when
  resources allow. The primary clock is 100 MHz and 10 MHz is an explicitly
  labelled fallback. Comparable runs retain area, signoff timing/slack,
  derived fmax, power activity status, and DRC/LVS/antenna status. Source:
  [ADR 0006](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/docs/adr/0006-systemverilog-openlane-ppa-flow.md).

### DSP and course facts

- **Fact:** The course folding exercise reuses one multiplier and one adder
  for a four-coefficient FIR, schedules the work over five cycles per sample,
  and documents the resulting area/throughput trade-off. It also measures the
  real synthesized `$mul`, `$add`, and register counts with Yosys. This is a
  useful precedent for making the folded point a resource-sharing contrast
  rather than an unbounded parameter sweep. Sources: the course
  [folding exercise README](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod6/ej3_folding/README.md),
  [RTL](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod6/ej3_folding/fir4_folded.sv),
  and [run script](https://github.com/iledesma08/rtl-marvell-formation-course/blob/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod6/ej3_folding/run.sh).
- **Fact:** Parhi's DSP architecture lecture material defines folding as
  time-multiplexing several algorithm operations onto fewer functional units,
  with an output-rate cost, and presents FIR systolic designs through
  space-time transformations. Sources: [Parhi, Chapter 6:
  Folding](http://www.ece.umn.edu/users/parhi/SLIDES/chap6.pdf) and [Parhi,
  Chapter 7: Systolic Architecture Design](http://www.ece.umn.edu/users/parhi/SLIDES/chap7.pdf).
- **Fact:** Stanford's FIR hardware lecture describes pipelining as a way to
  increase frequency while adding registers, latency, and register overhead.
  Source: [Stanford EE371 Lecture 3](https://web.stanford.edu/class/archive/ee/ee371/ee371.1066/lectures/lect_03.2up.pdf).
- **Fact:** NumPy's FFT documentation states that an FFT length larger than
  the input zero-pads the input and that powers of two are especially
  efficient. Source: [NumPy `fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html).
- **Fact:** SciPy documents FFT convolution as a linear convolution method and
  documents overlap-add convolution separately. Sources: [`fftconvolve`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.fftconvolve.html)
  and [`oaconvolve`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.oaconvolve.html).

### OpenLane/OpenROAD facts

- **Fact:** OpenLane 2's `CLOCK_PERIOD` is specified in nanoseconds. Source:
  [OpenLane universal flow variables](https://openlane2.readthedocs.io/en/stable/reference/common_flow_vars.html).
- **Fact:** The Classic flow includes synthesis, placement, CTS, routing,
  parasitic extraction, post-PnR STA, DRC, LVS, antenna checks, and final
  metrics. Source: [OpenLane built-in flows](https://openlane2.readthedocs.io/en/stable/reference/flows.html).
- **Fact:** OpenLane's post-PnR STA is the most accurate timing point in the
  documented flow because it uses the final routed design and extracted
  parasitics. The signoff step produces a multi-corner `summary.rpt` and
  per-corner `checks.rpt`, `max.rpt`, `min.rpt`, `power.rpt`, and skew reports.
  Sources: [OpenLane timing closure](https://openlane2.readthedocs.io/en/stable/usage/timing_closure/index.html)
  and [OpenLane newcomer flow outputs](https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html).
- **Fact:** OpenLane 2 exposes final `metrics.json` and `metrics.csv`; its
  resolved configuration records the final loaded configuration and metadata.
  Source: [OpenLane migration/output documentation](https://openlane2.readthedocs.io/en/stable/getting_started/migrants/index.html).
- **Fact:** OpenROAD provides `report_design_area` for design component area
  and utilization. Source: [OpenROAD Gate Resizer documentation](https://openroad.readthedocs.io/en/latest/main/src/rsz/README.html).
- **Fact:** OpenSTA/OpenROAD accepts gate-level Verilog, Liberty, SDC, SPEF,
  VCD, and SAIF inputs; VCD and SAIF are therefore valid activity sources for
  power analysis. Source: [OpenROAD STA documentation](https://openroad.readthedocs.io/en/latest/main/src/sta/README.html).
- **Fact:** OpenLane documents that timing repair can increase cell area via
  sizing and buffer insertion. Source: [OpenLane timing closure, timing
  optimization notes](https://openlane2.readthedocs.io/en/stable/usage/timing_closure/index.html).

## Recommended Fair Workload

The following is a recommendation for a stable comparison. The separate
frequency baseline ticket must settle the final alignment details before RTL
implementation.

- Use one fixed FXP data/coefficient/accumulator width selected by the shared
  SQNR contract. Do not let an architecture use a narrower internal type.
- Include both complex components in every DUT. A candidate may share hardware
  only when its schedule explicitly accounts for the resulting cycles and
  throughput; it may not report a real-only PPA number for a complex filter.
- Use the same generated QPSK stimulus: 128 symbols produce 256 complex
  2x-oversampled input samples. Use the same vector manifest, coefficient
  bits, reset sequence, and valid output window for every candidate.
- For frequency candidates, use FFT16, explicit frequency-domain
  multiplication, explicit IFFT, 50% overlap, and hop 8. For each 16-sample
  frame, discard the first `L-1=7` overlap-save outputs and retain the next 8
  outputs. The one remaining mathematically valid output in the 16-point frame
  is intentionally not used by this fixed hop-8 workload. This follows the
  professor's proposed FFT16/50%-overlap baseline from issue #14; alignment,
  padding, and exact valid-window details remain subject to that ticket.
- Use 32 frequency frames for the 256-sample workload. Do not compare a
  frequency design after only one frame with a time design after 256 samples;
  report steady-state measurements after warm-up and separately record
  block-fill latency.
- Drive the time lane continuously after reset and drive the frequency lane
  with contiguous frames after its initial buffer fill. Record accepted input
  samples, valid output samples, latency cycles, and steady-state initiation
  interval from the handshake, rather than inferring them solely from RTL
  names.
- Generate one representative VCD or SAIF from this same fixed workload,
  including the same reset and warm-up policy. Use the same activity file
  policy for all candidates. If activity is not annotated, label power as an
  unannotated estimate and use it only as a like-for-like auxiliary comparison,
  not as measured workload-dependent dynamic power.

## OpenLane Measurement Conditions

Every row should use the same conditions unless the factor itself requires a
documented exception:

- OpenLane 2 Classic, the same OpenLane revision, the same `sky130A` PDK, and
  the same `sky130_fd_sc_hd` standard-cell library.
- The same synthesis, floorplan, placement, CTS, routing, extraction, signoff,
  utilization, PDN, pin-order, IO-delay, drive, load, fanout, and max-transition
  constraints. Only the DUT source list, top name, architecture factor, and
  clock target should change.
- DUT and shared RTL only. Exclude testbenches, VCD/SAIF generators, golden
  vectors, and simulation-only code from `VERILOG_FILES`.
- The same reset/clock ports and an equivalent top-level scope. Include the
  domain-specific stream buffers, FFT storage, controllers, and valid/ready
  logic when they are part of the deployed DUT; excluding them would reward a
  smaller but unusable core.
- One primary 100 MHz run per row. A failed primary run is retained, then the
  unchanged RTL is run at the labelled 10 MHz fallback. Do not change
  utilization or optimization strategy only for a fallback run.
- Compare area, timing, and power only within the same clock target and signoff
  corner. Keep a separate fallback table so the 10 MHz recovery results cannot
  obscure a 100 MHz failure.
- Require 100% vector matching before a row enters the PPA ranking table.
  Record failed vector matching and failed physical signoff, but do not call
  either a valid PPA winner.

## Reports and Fields to Retain

Retain both raw artifacts and a normalized one-row record per run.

| Evidence | Fields to record |
| --- | --- |
| `resolved.json` and run metadata | OpenLane version, OpenROAD/Yosys/PDK revisions when available, flow, top, source checksum, factor values, clock target, exact config |
| `final/metrics.json` and `final/metrics.csv` | Canonical final metrics, flow status, area and health metrics available in that run |
| Post-PnR `summary.rpt` | Worst setup/hold slack, setup/hold TNS, violation counts, and the corner/aggregation used |
| Per-corner `max.rpt`, `min.rpt`, `ws.*`, `wns.*`, `tns.*`, `skew.*` | Critical setup and hold paths, WNS/WS/TNS, skew, and the corner that limits the result |
| Per-corner `checks.rpt` | Max capacitance, max slew, max fanout, unconstrained paths, unannotated/partially annotated nets, and SDC checks |
| Per-corner `power.rpt` | Total, leakage, internal, and switching power if present; power corner; voltage/temperature; VCD/SAIF name; activity annotation/coverage status |
| Area and implementation reports | Cell/design area in um2, core area, utilization, cell count/type breakdown, register count, and wire length if emitted |
| Signoff reports | DRC count/status, LVS result, antenna result, XOR/manufacturability result, and IR-drop/PDN status when enabled |
| Functional evidence | Vector manifest/checksum, exact vector-match count, valid-window convention, simulator log, and RTL source checksum |
| Throughput normalization | Measured II, accepted samples, valid outputs, block latency, steady-state samples/cycle, derived samples/s at signoff fmax, and energy/output only when activity is annotated |

For each timing row, retain raw period and signed slack. A derived fmax is
useful only when it is calculated from the same post-PnR signoff path and
corner; it must not replace WNS or hide a negative slack. For the normalized
PPA table, retain at least:

`lane, architecture, S, P, U, F, fft_n, hop, clock_target, timing_status,
vector_status, area_um2, utilization, setup_ws_ns, setup_tns_ns, hold_ws_ns,
hold_tns_ns, fmax_mhz, ii_cycles, samples_per_cycle, power_total, power_status,
drc, lvs, antenna, run_tag`.

## Interpretation Rules

- The primary performance comparison is effective valid-output throughput,
  not raw clock frequency alone. A folded or low-S design may have a good
  fmax but a worse samples/second result because its II is larger.
- Report time-lane pipeline effects at fixed `S` and report systolic effects at
  fixed `P`; this is why the 2x3 time factorial is preferable to only three
  diagonal points.
- Report frequency replication effects across F-U2, F-U4, and F-U8. Compare
  F-F2 primarily with F-U8 to show the area/throughput cost of reuse, and
  secondarily with F-U4 to expose mux/controller overhead.
- Do not claim that the matrix predicts the PPA trend. More registers can
  improve timing but increase area and clock power; OpenLane timing repair can
  also add buffers and cell area. The matrix is designed to reveal that trade,
  not to assume its sign.
- Use a Pareto table rather than a single weighted score unless the assignment
  supplies weights. Show area versus effective throughput and power per valid
  output separately, with timing/signoff status as gates.
- If all six time rows or all three unfolded frequency rows close comfortably
  and show the same trend, stop. Only add intermediate factors or repeated
  physical runs for a finalist when the first matrix leaves a genuine tie or
  unexplained outlier.

## Open Questions for Human Confirmation

- Issue #14 must finalize whether the 50% overlap FFT16 baseline keeps exactly
  the eight outputs described here, its zero-padding convention, and the
  time/frequency index alignment.
- Issue #17 must define the normative handshake, latency, and II semantics used
  to measure `S`, `P`, `U`, and `F`.
- The implementation owner must confirm that `P=1` and `P=2` are realizable
  with the chosen signed complex fixed-point datapath without changing
  truncation or saturation behavior.
- The team should decide whether a second identical OpenLane run is needed for
  finalists after the reproducible environment ticket (#19) reports the
  available tool versions and seed controls.

## Resolution Status

This report was written before the decision contracts. The open items and the
superseded recommendations are resolved as follows.

| Research item | Resolution |
| --- | --- |
| #14 finalize the 50% overlap FFT16 baseline, zero padding, and index alignment | #14 D1/D2: forced-50% OLS accepted (`N=16`, `H=8`, discard `z[0:8]`, emit `z[8:16]`), zero pre-frame history, and the full causal window via #15; #18 D8 cites the accepted schedule. |
| #17 define handshake, latency, and `II` semantics | #17 D1-D7: `valid`/`ready`, `latency_samples`/`latency_cycles` per variant, and `II` measured from the handshake; #18 D2 uses those definitions. |
| `P=1` and `P=2` realizable without changing truncation or saturation | Deferred to F3, recorded as an open item in `ppa-matrix-18.md`; all variants must be bit-exact, and the datapath owner confirms the cut placement during implementation. |
| Second identical OpenLane run for finalists | #18 D7: rerun a finalist only on a genuine tie or unexplained outlier; the environment and tool revisions are recorded per #19. |
| Research workload recommendation (256 samples) | Superseded by #18 D4: the canonical #15 frame (1024 symbols, 2048 samples) is used for matching and activity; the frequency lane processes 256 blocks of 8. |
| Research OLS wording ("discard `L-1=7`, retain 8") | Corrected by #18 D8: the accepted #14 schedule is discard `z[0:8]` and emit `z[8:16]`. |

The report remains the long-form research record; the accepted decisions live
in the contracts under `docs/contracts/`.

## Sources

1. Repository `CONTEXT.md`, especially the PPA and architecture vocabulary:
   https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/CONTEXT.md
2. Repository ADR 0002, serial RTL before optimization:
   https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/docs/adr/0002-serial-rtl-before-optimization.md
3. Repository ADR 0006, SystemVerilog/OpenLane/PPA decisions:
   https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/blob/main/docs/adr/0006-systemverilog-openlane-ppa-flow.md
4. Course folding exercise, README, RTL, and run script at commit
   `c7d9c32a6460be9c512186f8e112fb4661da92a9`:
   https://github.com/iledesma08/rtl-marvell-formation-course/tree/c7d9c32a6460be9c512186f8e112fb4661da92a9/mod6/ej3_folding
5. K. K. Parhi, *Chapter 6: Folding*:
   http://www.ece.umn.edu/users/parhi/SLIDES/chap6.pdf
6. K. K. Parhi, *Chapter 7: Systolic Architecture Design*:
   http://www.ece.umn.edu/users/parhi/SLIDES/chap7.pdf
7. Stanford EE371, *Lecture 3*:
   https://web.stanford.edu/class/archive/ee/ee371/ee371.1066/lectures/lect_03.2up.pdf
8. NumPy, `numpy.fft.fft` reference:
   https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html
9. SciPy, `signal.fftconvolve` and `signal.oaconvolve` references:
   https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.fftconvolve.html
   and https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.oaconvolve.html
10. OpenLane 2, universal flow variables:
    https://openlane2.readthedocs.io/en/stable/reference/common_flow_vars.html
11. OpenLane 2, Classic flow:
    https://openlane2.readthedocs.io/en/stable/reference/flows.html
12. OpenLane 2, timing closure and post-PnR reports:
    https://openlane2.readthedocs.io/en/stable/usage/timing_closure/index.html
13. OpenLane 2, newcomer flow outputs and signoff artifacts:
    https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html
14. OpenLane 2, migration/output mapping for `metrics.json`, `metrics.csv`,
    and `resolved.json`:
    https://openlane2.readthedocs.io/en/stable/getting_started/migrants/index.html
15. OpenROAD, Gate Resizer area/timing reporting:
    https://openroad.readthedocs.io/en/latest/main/src/rsz/README.html
16. OpenROAD, OpenSTA inputs and activity formats:
    https://openroad.readthedocs.io/en/latest/main/src/sta/README.html
