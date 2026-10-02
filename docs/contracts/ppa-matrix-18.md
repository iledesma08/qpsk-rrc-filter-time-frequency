# PPA Experiment Matrix Contract

Decision ticket: [#18](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/18)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-22

Updated: 2026-10-02

Branch: `docs/18-ppa-matrix`

Scope: decision record for the PPA experiment matrix, factor definitions,
workload, measurement conditions, activity policy, and the ranking rule. No
RTL, OpenLane configuration, or measurement script is included.

## Accepted Decisions

The team accepted the original decisions on 2026-09-22. The current decisions
include the 2026-09-25 scope amendment and the user-approved 2026-10-02 clock
and optimization-evidence amendment below; no professor approval is claimed
for the latter.

- **D1 — Matrix:** 6-row base matrix for the 11-06 delivery: the two serial
  baselines plus two time variants (`T-S4P1`, `T-S8P1`) and two frequency
  variants (`F-U4`, `F-U8`). The remaining six rows of the original 12-row
  matrix (`T-S2P1`, `T-S2P2`, `T-S4P2`, `T-S8P2`, `F-U2`, `F-F2`) return only
  on extension. (Amended 2026-09-25 — see Amendment below; rescoped before
  any implementation.)
- **D2 — Factor definitions:** `S`, `P`, `U`, and `F` have the meanings below;
  `II = 8/S`; all variants come from one parameterized RTL source and must be
  bit-exact within each domain's frozen numeric policy.
- **D3 — Clock policy:** the two serial architectures have main target SLOW
  10 MHz; the four optimized architectures have main target FAST 100 MHz.
  Prepare both targets for each of the six architectures (12 runs, not 12
  architectures). Prioritize the six main-target runs; execute secondary
  comparative runs as time/resources measured by the first real pilot permit.
  Completion of all 12 runs before 11-06 is not promised.
- **D4 — Workload:** the canonical #15 frame (1024 symbols, 2048 input
  samples, 2055 full causal outputs); the frequency lane processes 257 blocks
  (256 steady-state + 1 tail-flush, 2055 causal outputs).
- **D5 — Measurement conditions:** re-synthesize, optimize, and run PnR for
  each architecture/target under the same conditions except the declared
  clock. RTL and numerics do not change between targets; vector matching and
  physical signoff are gates.
- **D6 — Activity and power:** one representative VCD/SAIF per candidate and
  target from the same workload, timed at the actual clock period; dynamic
  power is ranked only with valid annotation at the same target, scenario,
  and corner.
- **D7 — Ranking:** Pareto front over area versus effective throughput, and
  power per output when annotated, with timing, vector, and signoff gates; no
  arbitrary weighted score. Each optimized candidate reports deltas against
  its same-domain serial at the same target under comparable conditions.
  Delivery requires demonstrated improvement in at least one PPA axis from
  at least one optimized candidate per domain, not from every variant or in
  every axis.
- **D8 — OLS schedule:** the matrix cites the accepted #14 schedule (discard
  `z[0:8]`, emit `z[8:16]`), correcting the earlier research wording.
- **D9 — Location:** this contract lives in `docs/contracts/` and follows the
  integration-branch flow.

## Decision Rationale

### D1 — Original decision: 12 structured rows

Historical rationale for the original matrix. The accepted six-row delivery
base supersedes it; see Matrix and Amendment below. These alternatives do
not make the extension rows mandatory.

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
  difference attributable to the architecture under test only within matched
  target, corner, workload, and activity conditions.

### Base implementation and optional experiments (amended 2026-10-02)

The base uses ordinary signed RTL multiplication/addition, a single correct
read-only coefficient representation, the conservative time accumulator and
frequency baseline A. Fixed coefficients and simulation/synthesis agreement
are required; a custom multiplier or a two-ROM comparison is not.
The following experiments are optional only after base evidence and with
capacity. They have no blocking edges into M2-M4 or the delivery:

- Optional custom Booth multiplier: if implemented, share recoder multiples
  (`+/-A`, `+/-2A`) across its partial-product multiplexers. Using the normal
  signed `*` operator is sufficient for the base; no Booth-specific sharing
  is required when no custom Booth implementation is used.
- Optional coefficient-path comparison: provide `$readmemh` and `case` ROM
  alternatives only if that experiment is activated. Constant coefficients via
  `case`/hardwiring permit or favor constant propagation and constant
  folding, subject to the synthesis tool and its configuration; verify the
  effect in the reports/netlist, never assume a physical implementation from
  the source form. If both paths are implemented, test their equivalence;
  otherwise validate the one chosen coefficient path against the frozen table.
  This does not remove `$readmemh` for testbench input/expected vector loading.
- Optional narrower accumulator and FFT-B experiments follow
  `fxp-policy-16.md`; do not silently adopt their policies or mix them into the
  six-architecture production comparison. Base no-overflow and SQNR checks
  remain mandatory even when these experiments are omitted.
- Keep synthesis constant folding separate from the architectural folding
  factor `F` (time-multiplexing of operators, defined above): they share a
  word and nothing else.
- Runtime-reloadable taps (coefficients from writable RAM/registers) stay
  outside the main PPA comparison: the eight taps are fixed by contract, and
  a variable coefficient operand would forfeit the constant optimization
  above for flexibility this project does not need.
- MAY (annex only, T44): one one-off area experiment with and without the
  constant-optimizable coefficient path, reported as annex evidence and
  excluded from the active Pareto ranking (six base rows, or twelve if the
  extension is activated). It MUST NOT become an additional ranked row nor
  contaminate the main comparison.

Outside the base delivery: the extra S2/P2/U2/folded architectures, Q1.15
coefficient sensitivity, AWGN/BER/full-link analysis, runtime-reloadable taps,
full AXI or new board-demo requirements. Additional matrix architectures remain
extension-only; other scope activation requires an explicit team decision.
An extension or unused time does not automatically activate every experiment.

### D3 — Original clock policy (historical, superseded 2026-10-02)

The rationale below records the original all-100-MHz-primary policy, not the
current rule. The 2026-10-02 amendment recognizes serial SLOW and optimized
FAST main targets; secondary matched-target runs add like-for-like serial
comparisons, subject to measured pilot capacity. See Clock Policy below.

- **Alternatives:** compare each variant at its own maximum frequency; force
  all rows to 10 MHz to avoid failures; run both targets for every row.
- **Why they were rejected:** comparing fmax rewards a small design that never
  meets the target; lowering everything to 10 MHz hides the primary goal;
  running both targets for every row doubles the work without adding
  information.
- **Why this was chosen:** a fixed signoff target is the production rule. The
  primary table contains only 100 MHz-closed rows, and failures are retained
  and repeated unchanged at a labelled 10 MHz fallback so the recovery result
  cannot be confused with a primary pass. Synthesis and PnR inputs (SDC, TCL,
  OpenLane JSON per top-level variant) are committed even when their numbers
  arrive later; an unrun script is recorded as unrun, never as a result.

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
  corners, PDN, IO, and utilization; only the DUT architecture, die size (per
  sizing rule), and clock target change, and
  vector matching plus physical signoff gate the ranking. Each clock target
  gets its own synthesis, timing optimization, and PnR run; architecture-only
  comparisons hold the target fixed.

### D6 — Activity and power

- **Alternatives:** no activity annotation; a different activity file policy
  per row; one representative VCD/SAIF from the common workload.
- **Why they were rejected:** without annotation the dynamic power is a
  default-activity estimate, not the workload result; different activity
  policies are not comparable.
- **Why this was chosen:** VCD and SAIF are the activity formats accepted by
  OpenSTA/OpenROAD, and one representative file per candidate and target from
  the same workload, at the actual period, makes the power comparison
  meaningful. Annotation coverage is recorded; unannotated power is labelled
  as an estimate and excluded from the dynamic-power ranking.

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

Base matrix for the 11-06 delivery (6 architectures, 12 prepared target runs):

| ID | Lane | Factor | Role | Main Target | Secondary Target |
| --- | --- | --- | --- | --- | --- |
| T-serial | Time | Serial baseline (`S=1`, `P=1`) | Area, timing, and throughput reference | SLOW 10 MHz | FAST 100 MHz |
| T-S4P1 | Time | `S=4`, `P=1` | Mid parallelism | FAST 100 MHz | SLOW 10 MHz |
| T-S8P1 | Time | `S=8`, `P=1` | Full tap array | FAST 100 MHz | SLOW 10 MHz |
| F-serial | Frequency | Serial baseline (`U=1`) | Area, timing, and throughput reference | SLOW 10 MHz | FAST 100 MHz |
| F-U4 | Frequency | `U=4` | Mid replication | FAST 100 MHz | SLOW 10 MHz |
| F-U8 | Frequency | `U=8` | Full radix-2 butterfly parallelism for FFT16 | FAST 100 MHz | SLOW 10 MHz |

An architecture row above is not a run: each has one main and one secondary
target run. The original 12-architecture extension below is distinct from
these 12 base target runs and is not activated by the clock amendment.

Extension rows (only if an extension is granted — same contracts, same
conditions; the datapaths stay parameterized so these return by
configuration, not redesign):

| ID | Lane | Factor | Role |
| --- | --- | --- | --- |
| T-S2P1 | Time | `S=2`, `P=1` | Low parallelism |
| T-S2P2 | Time | `S=2`, `P=2` | Pipeline effect at low parallelism |
| T-S4P2 | Time | `S=4`, `P=2` | Balanced timing/area point |
| T-S8P2 | Time | `S=8`, `P=2` | Timing-oriented full array |
| F-U2 | Frequency | `U=2` | Low replication point |
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
- All architectural variants within a domain are bit-exact with that domain's
  serial/FXP baseline: same rounding, saturation, widths, and expected codes
  at both clocks. Time and frequency FXP codes need not equal each other;
  each must meet SQNR against float and its RTL must match its own FXP model.
  If a numeric policy changes within a comparison, it measures precision
  rather than architecture and requires separate evidence.

## Clock Policy

- SLOW means `CLOCK_PERIOD = 100 ns` (10 MHz); FAST means
  `CLOCK_PERIOD = 10 ns` (100 MHz). Each run records its target, class, and
  main-or-secondary role according to the matrix above.
- Prepare the six architectures at both targets: 6 x 2 = 12 runs, not 12
  architectures. Prioritize the six declared main-target runs, then execute
  secondary comparative runs as measured time/resources permit. Record runtime
  and resource use from the first real filter pilot to determine capacity;
  there is no promise of all 12 completed runs before 2026-11-06 and no new
  assumed run duration.
- Re-synthesize, perform timing optimization, and run PnR separately for each
  target under the same conditions except the declared clock. Keep the same
  RTL revision, architecture parameters, coefficients, and numerics between
  targets; apply the same sizing rule and record the resulting die/core/util.
  Generate activity at each run's actual period, not by reusing another
  target's timing or merely scaling its reported power.
- Secondary runs supply same-clock serial comparisons: serial FAST versus
  optimized FAST, or serial SLOW versus optimized SLOW. They are comparative
  runs, not a fallback-only policy.
- Retain failed and unrun target runs with their status and reason. A FAST
  failure remains a failed FAST goal even if the same architecture passes
  SLOW; a SLOW pass never fulfills an optimized architecture's FAST main goal.
- Pareto ranking and architecture-only improvements require the same target,
  signoff corner, workload, and activity policy. Cross-target results may be
  displayed together only with explicit labels; they are not a controlled
  architecture-only comparison and cannot share a Pareto ranking.

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
  die. Record die area, core area, and utilization per target run.
- Require 100% vector matching and physical signoff before a row enters the
  ranking. Failed matching or failed signoff is recorded but is not a winner.

## Activity and Power

- Generate one representative VCD or SAIF per candidate and target from the full
  257-block canonical workload (256 steady-state + 1 tail-flush) after
  warm-up, with the same reset and warm-up policy for every row. The activity
  clock period must match the run's declared period (10 ns FAST or 100 ns SLOW);
  record that period with the activity evidence.
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

Among gated rows at the same target, signoff corner, workload, and activity
policy, build a Pareto front over:

- area in `um^2` versus effective throughput (valid outputs per second at the
  signoff corner and clock);
- power per valid output when activity is annotated.

No arbitrary weighted score. Derived metrics to report: samples/s per `um^2`,
energy per valid output when annotated, and `II`. The final selection is
defended with the measured trade-off. Rerun a finalist only when the first
matrix leaves a genuine tie or an unexplained outlier.

### Optimization Evidence

- Each optimized candidate must report deltas versus the **same-domain
  serial** using actual matched-target results: `T-S4P1`/`T-S8P1` versus
  `T-serial`, and `F-U4`/`F-U8` versus `F-serial`. Record both run tags, target,
  corner, workload, and activity conditions. Main/secondary roles may differ;
  the comparison target must not.
- Report effective valid-output throughput, area, and power per valid output
  for both runs, plus their absolute and/or percentage deltas with units and
  sign convention. Power per valid output is energy/output: annotated
  core + clock-tree power divided by effective valid-output throughput.
  Power evidence requires valid activity at the actual period for both runs,
  with comparable annotation policy and recorded coverage.
- If the serial fails the same-target gates, is unrun, or conditions are not
  comparable, record `not-comparable` and the reason; do not invent a delta,
  substitute another clock's serial result, or infer a baseline from fmax.
  Missing valid activity makes the power delta `not-comparable`; it cannot
  substantiate a power improvement.
- Delivery requires at least one optimized candidate **per domain** to
  demonstrate improvement in at least one PPA axis against a comparable
  serial result. It does not require every variant to improve, or one variant
  to improve every axis. The evidence comparison may use either matched
  target, but a secondary SLOW improvement does not fulfill a FAST main goal.
- Retain failed and non-improving candidates honestly. No run that fails the
  vector, physical-signoff, or target-timing gates can be a winner or count as
  demonstrated improvement; an unrun or non-comparable row supplies no such
  evidence. Report any unmet delivery evidence explicitly.

## Normalized Row

Retain at least:

```text
lane, architecture, S, P, U, F, fft_n, hop,
clock_target, clock_period_ns, target_class, target_role, corner, workload,
run_status, failure_or_unrun_reason, timing_status, vector_status,
area_um2, die_area_um2, core_area_um2, utilization,
setup_ws_ns, setup_tns_ns,
hold_ws_ns, hold_tns_ns, fmax_mhz, ii_cycles, samples_per_cycle,
effective_outputs_per_s, power_total, power_status, power_per_valid_output,
activity_file, activity_period_ns, annotation_coverage,
drc, lvs, antenna, run_tag, serial_run_tag, comparison_status,
comparison_reason, throughput_delta, area_delta, power_per_output_delta
```

Plus the raw evidence from `docs/contracts/openlane-env-19.md`: `resolved.json`,
`final/metrics.json`, `metrics.csv`, post-PnR `summary.rpt`, per-corner
`max.rpt`/`min.rpt`/`checks.rpt`/`power.rpt`, signoff reports, functional
evidence, and the throughput normalization.

## Interpretation Rules

- The primary performance comparison is effective valid-output throughput, not
  raw clock frequency alone; a folded or low-`S` design may have a good fmax
  and a worse samples/second result.
- Report pipeline effects at fixed `S` and systolic effects at fixed `P`
  (base matrix: systolic scaling `S4→S8` at fixed `P=1`; pipeline `P=2`
  comparisons return on extension).
- Report frequency replication across `F-U4` and `F-U8`; `F-U2` and the
  `F-F2` folded contrast return on extension (then compare `F-F2`
  primarily against `F-U8` and secondarily against `F-U4`).
- Do not claim that the matrix predicts the PPA trend; registers can improve
  timing and increase area and clock power. The matrix reveals the trade-off.
- If every time row and every unfolded frequency row close comfortably with
  the same trend at a comparable target, stop and keep the finalists; adding
  intermediate architectures still requires the extension, even for a tie or
  outlier.

## Presentation evidence (F5, non-normative)

- Keep the three quantities separate: **SQNR** is fixed-point quantization
  degradation versus the float reference (ADR-0005); **SNR / Es/N0** is
  channel noise and applies only if an explicit channel/noise model is
  defined (none exists: no AWGN is introduced in RTL or contractual
  vectors); **EVM** is RMS vector error versus the float golden output, the
  definition adopted here.
- F5 evidence priority: taps/response, SQNR, EVM, constellation, eye/zero-ISI
  on the canonical frame.
- BER versus theory is conditional only: it requires an explicitly
  implemented full chain (bits, mapper, TX shaping, AWGN, matched filter,
  timing, slicer, bits) with documented statistical significance, and stays a
  complementary analysis, never a contractual DoD. No AWGN model or
  communications chain is introduced only to replicate an external project.

## Open Items

- The implementation owner confirms during F3 that the `P=1` cuts are
  realizable in the chosen signed complex datapath without changing rounding
  or saturation; `P=2` cuts are verified only on extension.
- Finalist reruns are conditional on a tie or outlier (D7).
- Secondary-run capacity and ordering depend on runtime/resources measured by
  the first real filter pilot; retain unrun entries rather than promise all
  12 target runs before 11-06. Missing matched-target serial or valid-activity
  evidence must be reported, not filled by cross-target estimates.
- Nothing else blocks the F4 optimization phase once this contract is merged.

## Amendment — 6-row baseline (2026-09-25)

Before any implementation started, the team rescoped the base matrix from 12
rows to the 6-row base above: the 11-06 delivery cannot host the full
factorial (two opt lanes × closure × VCD × table in 11-01→11-05), and the
cheapest losses are the low-end points (`T-S2P1`, `F-U2`, readable as trends
from `S4/S8` and `U4/U8`) plus the additional pipeline-depth (`P=2`) and
folded comparisons. The base retains the registered `P=1` arithmetic;
pipeline-depth effects and the folded trade-off are not measured by it.
The 12-row matrix is not deleted: it is the defined extension scope, and every
datapath stays parameterized so cut rows return by configuration. The 10-16 checkpoint no
longer decides matrix scope; it confirms progress and is the venue to request
the extension.

## Amendment - Main Targets and Optimization Evidence (2026-10-02)

Accepted by the user on 2026-10-02 for recommendations 1 and 5; this records
user approval, not professor approval. The six base architectures and the
2026-09-25 extension-only scope are unchanged. The original D3 rationale is
retained as historical evidence, not an active fallback-only rule.

The two serial main targets are SLOW 10 MHz, and the four optimized main
targets are FAST 100 MHz. Prepare all 12 architecture/target runs, prioritize
the six main targets, and use the first real pilot's measured capacity to
schedule secondary comparisons without promising all 12 before 11-06.
Separate target runs use unchanged RTL/numerics, fresh synthesis/optimization/
PnR, and actual-period activity. A SLOW pass does not erase a FAST failure.

Every optimized candidate reports comparable same-domain serial deltas, or
explicit `not-comparable` status. Delivery needs demonstrated improvement in
at least one PPA axis from at least one optimized candidate per domain;
failed/non-improving candidates remain visible and failed gates yield no
winner. Cross-target displays are labelled context, not controlled
architecture-only improvement claims. This amendment does not change
precision, activate additional architectures, or alter the non-normative
Booth/ROM guidance.

## References

- Research: `docs/contracts/ppa-experiment-matrix-18.md`.
- Frequency block contract: `docs/contracts/frequency-block-contract-14.md`.
- QPSK stimulus contract: `docs/contracts/qpsk-stimulus-15.md`.
- FXP policy contract: `docs/contracts/fxp-policy-16.md`.
- RTL streaming contract: `docs/contracts/rtl-streaming-17.md`.
- OpenLane environment record: `docs/contracts/openlane-env-19.md`.
- ADR-0002, ADR-0006, and `CONTEXT.md`.
