# FXP Common-Width Research

Research ticket: [#16](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/16)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-21

Scope: recommend the fixed-point numeric policy for the QPSK RRC time-domain and frequency-domain filters. This is research only. It does not implement the simulator, vectors, RTL, or an ADR.

## Executive Recommendation

Use one explicit signed two's-complement component format for the common data and coefficient interface:

```text
W-bit signed Q2.(W-2)
F = W - 2 fractional bits
real_value = stored_integer * 2^(-F)
```

This format represents the project's component values `-1` and `+1` exactly. Sweep `W` over `8, 10, 12, 14, 16, 18` and select the smallest `W` for which both domains reach `SQNR >= 40 dB` under the same stimulus, valid output window, and quantization contract.

Use these arithmetic defaults:

- Round to nearest, ties to even (RNE) when reducing fractional precision.
- Saturate only at an explicit narrowing/output boundary; do not silently saturate an internal accumulator.
- Use full-precision signed products.
- Use a wider accumulator. For the eight-tap time-domain MAC, start with `W_acc_time = 2*W + ceil(log2(8)) = 2*W + 3` bits and `2*F` fractional bits. This is a conservative bound, not a claim that it is the minimum implementation width.
- For frequency-domain FFT/IFFT arithmetic, derive internal widths from the selected FFT scaling schedule. Record those widths separately from the common `W`.
- Treat any internal accumulator overflow as a failed candidate. Count output saturation events and reject the canonical candidate if any occur.
- Generate vectors from the same fixed-point model used for SQNR. Compare packed I/Q integer codes exactly in RTL; do not compare re-converted floating-point values.

The recommendation is deliberately a policy, not a preselected winning width. The actual `W` must be established by the measured sweep after the team freezes the stimulus and frequency block contract.

## Existing Project Constraints

These are facts from the repository, not new recommendations:

- The float64 Python simulator is the correctness reference for coefficients, golden vectors, and SQNR ([ADR 0001](../adr/0001-python-float-golden-simulator.md)).
- SQNR is the aggregated complex I/Q metric over a common deterministic frame and aligned valid output window ([ADR 0005](../adr/0005-common-sqnr-contract.md)). The project already states that the smallest common FXP width reaching at least 40 dB in both domains is selected.
- Packed vectors use one 32-bit record `{Q[15:0], I[15:0]}` ([ADR 0004](../adr/0004-packed-external-vectors.md)). The numeric manifest still needs to state the active `W`, binary point, and sign extension convention.
- Serial RTL must reach 100% vector matching before PPA optimization ([ADR 0002](../adr/0002-serial-rtl-before-optimization.md)).
- OpenLane 2, Sky130, and a 100 MHz primary target are the accepted PPA flow constraints; 10 MHz is a labelled fallback ([ADR 0006](../adr/0006-systemverilog-openlane-ppa-flow.md)).
- The seed, exact QPSK frame, valid output window, and frequency overlap-save/overlap-add details are still open in map #12. The FXP sweep cannot be considered final until those inputs are frozen.

## Source-Backed Facts

### Fixed-point representation

AMD documents `ap_fixed<W,I,...>` as a signed or unsigned fixed-point word with total width `W`, integer width `I` including the sign bit, and `W-I` fractional bits. Its quantization and overflow behavior are explicit type parameters, not properties to leave implicit. Source: [AMD UG1399, C++ arbitrary precision fixed-point types](https://docs.amd.com/r/en-US/ug1399-vitis-hls/C-Arbitrary-Precision-Fixed-Point-Types).

The Accellera SystemVerilog material states that a packed array declared `signed` is signed when viewed as a whole, while a part-select is unsigned unless it is explicitly cast. Source: [Accellera SystemVerilog draft](https://accellera.org/images/eda/vlog-pp/att-0614/01-SystemVerilog_draft7.pdf). The current standard is listed by Accellera as [IEEE 1800-2023](https://accellera.org/downloads/ieee).

### Product, sum, and FIR growth

Fixed-point addition requires aligned binary points and sign extension. A full-precision product retains the sum of the operand fractional lengths. A later cast is where rounding or overflow can occur. Source: [MathWorks, Fixed-Point Arithmetic](https://www.mathworks.com/help/fixedpoint/gs/fixed-point-arithmetic-tutorial.html).

AMD's FIR Compiler documentation says that multiplication and addition create bit growth, that the full-precision accumulator is wider than the input, and that a fixed filter's growth can be derived from the base-2 logarithm of the sum of the absolute coefficient values. It also states that data and coefficient fractional widths add in the product and are reduced by output rounding. Source: [AMD PG149, Output Width and Bit Growth](https://docs.amd.com/r/en-US/pg149-fir-compiler/Output-Width-and-Bit-Growth).

The exact project-specific accumulator width cannot be taken from the tap count alone. It depends on operand ranges, coefficient normalization, the reduction tree, and whether intermediate casts occur. The conservative `2*W+3` time-domain starting point above avoids relying on an optimistic coefficient bound. A later reduction is acceptable only after an exhaustive no-overflow check and a measured PPA comparison.

### Rounding and overflow

MathWorks documents the following relevant behaviors:

- Rounding introduces quantization error and computational noise.
- Convergent rounding is nearest with ties to the even stored value and is unbiased with respect to ties.
- Truncation toward zero and floor/truncation have directional bias for signed data.
- Rounding and saturation settings can require additional arithmetic and comparison hardware.

Sources: [MathWorks, Choose a Rounding Mode](https://www.mathworks.com/help/fixedpoint/ug/choose-a-rounding-mode.html), [MathWorks, Rounding Modes](https://www.mathworks.com/help/fixedpoint/ug/rounding.html), and [MathWorks HDL Coder rounding and saturation guidance](https://www.mathworks.com/help/hdlcoder/ug/guidelines-for-using-rounding-modes-for-fixed-point.html).

AMD documents saturation and wrap-around as distinct overflow modes. Its fixed-point documentation also notes that saturation needs extra logic, while wrap-around is the natural bit-width reduction behavior. Source: [AMD UG1399, Overflow Modes](https://docs.amd.com/r/en-US/ug1399-vitis-hls/Overflow-Modes).

These sources establish the available behaviors. They do not select a policy for this project. The project should specify every narrowing operation explicitly because relying on a language or library default would make Python and SystemVerilog vector matching fragile.

### FFT-specific growth

AMD's fixed-point FFT documentation describes signed two's-complement input and phase-factor data, and exposes scaled, unscaled, and block-floating output choices. It also describes truncation at FFT ranks as a configurable behavior. Source: [AMD FFT documentation](https://docs.amd.com/r/2021.2-English/ug1483-model-composer-sys-gen-user-guide/Fast-Fourier-Transform-9.1).

The AMD FFT product guide states that the IFFT does not implement the `1/N` scaling automatically. A frequency-domain implementation must therefore record both its stage scaling and its final normalization. Source: [AMD PG109, Algorithm](https://docs.amd.com/r/en-US/pg109-xfft/Algorithm).

For a radix-2 16-point transform, four butterfly stages exist. An unscaled stage can grow by one bit per stage in the worst case. This is a mathematical consequence of an add/subtract butterfly and is a project calculation, not a vendor promise about a particular FFT implementation.

### Width and PPA

AMD describes arbitrary-precision types as enabling smaller hardware operators and potentially higher clock frequencies, and warns that unnecessarily wide datapaths use more resources and have longer delays. Source: [AMD, Arbitrary Precision Data Types](https://docs.amd.com/r/2023.2-English/ug1399-vitis-hls/Arbitrary-Precision-AP-Data-Types).

MathWorks' HDL guidance likewise documents extra hardware for non-floor rounding and saturation. This establishes why RNE and saturation must be included in PPA measurements rather than treated as free simulation-only behavior.

OpenLane 2's documented Classic flow produces final metrics and post-PnR timing reports, and uses `CLOCK_PERIOD` as a timing constraint. Sources: [OpenLane 2 newcomer flow](https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html), [OpenLane 2 Classic flow](https://openlane2.readthedocs.io/en/stable/reference/flows.html), and [OpenLane 2 timing closure](https://openlane2.readthedocs.io/en/stable/usage/timing_closure/index.html).

The sources support the direction of the trade-off, but they do not predict this design's area, timing, or power. Those values must come from like-for-like OpenLane runs after vector matching passes.

## Recommended Numeric Policy

### Common data and coefficient words

Use signed two's-complement packed words and state the binary point in the manifest:

| Quantity | Recommended format | Reason |
| --- | --- | --- |
| QPSK I/Q input | `Q2.(W-2)` | `+1` and `-1` are exactly representable; range is approximately `[-2, +2)`. |
| RRC coefficient | `Q2.(W-2)` initially | Same total width and binary point in both domains; one coefficient table and one quantization rule. |
| Common width sweep | `W = 8, 10, 12, 14, 16, 18` | Coarse enough to expose the threshold without making the sweep expensive. Extend to 20 if no candidate reaches 40 dB. |

For a real value `x`, quantize with an integer scale factor:

```text
q_unbounded = round_even(x * 2^F)
q = min(max(q_unbounded, -2^(W-1)), 2^(W-1)-1)
```

The coefficient quantizer should fail the run or record a range violation if saturation occurs while loading the known RRC coefficients. Saturating a coefficient silently would change the filter design rather than merely quantize it.

Using `Q1.(W-1)` for coefficients could gain one fractional bit because normalized coefficients are usually below `+1`, but it creates a second binary-point convention. Include it only as an explicitly labelled sensitivity experiment. Do not compare it to common `Q2.(W-2)` and call the result a pure width comparison.

### Products and the time-domain accumulator

With `W_d = W_c = W` and `F_d = F_c = F`:

```text
product width       W_p   = W_d + W_c = 2W
product frac bits   F_p   = F_d + F_c = 2F
time accumulator     W_acc = W_p + ceil(log2(8)) = 2W + 3
time accumulator     F_acc = 2F
```

The accumulator should add full-precision products without rounding between taps. After the eight-tap reduction, cast once to the output format using RNE and saturation. This prevents per-tap truncation from accumulating avoidable noise and makes the quantization boundary easy to identify in the vector manifest.

The `2W+3` width is conservative. AMD's coefficient-sum growth rule can justify a narrower accumulator for a fixed, known coefficient set, but that optimization should be a separate experiment. It must retain an overflow assertion and be compared against the conservative baseline.

### Frequency-domain internal widths

The common width is the width of the input samples and stored/filter coefficients, not a claim that every FFT wire is `W` bits.

For an unscaled 16-point radix-2 baseline, use this conservative derivation for a component width `B` at each stage:

```text
forward FFT stage widths:  W, W+1, W+2, W+3, W+4
complex pointwise product: 2*(W+4) + 1 bits
unscaled IFFT growth:      four additional add/subtract guard bits
final normalization:        divide by 16, then cast to Q2.(W-2)
```

The extra `+1` on the complex product is for the real/imaginary add or subtract after two component products. This is a safe width derivation for the stated unscaled structure, not a required microarchitecture. A scaled FFT can keep narrower wires by shifting at stages, but every shift is a quantization boundary and must be measured.

Recommendation for the first frequency sweep:

1. Baseline A: grow one guard bit per radix-2 stage, retain full-precision products, apply the explicit `1/16` IFFT normalization, and round only at declared narrowing points.
2. Baseline B: shift by one bit at each FFT/IFFT stage to bound the component width, recording the total scale and using the same RNE rule.
3. Compare A and B at the same common `W`. Keep the one that reaches the SQNR contract with the better measured PPA, not the one with the more convenient internal width.

The exact frequency accumulator and FFT widths belong in the frequency block contract from issue #14. They must not be hidden inside the label `W`.

### Rounding

Use RNE at every intentional reduction in fractional precision:

- coefficient quantization;
- frequency-domain FFT stage scaling, if stage scaling is selected;
- complex product reduction, if the product is narrowed before the IFFT;
- final output cast.

Keep a truncation-toward-zero variant in the sweep as a low-cost comparison. Do not use an implicit arithmetic right shift as the project definition of signed truncation: for negative two's-complement values, an arithmetic shift has floor-like behavior. The Python model and RTL must use the same explicitly named operation.

RNE is recommended because it removes the directional bias of truncation at a modest hardware cost. The cost is real: include the rounding adder and any tie logic in synthesis and timing results.

### Saturation and overflow

Use this hierarchy:

1. Input and coefficient quantizers: saturating conversion with a range assertion. A range violation is a test failure for the canonical coefficients/input contract.
2. Time and frequency accumulators: no wrap and no silent saturation. Make them wide enough, expose an overflow flag, and fail the candidate if it asserts.
3. Explicit narrowing/output cast: RNE followed by saturation. Count saturation events.
4. Canonical acceptance frame: require zero internal overflow and zero output saturation. If either occurs, increase the relevant width or change the declared scaling; do not hide it behind a high aggregate SQNR.
5. Diagnostic negative control: run wrap-around once to demonstrate its effect, but do not use it for the selected RTL contract.

This policy keeps saturation as a defined safety behavior at an interface while preventing internal overflow from being mistaken for acceptable quantization noise.

### Signed SystemVerilog discipline

The RTL should use explicit signed declarations and explicit sign extension before additions. Every part-select used in an arithmetic expression should be cast back to a signed type. Product, accumulator, and narrowed-output widths should be named parameters in the shared package or module interface. This is necessary because SystemVerilog's signedness rules apply differently to a whole packed array and to a part-select.

The testbench should compare the stored integer bit patterns after sign extension to the packed vector width. It should not depend on a simulator-specific conversion from a signed `logic` vector to an `integer`.

## Reproducible Sweep Matrix

### Inputs that must be frozen

The sweep is reproducible only if these values are recorded in a generated manifest:

| Field | Recommendation |
| --- | --- |
| Python/runtime | Pin the simulator environment already selected by the repository's toolchain research. |
| Float reference | Python float64, same RRC coefficients and same time/frequency block definitions. |
| QPSK generator | One named PRNG algorithm and integer seed; generate I and Q independently from `{-1, +1}`. |
| Frame | At least 4096 symbols for the canonical SQNR frame, plus deterministic edge-case frames. |
| Coefficient normalization | One documented normalization and coefficient ordering. |
| Frequency block | FFT length, hop, overlap, padding, scaling schedule, and final `1/N` normalization. |
| Alignment | A declared latency offset and the same valid output window for float and FXP. |
| Metric | ADR-0005 complex I/Q power formula, with no implementation-only padding. |
| Reproducibility | Git commit, dependency lock/version, manifest hash, vector hash, and policy fields. |

The seed and valid window are not currently fixed by the repository. The human team must choose them before accepting the final row of the sweep. A proposed default is a 4096-symbol PCG64 frame with a seed recorded as an integer in the manifest, but the numerical value of the seed is intentionally left for issue #15 rather than being silently chosen here.

### Matrix phases

Run the phases in this order to keep the result interpretable:

| Phase | Values | Purpose |
| --- | --- | --- |
| A. Common format | `W = 8,10,12,14,16,18`; `Q2.(W-2)` for data/coefficient; full accumulator; RNE and truncation-toward-zero | Find the width/rounding frontier without mixing FFT scaling or narrow accumulators. |
| B. Overflow behavior | On the best two A candidates: saturating narrowing and wrap-around diagnostic | Demonstrate that wrap is unacceptable and quantify any clipping. |
| C. Accumulator guard | For the best common `W`: `2W+1`, `2W+2`, and conservative `2W+3` bits; no intermediate narrowing in the time MAC | Measure whether a narrower accumulator overflows and whether guard bits affect SQNR or only PPA. Keep the smallest no-overflow choice. |
| D. Frequency schedule | For the selected common `W`: unscaled/grow-by-stage and one-bit-per-stage scaling, with all internal widths recorded | Separate common word precision from FFT scaling cost. |
| E. Format sensitivity | Optional `Q2` data plus `Q1.(W-1)` coefficients at the selected `W` values | Quantify the cost/benefit of a separate coefficient binary point; do not fold it into the common-width claim. |

The Cartesian product for phase A is 6 widths x 2 rounding modes = 12 configurations per domain. Phase B is a diagnostic subset. Phases C-E are conditional, so the final report remains small enough to inspect while still exposing the important policy choices.

### Required result row

Every configuration should produce one machine-readable row with at least:

```text
git_commit
stimulus_manifest_sha256
vector_manifest_sha256
W_common, F_data, F_coeff
rounding_mode, overflow_mode
W_product, W_acc_time
fft_mode, fft_stage_widths, W_acc_freq, ifft_scale
sqnr_time_db, sqnr_freq_db
max_abs_acc_time, max_abs_acc_freq
internal_overflow_count, output_saturation_count
valid_start, valid_count, latency_time, latency_freq
vector_match_time, vector_match_freq
area_um2, fmax_mhz, power_status
```

The PPA fields are populated only after the corresponding RTL candidate has 100% vector matching. `power_status` must distinguish annotated workload power from an unannotated estimate.

### Acceptance rule

A candidate is numerically acceptable only when all of the following hold:

- `SQNR_time >= 40 dB`;
- `SQNR_freq >= 40 dB`;
- zero internal overflow on the canonical frame and edge-case checks;
- zero canonical output saturation events;
- float-to-FXP alignment follows the manifest;
- serial RTL matches the generated fixed-point expected vectors exactly in both domains.

Select the lowest `W_common` accepted by both domains. If two policies tie at the same `W`, prefer the one with fewer narrowing points and simpler shared RTL. If no width in the proposed sweep passes, extend the sweep or revisit the frequency scaling contract; do not lower the SQNR threshold.

## Why the Smallest Common Width Is Fair and Useful

This is a project recommendation supported by the existing common-SQNR ADR:

- **It controls the precision variable.** Time and frequency are being compared as architectures, so both should receive the same external/sample/coefficient precision. Giving one domain a wider input or coefficient word would mix numerical quality with architectural quality.
- **It exposes the real architecture trade-off.** Once both domains meet 40 dB at the same `W`, differences in area, timing, and power are more attributable to convolution versus FFT filtering rather than to an undocumented precision advantage.
- **It prevents overfitting the frequency implementation.** The frequency path has more internal operations and may need guard bits, but it cannot meet the contract merely by using a wider external data word. Its internal growth must be visible in the accumulator/FFT fields and PPA results.
- **It is useful for RTL reuse.** A common input/coefficient format simplifies coefficient ROMs, vector manifests, testbench packing, and cross-domain debugging.
- **It does not ban legitimate internal width.** A MAC or FFT reduction is not an external precision choice. A wider accumulator preserves precision and range before the final cast; forcing it to equal `W` would create artificial overflow and penalize the architecture with the larger reduction.
- **It makes PPA honest.** Internal accumulator width is still synthesized, so its area and timing cost appears in OpenLane. The report must show both `W_common` and internal widths.

The fairness rule is therefore: common external quantization contract, architecture-specific full-precision internal arithmetic, explicit and measured narrowing/scaling, and one shared SQNR threshold.

## Relationship to SQNR, Area, Timing, and Vector Matching

### SQNR >= 40 dB

The SQNR threshold is a measured acceptance criterion, not something that can be guaranteed from `W` alone. RNE generally avoids the directional bias of truncation, but coefficient error, FFT stage rounding, scaling, final output casting, and the chosen valid window all contribute to the measured error. The sweep must therefore report time and frequency SQNR separately and select on the worse domain.

The canonical frame should also report overflow and saturation counts. A candidate can have a high aggregate SQNR while containing a few catastrophic wrapped samples; the explicit counters prevent that failure mode from being hidden.

### Area and timing

Increasing `W` widens multipliers, adders, registers, coefficient storage, and possibly vector ports. Increasing `W_acc` widens reduction adders and accumulator registers. RNE adds low-order-bit logic; saturation adds range checks and muxing. These costs can be different in time and frequency, so they must be included in the synthesized candidate rather than estimated from bit counts.

Use identical OpenLane 2, PDK, standard-cell library, clock target, source inclusion, and signoff/report extraction for every accepted width. Report area and signoff timing separately at 100 MHz, and use the 10 MHz result only as the documented fallback. Do not call a design faster because it meets a looser clock target.

### Vector matching

The generated expected vector is the executable numeric contract. Its manifest should include `W`, every fractional width, rounding, saturation, accumulator width, FFT scaling, final normalization, latency, and valid window. The vector hash then proves that the RTL and simulator consumed the same contract.

For `W < 16`, sign-extend each component into the existing 16-bit I/Q vector field. If the selected `W` is 16, the field is direct. If a future candidate exceeds 16, the vector record format must be revisited instead of truncating silently. This preserves the accepted packed-vector shape while making the active FXP width explicit.

## Human Decisions Still Required

The research recommendation does not make these decisions for the team:

- Freeze the QPSK PRNG algorithm, seed, symbol count, and edge-case frames in issue #15.
- Freeze the RRC coefficient normalization, coefficient order, and whether the coefficient peak is guaranteed below `+1` or only below `+2`.
- Accept or reject the recommended common `Q2.(W-2)` coefficient format versus a separate `Q1.(W-1)` coefficient sensitivity policy.
- Choose the exact FFT/IFFT implementation, overlap-save or overlap-add contract, hop, padding, latency, and valid output window in issue #14.
- Choose the frequency stage scaling baseline: unscaled/grow-by-stage, one-bit-per-stage scaling, or another explicitly measured schedule.
- Decide whether zero output saturation is a hard gate, as recommended here, or whether a bounded number of clipped samples is allowed. If relaxed, define the count and SQNR treatment before the sweep.
- Decide whether the conservative `2W+3` time accumulator is the frozen baseline or whether coefficient-sum analysis may reduce it before the first RTL implementation.
- Decide whether the optional coefficient-specific binary point is in scope for the official comparison or only for learning/sensitivity data.
- Freeze the vector manifest schema, including sign extension into the existing 16-bit fields.
- Select the exact PPA ranking rule when area, fmax, and power disagree. The FXP width should not be changed after seeing one preferred PPA axis without recording the trade-off.

## Resolution Status

This report was written before the decision contracts. Every item above is now
resolved; this table records where.

| Research item | Resolution |
| --- | --- |
| QPSK PRNG, seed, symbol count, edge cases | #15 `qpsk-stimulus-15.md`: `default_rng(2026)`, 1024 symbols, five fixed edge patterns, zero insertion, full causal window. |
| RRC normalization, order, coefficient peak | #13 `rrc-coefficient-contract-13.md`: discrete unit energy, ascending time order, `max(abs(h)) = 0.6894 < 1`. |
| Common `Q2.(W-2)` vs separate `Q1.(W-1)` coefficients | #16 D2: common `Q2.(W-2)`; `Q1.(W-1)` coefficients only as the labelled phase E sensitivity experiment; RRC D4 refined. |
| FFT/IFFT contract, hop, padding, latency, valid window | #14 D1/D2: forced-50% OLS (`N=16`, `H=8`, discard `z[0:8]`, emit `z[8:16]`), internal zero history, full causal window via #15. |
| Frequency stage scaling baseline | #16 D5: run baseline A (grow-by-stage) and baseline B (one-bit-per-stage) at the same `W`; the winner comes from the F4 measurements. |
| Zero output saturation as a hard gate | #16 D3 and acceptance rule: zero canonical output saturation and zero internal overflow are hard gates; wrap is a diagnostic only. |
| `2W+3` accumulator frozen or reducible | #16 D4: `2W+3` is the frozen baseline; `2W+1`/`2W+2` are a separate experiment with an overflow assertion. |
| Coefficient-specific binary point scope | #16 D2/D5: phase E sensitivity only, outside the common-width comparison. |
| Vector manifest schema and sign extension | #16 D7 and the Manifest section: fields frozen; sign-extend into the 16-bit packed fields when `W < 16`. |
| PPA ranking rule | #16 D8 (deferred) and #18 D7: Pareto front with gates and no arbitrary weights; the width is not changed after seeing one preferred axis without recording the trade-off. |

Two items keep execution-time components by design: the FFT core selection
belongs to F3, and the frequency scaling winner comes from the F4
measurements.

## Sources

### Primary external sources

- [AMD UG1399: C++ arbitrary precision fixed-point types](https://docs.amd.com/r/en-US/ug1399-vitis-hls/C-Arbitrary-Precision-Fixed-Point-Types)
- [AMD UG1399: overflow modes](https://docs.amd.com/r/en-US/ug1399-vitis-hls/Overflow-Modes)
- [AMD PG149: FIR output width and bit growth](https://docs.amd.com/r/en-US/pg149-fir-compiler/Output-Width-and-Bit-Growth)
- [AMD PG149: best precision fractional length](https://docs.amd.com/r/en-US/pg149-fir-compiler/Best-Precision-Fractional-Length)
- [AMD FFT fixed-point documentation](https://docs.amd.com/r/2021.2-English/ug1483-model-composer-sys-gen-user-guide/Fast-Fourier-Transform-9.1)
- [AMD PG109: FFT algorithm and IFFT scaling](https://docs.amd.com/r/en-US/pg109-xfft/Algorithm)
- [MathWorks: fixed-point arithmetic](https://www.mathworks.com/help/fixedpoint/gs/fixed-point-arithmetic-tutorial.html)
- [MathWorks: choose a rounding mode](https://www.mathworks.com/help/fixedpoint/ug/choose-a-rounding-mode.html)
- [MathWorks: rounding modes](https://www.mathworks.com/help/fixedpoint/ug/rounding.html)
- [MathWorks HDL Coder: rounding and saturation hardware guidance](https://www.mathworks.com/help/hdlcoder/ug/guidelines-for-using-rounding-modes-for-fixed-point.html)
- [Accellera IEEE standards listing](https://accellera.org/downloads/ieee)
- [Accellera SystemVerilog draft, signed packed arrays](https://accellera.org/images/eda/vlog-pp/att-0614/01-SystemVerilog_draft7.pdf)
- [OpenLane 2 newcomer flow and final metrics](https://openlane2.readthedocs.io/en/stable/getting_started/newcomers/index.html)
- [OpenLane 2 Classic flow](https://openlane2.readthedocs.io/en/stable/reference/flows.html)
- [OpenLane 2 timing closure](https://openlane2.readthedocs.io/en/stable/usage/timing_closure/index.html)

All external sources were accessed on 2026-09-21.

### Project sources

- [ADR 0001: Python float simulator as golden](../adr/0001-python-float-golden-simulator.md)
- [ADR 0002: serial RTL before optimization](../adr/0002-serial-rtl-before-optimization.md)
- [ADR 0004: packed external vectors](../adr/0004-packed-external-vectors.md)
- [ADR 0005: common SQNR contract](../adr/0005-common-sqnr-contract.md)
- [ADR 0006: SystemVerilog and OpenLane PPA flow](../adr/0006-systemverilog-openlane-ppa-flow.md)
- [Plan and Gantt, F2 FXP tasks](../plan-gantt.md)
- [Map #12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)
- [Issue #14: frequency block contract](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/14)
- [Issue #15: QPSK stimulus and valid output window](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/15)
