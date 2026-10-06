# Common SQNR contract for both domains

**Status:** accepted, extended by contracts. Normative: `docs/contracts/fxp-policy-16.md` + `docs/contracts/qpsk-stimulus-15.md` + `docs/contracts/rrc-coefficient-contract-13.md` (as refined by #16). This ADR defines only the SQNR formula, the >=40 dB bar in both domains, the cross-domain SQNR gate (amended 2026-10-06), and float equality `rtol=1e-10`/`atol=1e-12`; sweep policy and stimulus frame live in the contracts.

SQNR is measured over the same deterministic QPSK frame for both filter
domains, aggregating I and Q power:

```text
SQNR = 10 log10(sum(|y_float|^2) / sum(|y_float - y_fxp|^2))
```

The comparison uses the common emitted output frame, aligned for model
latency, and excludes samples produced only by implementation padding.
Float time/frequency equality uses `rtol=1e-10` and `atol=1e-12`.

Amendment accepted 2026-10-02: production uses signed `Q2.14` (`W_common=16`)
for input/output components and stored RRC coefficients. The width sweep
remains required evidence of the precision frontier, but does not automatically
replace this declared production format with the smallest passing width.
The `Q2.14` candidate must still meet 40 dB in both domains and the overflow/
saturation gates; changing the production format requires a recorded decision.
The earlier smallest-width selection rule is superseded by this amendment.

Each RTL matches its own integer FXP model exactly. Optimized variants remain
bit-exact with their same-domain serial baseline under the frozen numeric
policy; time and frequency FXP codes need not be bit-identical to each other.

Cross-domain amendment accepted 2026-10-06 (#74): the revised assignment asks
to verify the correspondence of results between the time and frequency
versions. Their float references are already equal within the tolerances
above. Their FXP codes differ by quantization, so the correspondence is
measured as a cross-domain SQNR over the same full causal window:

```text
SQNR_cross = 10 log10(sum(|y_float|^2) / sum(|y_time_fxp - y_freq_fxp|^2))
```

`y_time_fxp` and `y_freq_fxp` are the decoded production outputs of each
accepted FXP model at the same absolute sample indices. `y_float` is the
common float reference, so the metric has one reference power for both
domains instead of treating either FXP domain as the reference.

The threshold is `SQNR_cross >= 40 - 20 log10(2) dB` (about 33.98 dB, reported
as 34 dB nominal). It is the bound implied by the per-domain gate: if each
domain error is at most 1% of the reference RMS (40 dB), the triangle
inequality limits their difference to 2% (33.98 dB). Requiring 40 dB between
domains would be stricter than the per-domain gate and could fail with both
domains passing. A failure therefore indicates inconsistent measurement
inputs, such as a different window, alignment or reference, rather than a new
precision requirement. The measured value is reported as the correspondence
evidence the assignment asks for.

The gate applies to production Q2.14 on the canonical frame. The three
`sys_corners` frames report `SQNR_cross` as diagnostics without a threshold,
like their per-domain SQNR. It is measured on the accepted FXP models in F2
(T21). Because each RTL matches its own FXP model exactly, F3 inherits the
result without a separate RTL computation. The per-domain 40 dB gate and
the bit-exact matching rules above are unchanged.
