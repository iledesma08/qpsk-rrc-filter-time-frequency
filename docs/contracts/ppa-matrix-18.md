# PPA Experiment Matrix Contract

Decision ticket: [#18](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/18)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-22

Updated: 2026-09-22

Branch: `docs/18-ppa-matrix`

Scope: decision record for the PPA experiment matrix, factor definitions,
workload, measurement conditions, activity policy, and the ranking rule. No
RTL, OpenLane configuration, or measurement script is included.

## Accepted Decisions

The team accepted these decisions on 2026-09-22:

- **D1 — Matrix:** 12 rows: the two serial baselines plus six time variants,
  three frequency variants, and one folded contrast.
- **D2 — Factor definitions:** `S`, `P`, `U`, and `F` have the meanings below;
  `II = 8/S`; all variants come from one parameterized RTL source and must be
  bit-exact with each other.
- **D3 — Clock policy:** 100 MHz primary for every row; a failing row is kept
  and repeated unchanged at 10 MHz as a labelled fallback in a separate table.
- **D4 — Workload:** the canonical #15 frame (1024 symbols, 2048 input
  samples, 2055 full causal outputs); the frequency lane processes 256 blocks
  of 8 output samples.
- **D5 — Measurement conditions:** one controlled experiment per row; only the
  DUT architecture changes; vector matching and physical signoff are gates.
- **D6 — Activity and power:** one representative VCD/SAIF per candidate from
  the same workload; dynamic power is ranked only with annotation and within
  the same scenario and corner.
- **D7 — Ranking:** Pareto front over area versus effective throughput, and
  power per output when annotated, with timing, vector, and signoff gates; no
  arbitrary weighted score.
- **D8 — OLS schedule:** the matrix cites the accepted #14 schedule (discard
  `z[0:8]`, emit `z[8:16]`), correcting the earlier research wording.
- **D9 — Location:** this contract lives in `docs/contracts/` and follows the
  integration-branch flow.

## Decision Rationale

### D1 — Matrix: 12 structured rows

- **Alternatives:** a full `S x P x U x F` factorial (about 36 runs); only
  three diagonal points; the structured 12-row matrix.
- **Why they were rejected:** the full factorial costs compute and produces
  redundant points for an 8-tap filter; the diagonal points cannot separate
  the effect of `S` from the effect of `P`.
- **Why this was chosen:** 2, 4, and 8 divide the eight taps exactly, the
  2x3 time factorial reads `S` at fixed `P` and `P` at fixed `S`, and the
  frequency series plus one folded contrast shows scaling and reuse without
  becoming an arbitrary parameter sweep.

### D2 — Factor definitions and production practice

- **Alternatives:** vague labels with no numeric parameter; hand-edited
  variants; parameters that change numeric behavior between variants.
- **Why they were rejected:** ambiguous labels produce different architectures
  under the same name; hand-edited variants cannot be attributed or
  regenerated; if rounding, saturation, or widths change, the comparison
  measures precision instead of architecture.
- **Why this was chosen:** production design-space exploration generates every
  variant from one parameterized RTL source, documents the semantics of each
  parameter, measures `II`, latency, and throughput from the handshake, and
  requires all variants to be bit-exact with each other. That keeps every PPA
  difference attributable to the architecture under test.

### D3 — Clock policy

- **Alternatives:** compare each variant at its own maximum frequency; force
  all rows to 10 MHz to avoid failures; run both targets for every row.
- **Why they were rejected:** comparing fmax rewards a small design that never
  meets the target; lowering everything to 10 MHz hides the primary goal;
  running both targets for every row doubles the work without adding
  information.
- **Why this was chosen:** a fixed signoff target is the production rule. The
  primary table contains only 100 MHz-closed rows, and failures are retained
  and repeated unchanged at a labelled 10 MHz fallback so the recovery result
  cannot be confused with a primary pass.

### D4 — Workload: the canonical stimulus frame

- **Alternatives:** the research's 256-sample workload; a per-lane workload;
  the canonical 2048-sample frame.
- **Why they were rejected:** a second workload adds a convention to maintain
  for no measurable benefit, and per-lane workloads destroy comparability.
- **Why this was chosen:** the accepted #15 frame is already the single source
  of truth, 2048 samples are trivial to simulate, and the frequency lane
  simply processes 257 blocks (256 steady-state + 1 tail-flush, 2055 causal
  outputs).

### D5 — Measurement conditions

- **Alternatives:** let each row use its own flow settings; exclude buffers and
  controllers to shrink the area; promote a row to the ranking before signoff.
- **Why they were rejected:** different settings make the comparison invalid;
  excluding deployed logic rewards an unusable core; an unverified row cannot
  be a PPA winner.
- **Why this was chosen:** it is the production controlled experiment: same
  flow, PDK, standard cells, constraints, floorplan, CTS, routing, extraction,
  corners, PDN, IO, and utilization; only the DUT architecture changes, and
  vector matching plus physical signoff gate the ranking.

### D6 — Activity and power

- **Alternatives:** no activity annotation; a different activity file policy
  per row; one representative VCD/SAIF from the common workload.
- **Why they were rejected:** without annotation the dynamic power is a
  default-activity estimate, not the workload result; different activity
  policies are not comparable.
- **Why this was chosen:** VCD and SAIF are the activity formats accepted by
  OpenSTA/OpenROAD, and one representative file per candidate from the same
  workload makes the power comparison meaningful. Annotation coverage is
  recorded; unannotated power is labelled as an estimate and excluded from the
  dynamic-power ranking.

### D7 — Ranking rule

- **Alternatives:** a weighted score; single-axis optimization; a Pareto front
  with gates and a documented selection.
- **Why they were rejected:** a weighted score needs weights nobody defined
  and is easy to manipulate; single-axis optimization ignores the other two
  required axes.
- **Why this was chosen:** production multi-objective decisions use Pareto
  fronts with hard constraints because the "best" point depends on product
  priorities. The final selection is defended in the slides with the derived
  metrics (throughput per area, power per valid output) and the measured
  trade-off.

### D8 — OLS schedule correction

- **Alternatives:** cite the earlier research wording (discard `L-1 = 7`,
  keep 8); cite the accepted #14 contract.
- **Why the earlier wording was rejected:** it contradicts the accepted
  interface specification. A derivation note is not the source of truth, and
  any deviation would require a formal change request and re-verification.
- **Why this was chosen:** one source of truth. The matrix uses the accepted
  forced-50% schedule: discard `z[0:8]` and emit `z[8:16]`.

### D9 — Location

- **Alternatives:** keep the matrix in the issue text; leave it on a research
  branch; commit directly to `main`.
- **Why they were rejected:** issue text is hard to diff and review; research
  branches are throwaway snapshots; a direct `main` commit bypasses the
  protected-branch flow.
- **Why this was chosen:** it matches the other contracts, stays reviewable in
  a PR, and lands on `main` through the final integration PR.

## Matrix

| ID | Lane | Factor | Role |
| --- | --- | --- | --- |
| T-serial | Time | Serial baseline (`S=1`, `P=1`) | Area, timing, and throughput reference |
| T-S2P1 | Time | `S=2`, `P=1` | Low parallelism |
| T-S4P1 | Time | `S=4`, `P=1` | Mid parallelism |
| T-S8P1 | Time | `S=8`, `P=1` | Full tap array |
| T-S2P2 | Time | `S=2`, `P=2` | Pipeline effect at low parallelism |
| T-S4P2 | Time | `S=4`, `P=2` | Balanced point |
| T-S8P2 | Time | `S=8`, `P=2` | Timing-oriented full array |
| F-serial | Frequency | Serial baseline (`U=1`) | Area, timing, and throughput reference |
| F-U2 | Frequency | `U=2` | Low replication |
| F-U4 | Frequency | `U=4` | Mid replication |
| F-U8 | Frequency | `U=8` | Full radix-2 butterfly parallelism for FFT16 |
| F-F2 | Frequency | `F=2` reuse of the `U=8` schedule | Area/throughput contrast |

## Factor Definitions

- **`S` (systolic tap PEs):** number of tap processing elements that can be
  active in one time-domain issue group. The remaining tap groups are
  scheduled in later cycles, so the expected initiation interval is
  `II = 8/S` cycles per accepted sample before interface bubbles. `S=8` is
  the fully parallel tap array; the serial baseline is the `S=1` reference
  (`II=8`: `ready_o` deasserts 7 of every 8 cycles under `valid_i = 1`) and
  is not duplicated in the factorial. `S` sets compute parallelism; `SPC`
  (`SAMPLES_PER_CLOCK` in `docs/contracts/rtl-streaming-17.md`) is the
  interface width and must not be conflated with `S` or `II`.
- **`P` (pipeline depth):** pipeline depth used consistently in every
  time-lane PE. `P=1` keeps the multiply/accumulate in one registered
  arithmetic stage; `P=2` inserts a register between the multiply and the add.
  If the team uses cut-set terminology instead, `P=1`/`P=2` map to one/two
  registered cuts and that mapping must be recorded with the run. `P` changes
  latency and critical path and must not change the sample schedule or the
  numeric widths.
- **`U` (frequency issue lanes):** number of frequency-domain arithmetic issue
  lanes used by the FFT, the frequency-bin multiply, and the IFFT. A scheduler
  handles the remaining operations. `U=1` is the serial baseline; `U=8` is the
  natural full butterfly parallelism for a 16-point radix-2 transform. The bin
  multiply and IFFT are included in the same top-level accounting.
- **`F` (folding factor):** `F=2` time-multiplexes the `F-U8` logical schedule
  across two issue slots with half the physical arithmetic lanes, including
  the associated registers, multiplexers, and controller. It is one contrast
  point, not a second folded sweep.
- **`II` (initiation interval):** cycles between accepting two consecutive
  input samples (time lane) or issuing two consecutive work groups. It is
  measured from the handshake (`valid && ready`), not inferred from RTL
  names, `SPC`, or `S` alone, and it is the basis of the
  effective-throughput comparison. `ready_o = 1` in every cycle holds only
  for fully-parallel variants; every other variant backpressures and the
  testbench measures `II` across that backpressure with no sample loss.

## Production Practice for Variants

- One parameterized RTL source generates every row; variants are never edited
  by hand.
- Each parameter has documented semantics, and the generator revision and
  parameter values are recorded with each run.
- `II`, latency, and throughput are measured from the handshake defined in
  `docs/contracts/rtl-streaming-17.md`.
- All variants are bit-exact with each other: same rounding, same saturation,
  same widths. If the numeric result changes, the comparison measures
  precision rather than architecture.

## Clock Policy

- Every row runs first at `CLOCK_PERIOD = 10 ns` (100 MHz).
- A row that does not close is retained as a failed primary result and
  repeated with the **unchanged RTL** at `CLOCK_PERIOD = 100 ns` (10 MHz) in a
  separate labelled fallback table.
- Area, timing, and power are compared only within the same clock target and
  signoff corner. A 10 MHz result never appears in the same table as a 100 MHz
  pass.
- D3 interpretation: 10 MHz is recovery, never ranked with 100 MHz passes. If
  professor intended slow-power class, add low-power lane.

## Workload

- Use the canonical #15 frame: 1024 symbols, 2048 input samples, and the full
  causal 2055-sample output window.
- Use the same vector manifest, coefficient bits, reset sequence, and valid
  output window for every candidate.
- The frequency lane processes 257 blocks (256 steady-state + 1 tail-flush,
  2055 causal outputs), input 2048 + zero-pad to cover S+M-2 per #14, trim to
  valid_len=2055, following the accepted #14 schedule: discard `z[0:8]`,
  emit `z[8:16]`.
- Report steady-state measurements after warm-up, and separately record
  block-fill latency. Report steady-state II on first 256, latency split
  fill vs tail, VCD covers all 257. Drive the time lane continuously after
  reset and the frequency lane with contiguous frames after its initial fill.
- Record accepted input samples, valid outputs, latency cycles, and
  steady-state `II` from the handshake.

## Measurement Conditions

- OpenLane 2 Classic, the same OpenLane revision (v2.3.10, volare `0fe599`
  per `docs/contracts/openlane-env-19.md`), `sky130A`, and
  `sky130_fd_sc_hd`.
- Same synthesis, floorplan, placement, CTS, routing, extraction, signoff,
  PDN strategy, pin-order, IO-delay, drive, load, fanout, and
  max-transition constraints; same SDC template via `PNR_SDC_FILE` and
  `SIGNOFF_SDC_FILE`, identical except the clock period (see
  `docs/contracts/toolchain-gap-2.md`). Only the DUT source list, top name,
  architecture factors, die size (per the sizing rule below), and clock
  target change.
- DUT and shared RTL only. Exclude testbenches, activity generators, golden
  vectors, and simulation-only code from `VERILOG_FILES`.
- Include the domain-specific stream buffers, FFT storage, controllers, reset
  synchronizer, and `valid`/`ready` logic when they are part of the deployed
  DUT.
- Sizing rule: size each die for 50-60% core utilization (target ~55%);
  final die is `max(sized-for-target, 200x200 um)` as the PDN-0185 floor
  (see `docs/contracts/openlane-env-19.md`). Same PDN strategy, not same
  die. Record die area, core area, and utilization per row.
- Require 100% vector matching and physical signoff before a row enters the
  ranking. Failed matching or failed signoff is recorded but is not a winner.

## Activity and Power

- Generate one representative VCD or SAIF per candidate from the full
  257-block canonical workload (256 steady-state + 1 tail-flush) after
  warm-up, with the same reset and warm-up policy for every row.
- **VCD** (`Value Change Dump`, IEEE 1364) records signal value changes over
  simulation time; Icarus/Verilator produce it with `$dumpfile`.
- **SAIF** (`Switching Activity Interchange Format`) stores per-net toggle
  counts and static probabilities in a compact form.
- OpenSTA/OpenROAD accept both for switching-power analysis.
- Record the activity file name and the annotation coverage. Report core +
  clock-tree power; exclude any IO split. If activity is
  not annotated, label the power as an unannotated estimate and use it only
  as an auxiliary like-for-like comparison, never in the dynamic-power
  ranking.

## Ranking Rule

Gates, in order:

1. 100% vector matching.
2. Physical signoff (DRC, LVS, antenna).
3. Timing closure at the row's clock target.

Among gated rows, build a Pareto front over:

- area in `um^2` versus effective throughput (valid outputs per second at the
  signoff corner and clock);
- power per valid output when activity is annotated.

No arbitrary weighted score. Derived metrics to report: samples/s per `um^2`,
energy per valid output when annotated, and `II`. The final selection is
defended with the measured trade-off. Rerun a finalist only when the first
matrix leaves a genuine tie or an unexplained outlier.

## Normalized Row

Retain at least:

```text
lane, architecture, S, P, U, F, fft_n, hop, clock_target, timing_status,
vector_status, area_um2, die_area_um2, core_area_um2, utilization,
setup_ws_ns, setup_tns_ns,
hold_ws_ns, hold_tns_ns, fmax_mhz, ii_cycles, samples_per_cycle,
power_total, power_status, activity_file, annotation_coverage,
drc, lvs, antenna, run_tag
```

Plus the raw evidence from `docs/contracts/openlane-env-19.md`: `resolved.json`,
`final/metrics.json`, `metrics.csv`, post-PnR `summary.rpt`, per-corner
`max.rpt`/`min.rpt`/`checks.rpt`/`power.rpt`, signoff reports, functional
evidence, and the throughput normalization.

## Interpretation Rules

- The primary performance comparison is effective valid-output throughput, not
  raw clock frequency alone; a folded or low-`S` design may have a good fmax
  and a worse samples/second result.
- Report pipeline effects at fixed `S` and systolic effects at fixed `P`.
- Report frequency replication across `F-U2`, `F-U4`, and `F-U8`; compare
  `F-F2` primarily against `F-U8` and secondarily against `F-U4`.
- Do not claim that the matrix predicts the PPA trend; registers can improve
  timing and increase area and clock power. The matrix reveals the trade-off.
- If every time row and every unfolded frequency row close comfortably with
  the same trend, stop and keep the finalists; add intermediate factors only
  for a genuine tie or outlier.

## Open Items

- The implementation owner confirms during F3 that `P=1` and `P=2` are
  realizable in the chosen signed complex datapath without changing rounding
  or saturation.
- Finalist reruns are conditional on a tie or outlier (D7).
- Nothing else blocks the F4 optimization phase once this contract is merged.

## References

- Research: `docs/contracts/ppa-experiment-matrix-18.md`.
- Frequency block contract: `docs/contracts/frequency-block-contract-14.md`.
- QPSK stimulus contract: `docs/contracts/qpsk-stimulus-15.md`.
- FXP policy contract: `docs/contracts/fxp-policy-16.md`.
- RTL streaming contract: `docs/contracts/rtl-streaming-17.md`.
- OpenLane environment record: `docs/contracts/openlane-env-19.md`.
- ADR-0002, ADR-0006, and `CONTEXT.md`.
