# FXP Policy Contract

Decision ticket: [#16](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/16)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-22

Updated: 2026-10-07 (production-A integer freeze amendment proposed, #44);
2026-10-06 (cross-domain SQNR amendment, #74); 2026-10-02 (production
Q2.14, numeric freeze and base-scope amendments)

Branch: `docs/16-fxp-policy`

Scope: decision record for the fixed-point numeric policy, the reproducible
width sweep, and the common-width rationale. No implementation code is
included.

## Accepted Decisions

The team accepted these decisions on 2026-09-22:

- **D1 — Sweep matrix:** the base requires the RNE width sweep at
  `W = 8, 10, 12, 14, 16, 18` and production W=16 validation, with conservative
  accumulators and frequency baseline A. Extra truncation/wrap, narrow-guard
  and frequency-B experiments are optional; Q1 sensitivity is outside base.
- **D2 — Common format:** production input/output components and stored RRC
  coefficients use signed `Q2.14` (`W_common=16`, `F_data=F_coeff=14`). The
  diagnostic sweep uses `Q2.(W-2)` at its tested widths. `Q1.(W-1)` remains
  a labelled sensitivity experiment, not a production alternative. This
  refines RRC D4 and supersedes automatic smallest-width selection.
- **D3 — Numeric policy:** RNE at every intentional narrowing; saturation only
  at an explicit narrowing/output boundary; internal accumulator overflow
  fails the candidate; wrap-around is a diagnostic only.
- **D4 — Time accumulator:** conservative `2W+3` base (35 bits at W=16).
  `2W+1` and `2W+2` are optional experiments, never F2 blockers; no-overflow
  assertions remain mandatory for the base as well.
- **D5 — Frequency scaling:** baseline A (grow-by-stage, full-precision
  products) is the production base. Baseline B (one-bit-per-stage scaling) is
  an optional separate experiment after base evidence is available, not a
  required selection contest. Adopting it requires an explicit policy change,
  regeneration, SQNR verification and repeat matching.
- **D6 — SQNR frame:** keep the accepted 1024-symbol frame from #15 and add a
  split-half stability check; extend to 4096 symbols only if the halves
  disagree by more than 0.5 dB.
- **D7 — Manifest:** adopt the machine-readable sweep row fields and
  sign-extend each component into the existing 16-bit I/Q vector fields when
  `W < 16`; RTL compares stored integer bit patterns.
- **D8 — PPA ranking:** deferred to ticket #18; the FXP width is not changed
  after seeing one preferred PPA axis without recording the trade-off.
- **D9 — Location:** this contract lives in `docs/contracts/` and follows the
  integration-branch flow.

## Decision Rationale

### D1 — Original sweep rationale: `W = 8..18` in five phases

Historical rationale below. The base-scope amendment on 2026-10-02 keeps the
RNE width sweep mandatory while removing optional comparison experiments from
phase exit criteria. The assignment still receives a measured bits/SQNR table.

- **Alternatives:** select a width analytically; run a two-point sweep (for
  example 12 and 16); guess a single width.
- **Why they were rejected:** analytical selection cannot predict the combined
  effect of rounding, coefficient quantization, and FFT stage scaling; a
  two-point sweep can miss the frontier and cannot separate policy effects;
  guessing risks failing 40 dB or over-provisioning hardware.
- **Why this was chosen:** the phased matrix isolates width, rounding,
  overflow behavior, accumulator guard bits, and FFT scaling, while phase A
  stays small enough to inspect (6 widths x 2 rounding modes = 12
  configurations per domain).

### D2 — Common format: signed `Q2.(W-2)` for data and coefficients

The rationale below records the shared binary-point convention. The
2026-10-02 amendment fixes its production instance to `Q2.14`; lower or higher
width sweep results are evidence, not automatic production selections.

- **Alternatives:** keep the split format from RRC D4 (data `Q2.(W-2)`,
  coefficients `Q1.(W-1)`); use a different binary point per signal.
- **Why they were rejected:** a split format creates two binary-point
  conventions, complicates the manifest and the final rescale, and mixes a
  coefficient-precision difference into what should be a pure width
  comparison; the extra coefficient bit is numerically irrelevant for the
  40 dB target.
- **Why this was chosen:** one convention simplifies the manifest, the RTL
  rescale, and the cross-domain comparison. The `Q1.(W-1)` coefficient variant
  is retained as a labelled sensitivity row in phase E, and RRC D4 is refined
  with a pointer to this decision.

### D3 — Numeric policy: RNE, explicit saturation, no internal overflow

- **Alternatives:** truncation-toward-zero as the canonical rounding; wrap
  as the overflow mode; rely on language or library defaults.
- **Why they were rejected:** truncation has a directional bias for signed
  data; wrap hides overflow and can produce a few catastrophic samples that a
  good aggregate SQNR would mask; Python and SystemVerilog defaults differ, so
  implicit behavior would make vector matching fragile.
- **Why this was chosen:** RNE removes the directional bias at a modest
  hardware cost, explicit saturation defines the interface behavior, and
  failing candidates on internal overflow keeps precision decisions honest.

### D4 — Time accumulator: conservative `2W+3` baseline

- **Alternatives:** derive a minimal width from the coefficient-sum bound;
  start from `2W+1` or `2W+2`.
- **Why they were rejected:** the coefficient-sum bound assumes optimistic
  operand ranges and ignores reduction-tree effects; narrower widths risk
  overflow and would need a proof before use; choosing them before measuring
  could invalidate the sweep results.
- **Why this was chosen:** `2W+3` is a conservative starting point that cannot
  overflow for the accepted stimulus; narrower widths are measured separately
  with an overflow assertion and adopted only after a no-overflow check and a
  PPA comparison.

### D5 — Original frequency-scaling rationale (superseded for base scope)

The rationale below records the original mandatory A/B comparison. Production
now uses A; B is optional and has no prerequisite edge into base delivery.

- **Alternatives:** fix baseline A (unscaled, grow-by-stage) only; fix
  baseline B (one-bit-per-stage scaling) only; use another schedule.
- **Why they were rejected:** fixing A risks unnecessary internal width;
  fixing B risks hidden quantization at each shift; other schedules add
  unmeasured complexity.
- **Why this was chosen:** running both at the same `W` separates the common
  word precision from the FFT scaling cost, and the PPA measurement decides
  between them instead of a preference.

### D6 — SQNR frame: keep 1024 symbols with a stability check

- **Alternatives:** extend the canonical frame to 4096 symbols (the research
  default); use a 1024-symbol vector frame and a separate 4096-symbol SQNR
  frame; keep 1024 without any check.
- **Why they were rejected:** extending reopens the accepted #15 contract for
  a benefit that is likely below 0.1 dB; two frames break the single-frame
  simplicity and the common-frame spirit of ADR-0005; keeping 1024 without a
  check risks an unstable estimate near the 40 dB threshold.
- **Why this was chosen:** the accepted frame is statistically sufficient for
  a stable estimate (2048 samples, roughly 0.1 dB standard error), and the
  split-half check catches the rare unstable case before it affects the width
  selection.

### D7 — Manifest: machine-readable rows and integer-code comparison

- **Alternatives:** reuse the stimulus manifest without FXP fields; invent
  field names per experiment; compare re-converted floating-point values in
  the testbench.
- **Why they were rejected:** missing fields make the sweep unreproducible;
  ad-hoc names break tooling and comparison; float comparison breaks exact
  vector matching and hides integer-level mismatches.
- **Why this was chosen:** the research row schema captures every policy field
  and the sign-extension rule keeps the accepted packed-vector format while
  making the active `W` explicit.

### D8 — PPA ranking: deferred to #18

- **Alternatives:** define the ranking rule here; let each lane pick its own
  rule; ignore power when activity is not annotated.
- **Why they were rejected:** defining it here mixes FXP policy with PPA
  methodology; per-lane rules make comparisons unfair; ignoring power hides a
  required PPA axis.
- **Why this was chosen:** #18 owns the PPA matrix and ranking, and the
  explicit rule that the width cannot change after seeing one preferred axis
  keeps the comparison honest.

### D9 — Location: `docs/contracts/` with the integration flow

- **Alternatives:** keep the policy in the issue text; leave it only on the
  research branch; commit directly to `main`.
- **Why they were rejected:** issue text is hard to diff and review; research
  branches are throwaway snapshots; a direct `main` commit bypasses the
  protected-branch flow.
- **Why this was chosen:** it matches the other contracts, stays reviewable in
  a PR, and lands on `main` through the single final integration PR.

## Numeric Policy

### Common data and coefficient words

| Quantity | Format | Reason |
| --- | --- | --- |
| Production I/Q input and output | `Q2.14`, `W=16` | Declared format; `+1` and `-1` inputs are exactly representable. |
| Production RRC coefficient | `Q2.14`, `W=16` | One binary point and one quantization rule for both domains. |
| Diagnostic width sweep | `Q2.(W-2)`, `W = 8, 10, 12, 14, 16, 18` | Report the precision frontier; extend to 20 if needed, without silently changing production. |

Quantization for a real value `x`:

```text
F = W - 2
q_unbounded = round_even(x * 2^F)
q = min(max(q_unbounded, -2^(W-1)), 2^(W-1)-1)
```

The coefficient quantizer must record a range violation instead of silently
saturating the known RRC coefficients.

For reference, at `W=16` the accepted coefficients become the common-format
integers:

```text
Q2.14: [179, -1818, 1818, 11295, 11295, 1818, -1818, 179]
```

The existing T10 artifact labels these integers `illustrative_not_frozen`.
T20/T21 must validate the complete numeric path and T22 exports the production
table and evidence. Declaring the format now is not a measured SQNR result.

The `Q1.(W-1)` coefficient variant (`Q1.15` at `W=16`, integers
`[359, -3636, 3636, 22590, 22590, 3636, -3636, 359]`) stays as a labelled
sensitivity experiment in phase E, outside the current delivery base.

### Products and the time-domain accumulator

With `W_d = W_c = W` and `F_d = F_c = F`:

```text
product width       W_p   = W_d + W_c = 2W
product frac bits   F_p   = F_d + F_c = 2F
time accumulator    W_acc = W_p + ceil(log2(8)) = 2W + 3
time accumulator    F_acc = 2F
```

Products are added at full precision with no rounding between taps; the single
cast to the output format happens after the eight-term sum, using RNE and
saturation.

At production `W=16`: products are 32 bits with 28 fractional bits; the
conservative accumulator is 35 bits with 28 fractional bits. Only the final
output is narrowed to signed 16-bit `Q2.14`. The format decision does not
force FFT intermediates or accumulators to 16 bits.

### Frequency-domain internal widths

The common width `W` is the width of the input samples and stored
coefficients, not of every FFT wire. For the unscaled 16-point radix-2
baseline:

```text
forward FFT stage widths:  W, W+1, W+2, W+3, W+4
complex pointwise product: 2*(W+4) + 1 bits
unscaled IFFT growth:      four additional add/subtract guard bits
final normalization:        divide by 16, then cast to Q2.(W-2)
```

Production baseline A grows guard bits per radix-2 stage and retains
full-precision products as specified by the numeric freeze. Optional baseline B
shifts by one bit per stage and must record its total scale. If evaluated, use
the same RNE rule and common W; neither policy can silently replace the other.

### Frequency arithmetic freeze (T20 before T21)

Juan defines the FFT/IFFT operation schedule with Matias, who implements the
same integer operations in the FXP model. Baseline A is the mandatory production
reference; baseline B is a separate optional experiment, not a freeze blocker.
Before a sweep result is accepted, the numeric policy must record:

- transform direction, radix/stage ordering, bin ordering, and inverse scaling;
- twiddle integers, their width/fractional bits, generation and RNE rules;
- generation of `H[k]` from the quantized eight coefficients, plus its stored
  width/fractional bits and every rounding step;
- product/add widths, sign extension, and every intentional narrowing point;
- all shifts and total compensation of the active policy (including baseline B
  only if that experiment is explicitly activated), so the
  forward/filter/inverse path restores the declared `Q2.14` output scale;
- deterministic arithmetic checks or intermediate traces showing that the
  intended RTL and model execute the same integer operations.

Using NumPy FFTs and quantizing only the final result is not the frequency FXP
model. The fixed-point model must include the actual internal quantization.
Both clock targets and every architecture within a domain use the same frozen
production-A policy and expected codes. Optional A/B experiments are identified separately;
switching policy requires regeneration and repeat matching, never mixing
different policies in an architecture-only PPA comparison.

### Rounding

RNE applies at every intentional reduction in fractional precision:
coefficient quantization, FFT stage scaling if selected, complex-product
narrowing if any, and the final output cast. Truncation-toward-zero remains a
low-cost comparison row only, and the Python model and RTL must use the same
explicitly named operation.

### Saturation and overflow

1. Input and coefficient quantizers: saturating conversion with a range
   assertion.
2. Time and frequency accumulators: no wrap and no silent saturation; expose
   an overflow flag and fail the candidate if it asserts.
3. Explicit narrowing/output cast: RNE followed by saturation; count events.
4. Canonical acceptance frame: zero internal overflow and zero output
   saturation. If either occurs, increase the width or change the declared
   scaling instead of hiding it behind aggregate SQNR.
5. Wrap-around, if the optional diagnostic is activated, appears only as a
   negative control. It is never an acceptable production overflow behavior.
6. Directed arithmetic checks, owned by T20 as `pytest` on the FXP model
   (arbitrary stimulus values are natural at model level; no RTL stimulus
   changes): positive/negative quantizer saturation, representable extremes,
   and `+/-1` LSB rounding behavior are MUST checks.
7. RNE ties at the output cast: T20 MUST first determine whether a reachable
   tie exists at the relevant narrowing boundary for the accepted `W` (i.e.
   dropped fraction bits exactly `100...0` producible by the time/frequency
   datapath on the canonical frame plus the `sys_corners` sets). If such a
   tie exists, its exact-rounding check is MUST; if no tie is reachable, T20
   documents the arithmetic reason instead of imposing an untestable MUST.
   No RTL infrastructure is added to force ties.

### Signed SystemVerilog discipline

Use explicit `signed` declarations and explicit sign extension before
additions; cast every part-select used arithmetically back to a signed type;
name product, accumulator, and narrowed-output widths as parameters in the
shared package. The testbench compares stored integer bit patterns after sign
extension, never a simulator-specific conversion.

## Sweep Matrix

### Inputs that must be frozen

| Input | Status |
| --- | --- |
| Python/runtime | Pinned by the toolchain research (#2). |
| Float reference | ADR-0001 and the RRC contract. |
| QPSK generator | #15: `default_rng(2026)`, 1024 symbols, five edge patterns. |
| Frame | #15: zero insertion, 2048 input samples, full causal 2055-sample window. |
| Coefficient normalization | #13: discrete unit energy, ascending time order. |
| Frequency block | #14: forced-50% OLS, FFT16, hop 8, discard `z[0:8]`, emit `z[8:16]`. |
| Alignment | #14/#15: full causal window with `D = 3.5` samples. |
| Metric | ADR-0005 complex I/Q SQNR, per domain and cross-domain. |
| Reproducibility | Git commit, dependency versions, manifest and vector hashes, policy fields. |

### Phases

| Phase | Values | Purpose |
| --- | --- | --- |
| A. Common format (required) | `W = 8,10,12,14,16,18`; RNE, conservative guards, frequency A | Report precision frontier and validate production Q2.14. |
| Rounding comparison (optional) | Truncation-toward-zero at selected diagnostic widths | Explain rounding effects; never redefine production RNE. |
| B. Wrap comparison (optional) | Wrap negative control at selected candidates | Explain overflow effects; production no-overflow/saturation checks remain required. |
| C. Accumulator guard (optional) | 33/34 bits versus the 35-bit base at W=16 | Separate no-overflow proof and measured PPA experiment; does not block the base. |
| D. Frequency schedule (optional) | Frequency B versus production A at W=16 | Separate scale/precision experiment; does not block the base or silently change expected codes. |
| E. Format sensitivity (outside base) | `Q1.(W-1)` coefficients | Requires explicit scope activation; never fold it into production Q2.14 claims. |

### Required result row

```text
git_commit
stimulus_manifest_sha256
vector_manifest_sha256
W_common, F_data, F_coeff
rounding_mode, overflow_mode
W_product, W_acc_time
fft_mode, fft_stage_widths, W_acc_freq, ifft_scale
sqnr_time_db, sqnr_freq_db, sqnr_cross_db
max_abs_acc_time, max_abs_acc_freq
internal_overflow_count, output_saturation_count
valid_start, valid_len, latency_samples, latency_cycles
vector_match_time, vector_match_freq
area_um2, fmax_mhz, power_status
```

PPA fields are populated only after the corresponding RTL candidate has 100%
vector matching; `power_status` distinguishes annotated workload power from an
unannotated estimate.

This is a lifecycle result record, not a requirement to invent future evidence
during the numerical sweep. F1 source hashes identify the float references;
the final expected-vector manifest hash is added after T22 export. Unknown
RTL latencies are omitted until measured in F3, and matching/PPA statuses are
explicitly not-run until their gates execute. A manifest's own digest remains
external to that manifest to avoid a self-referential hash.

### Acceptance rule

A candidate is numerically acceptable only when:

- `SQNR_time >= 40 dB` and `SQNR_freq >= 40 dB`;
- `SQNR_cross >= 40 - 20 log10(2) dB` (about 33.98 dB, 34 dB nominal) between
  the time and frequency FXP outputs, per the ADR-0005 cross-domain amendment;
- zero internal overflow on the canonical frame and the edge-case checks
  (the `sys_corners` sets of #15 plus the directed arithmetic checks above);
- zero canonical output saturation events;
- float-to-FXP alignment follows the manifest.

After numerical acceptance, F3 additionally requires serial RTL to match the
generated fixed-point expected vectors exactly in each domain before any
optimization is accepted.

Production is fixed to `W_common=16`, `Q2.14`. Report the smallest width that
passes the numerical sweep in both domains as a measured frontier, not as an
automatic replacement for production. Serial matching is the subsequent F3
gate, not a prerequisite for completing the F2 numerical sweep.

If the production candidate fails SQNR or overflow/saturation gates, diagnose
and correct the internal arithmetic/scaling, then repeat the evidence. If a
format change is necessary, record and approve that change before regenerating
production artifacts. Never silently widen the external format or lower the
SQNR threshold. Optional experiments cannot delay acceptance of a passing
production-A Q2.14 candidate merely because their results are unfinished.

## SQNR Frame and Stability Check

The canonical frame is the accepted #15 stimulus: 1024 symbols, 2048 input
samples, 2055 full causal output samples. Before accepting a width, compute the
SQNR over the full frame and over each half; if either half differs from the
full-frame value by more than 0.5 dB, extend the frame to 4096 symbols and
repeat the sweep row. This check keeps the accepted frame while catching an
unstable estimate near the 40 dB threshold.

## Manifest Fields

Normative schema: `docs/contracts/vector-manifest-schema.md` (§2 FXP policy
fields, §5 common format, §6 sign extension). The example below is
non-normative and must match the schema. The vector manifest extends the #15
fields with the active FXP policy:

```text
W_common, F_data, F_coeff
rounding_mode, overflow_mode
W_product, W_acc_time
fft_mode, fft_stage_widths, W_acc_freq, ifft_scale
latency_samples, latency_cycles
valid_start, valid_len
component_sign_extension: sign_extend_to_16
```

(`latency_time, latency_freq` in earlier wording are aliases of
`latency_samples, latency_cycles`; the schema names are canonical.)

Production packs signed 16-bit `Q2.14` components directly. Diagnostic
sub-16-bit exports use sign extension; above-16-bit sweep candidates remain
model-side results unless an explicitly separate record format is approved.
They must never be truncated into production records. See the normative
vector lifecycle and schema for F1 references, F2 expected codes, and F3
variant metadata; unknown latencies are never invented at F1/F2.

## Relationship to SQNR, Area, Timing, and Vector Matching

- **SQNR:** the 40 dB threshold is a measured criterion; report time and
  frequency separately and require the production `Q2.14` candidate to pass
  in both, with overflow and saturation counters visible. Report the
  cross-domain SQNR next to them as the time/frequency correspondence
  evidence.
- **Area and timing:** wider words widen multipliers, adders, registers, and
  coefficient storage; RNE and saturation add low-order logic. Measure them in
  the synthesized candidate with identical OpenLane settings, not from bit
  counts.
- **Vector matching:** the generated expected vector is the executable numeric
  contract; its manifest carries every policy field, and the hash proves that
  the RTL and the simulator consumed the same contract.

## Base-scope amendment (accepted 2026-10-02)

The base is production Q2.14, RNE, explicit saturation, a 35-bit conservative
time accumulator, frequency baseline A and the diagnostic RNE width sweep.
Truncation/wrap comparisons, 33/34-bit guard experiments and frequency B are
optional follow-ups, undertaken only with capacity after base evidence.
Their absence does not block F2, F3 or F4. Q1 sensitivity and the communications
annex are outside the base; runtime-reloadable coefficients are not requested.
Activating an experiment does not automatically authorize adopting its numeric
policy in production or mixing it into the architecture-only PPA ranking.

## Cross-domain amendment (accepted 2026-10-06)

The revised assignment asks to verify the correspondence of results between
the time and frequency versions. ADR-0005 defines the metric and its
rationale; this contract fixes how F2 measures it:

- `SQNR_cross = 10 log10(sum(|y_float|^2) / sum(|y_time_fxp - y_freq_fxp|^2))`
  over the full causal 2055-sample window, with decoded production outputs at
  the same absolute indices and the common float reference as signal power.
- Production `Q2.14` must reach `SQNR_cross >= 40 - 20 log10(2) dB` (about
  33.98 dB, 34 dB nominal) on the canonical frame. This is the bound implied
  by both domains passing 40 dB, so a failure points to inconsistent
  measurement inputs (window, alignment or reference) rather than a new
  precision target.
- The three `sys_corners` frames report `sqnr_cross_db` as diagnostics without
  a threshold, like their per-domain SQNR. Diagnostic sweep widths may report
  it too; only production W=16 is gated.
- T21 measures it on the accepted FXP models and records `sqnr_cross_db` in
  the result row. Per-domain vector manifests do not carry it, because it
  compares two domains. F3 inherits it through exact per-domain matching.
- Per-domain SQNR, overflow/saturation gates and the rule that time and
  frequency codes need not be bit-identical are unchanged.

## Production-A integer freeze amendment (proposed 2026-10-07, T20 #44)

Status: proposed. It records the integer operations of the T20 FXP models
(`sim/python/fxp.py`) and fills the "Frequency arithmetic freeze" list above.
It becomes accepted when the frequency co-designer (@JRondon23, owner of the
FFT schedule) signs off the frequency part and the time-arm review
(@iledesma08) signs off the time part. Until then T21 does not accept sweep
rows. It changes no accepted decision: production stays `Q2.14`, RNE,
explicit saturation, the 35-bit time accumulator and frequency baseline A,
with the widths of the Numeric Policy above.

### Scope and common rules

- One parameter, `W`, sets `F = W - 2` and every width below. Production is
  `W=16`. The diagnostic sweep uses the same rules at each tested `W`.
- **Constants follow the common width.** The RRC coefficients, the FFT
  twiddles and the stored `H[k]` table all use signed `Q2.(W-2)` with RNE from
  the exact value. A range violation in any constant is an error, never a
  saturation. Each sweep row therefore describes a datapath whose stored
  constants are all `W` bits wide, as in the time domain. Fixing the constants
  at 16 bits instead would mix widths in the frontier and cap the `W=18` row.
- Every reduction of fractional precision is an RNE right shift on the exact
  integer. RNE is odd-symmetric (`RNE(-v) = -RNE(v)`).
- Every listed width is checked on every value. A value outside it is an
  internal overflow and fails the candidate.

### Time domain

1. Input codes `x[n]` and coefficient codes `c[k]`, both `Q2.(W-2)`. History
   resets to zero; the full causal window is `y[0:2055]`.
2. Products `x[n-k] * c[k]` at full precision: `2W` bits, `2F` fractional
   bits (32/28 at `W=16`).
3. Accumulation in ascending tap order `k = 0..7` in a `2W+3`-bit accumulator
   (35 bits) with no intermediate rounding. Every partial sum is checked.
4. One output cast: RNE right shift by `F`, then saturation to `W` bits.

On the accepted stimulus every input component is `0` or `+/-2^F`, so every
accumulator is a multiple of `2^F`. The output cast drops only zero bits and
the time FXP output is the exact integer convolution. Its error is coefficient
quantization alone. This is the arithmetic reason no RNE tie is reachable in
the time domain (item 7 of Saturation and overflow).

### Frequency domain (forced-50% OLS, #14 D1)

1. **Framing.** Unchanged from #14: frame `b` is `x[8b-8 : 8b+8]` with eight
   zero history samples before `x[0]`, 257 blocks, emit `z[8:16]`, trim to
   2055 outputs. Frame components are `W` bits.
2. **Forward FFT16.** Radix-2 decimation in frequency, unscaled, natural-order
   input, four stages with spans `8, 4, 2, 1`. Butterfly on `a = x[j]`,
   `b = x[j+span]` within each group: `u = a + b`, `v = RNE_F((a - b) * T[k])`
   with `k = j * 16 / (2 * span)`. The output is in bit-reversed order.
3. **Twiddles.** `T[k] = exp(-j 2 pi k / 16)`, `k = 0..7`, in `Q2.(W-2)`.
   At `W=16`: real `[16384, 15137, 11585, 6270, 0, -6270, -11585, -15137]`,
   imaginary `[0, -6270, -11585, -15137, -16384, -15137, -11585, -6270]`.
   Products with `T[0] = 1` and `T[4] = -j` are exact, so an RTL may replace
   those multipliers with wiring and negation without changing any code.
4. **Forward widths.** Stage `s` values (`u`, `v`) fit `W + s` bits with `F`
   fractional bits: `W, W+1, W+2, W+3, W+4` = `fft_stage_widths`. The twiddle
   product is formed at full precision and narrowed by RNE (shift `F`) into
   the stage width; these are the only forward narrowing points.
5. **`H[k]`.** The exact DFT16 of the quantized coefficient codes zero-padded
   to 16, then one RNE to `Q2.(W-2)`. Bin `k` keeps standard DFT numbering
   (`k=0` is DC, #14 Complex FFT and Packing Contract). The table is stored at
   bit-reversed addresses, matching the order in which the forward transform
   delivers `X[k]`; this is an address mapping, not a different bin
   definition. At `W=16`, natural order:
   real `[22948, 4532, -21547, -11912, 11474, 7128, -685, 968, 0, 968, -685,
   7128, 11474, -11912, -21547, 4532]`, imaginary `[0, -22783, -8925, 17827,
   11474, -4763, -1653, -193, 0, 193, 1653, 4763, -11474, -17827, 8925,
   22783]`.
6. **Spectral product.** `Y[k] = X[k] * H[k]` at full precision with `2F`
   fractional bits, declared `2(W+4)+1` bits (41 at `W=16`). No narrowing:
   this is the full-precision product of baseline A.
7. **Inverse FFT16.** Radix-2 decimation in time, unscaled, bit-reversed
   input, natural-order output, four stages with spans `1, 2, 4, 8`. Butterfly:
   `v = RNE_F(b * conj(T[k]))`, then `a + v` and `a - v`, with
   `k = j * 16 / (2 * span)`. Stage `s` values, including `v`, fit
   `2(W+4)+1+s` bits with `2F` fractional bits; the last stage width is
   `W_acc_freq = 2(W+4)+5` (45 at `W=16`). The twiddle-product RNE is the only
   inverse narrowing point.
8. **Scale and output cast.** The forward transform has gain 1 and the
   unscaled inverse has gain 16. The division by 16 is an exact move of the
   binary point (`2F` to `2F+4` fractional bits), applied exactly once; then
   one RNE right shift by `F+4` (18 at `W=16`) and saturation to `W` bits.
   `ifft_scale = divide_by_16_then_cast_to_Q2.14`.

The model implements the RNE narrowings and the explicit saturations with
`fxpmath` (`rounding='around'`, `overflow='saturate'`). Because `fxpmath`
rounds through float64, an integer narrowing first subtracts an even
multiple of the rounding step so the rounded operand stays exact at every
width. The integer results are the same as an exact RNE shift.

`twiddle` and `H[k]` integers, all widths and per-stage ranges are also
recorded machine-readably in `sim/python/artifacts/t20-fxp/evidence_manifest.json`.
`traces.json` holds per-stage integer traces (time outputs 0, 7, 1024, 2054;
frequency blocks 0, 1, 128, 256) for stage-by-stage RTL comparison.

### Scope of the stage widths and directed checks

The `W+s` stage widths bound the accepted stimulus alphabet (components in
`{0, +/-1}`) with headroom: at `W=16` the forward stages need 17/18/19/19 bits
against 17/18/19/20 declared, the spectral product 33 against 41 and the
inverse stages at most 34 against 42-45. They are not a worst-case bound for
arbitrary full-scale `Q2.14` complex frames: a complex twiddle rotation can
grow one component by up to `sqrt(2)` (the first forward stage already
reaches `2 sqrt(2)` with QPSK input). Therefore:

- The canonical frame and the three `sys_corners` frames are the overflow
  gate, as in the Acceptance rule.
- Directed arithmetic checks with arbitrary full-scale values target the
  quantizer, rounding and saturation primitives and the time MAC, where the
  bound holds.
- A full-scale adversarial FFT frame is a negative control that proves the
  overflow detector fires. It is not a candidate gate.
- Adding a guard bit per stage would change `fft_stage_widths` and requires
  its own amendment.

### RNE tie reachability

Enumerated at `W=16` over the canonical frame and the three `sys_corners`
frames, which are deterministic and form the reachable set item 7 defines:

| Domain | Narrowing point | Operations | Inexact | Ties |
| --- | --- | --- | --- | --- |
| Time | output cast | 16440 | 0 | 0 |
| Frequency | forward twiddle products | 65792 | 0 | 0 |
| Frequency | inverse twiddle products | 65792 | 3706 | 0 |
| Frequency | output cast | 16440 | 3653 | 0 |

No tie is reachable, so no exact-tie MUST check applies to the frames. The
time reason is arithmetic (above). In the frequency domain the
zero-inserted input puts every nonzero sample on an even index, and every
forward twiddle product is exact. The inverse and output ties are absent by
enumeration. RNE tie behaviour stays covered by directed tests on the
rounding primitive. A test re-enumerates the ties, so a schedule change that
makes one reachable fails and turns its exact-rounding check into a MUST.

### T20 measurement (production `W=16`, informational; T21 owns acceptance)

| Frame | `sqnr_time_db` | `sqnr_freq_db` | `sqnr_cross_db` | Overflow | Output saturation |
| --- | --- | --- | --- | --- | --- |
| canonical | 91.16 | 88.95 | 89.29 | 0 | 0 |
| corner_repeat | 93.46 | 93.46 | identical codes | 0 | 0 |
| max_alternation | 93.44 | 93.44 | identical codes | 0 | 0 |
| single_symbol_perturbation | 93.45 | 93.43 | 114.31 | 0 | 0 |

Split halves of the canonical frame stay within 0.5 dB of the full-frame
value in both domains.

## Open Items

- The PPA ranking rule is deferred to #18 (D8).
- Optional experiments have no blocking edges into the base phases. Any
  production adoption requires its own evidence and recorded policy decision.
- The frequency arithmetic freeze is proposed in the T20 amendment above. T21
  accepts sweep rows only after its sign-off.

## References

- Research: `docs/contracts/fxp-common-width-16.md` (research branch
  `research/fxp-common-width`).
- RRC coefficient contract: `docs/contracts/rrc-coefficient-contract-13.md`.
- Frequency block contract: `docs/contracts/frequency-block-contract-14.md`.
- QPSK stimulus contract: `docs/contracts/qpsk-stimulus-15.md`.
- ADR-0001, ADR-0002, ADR-0004, ADR-0005, ADR-0006, and `CONTEXT.md`.
