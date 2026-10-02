# Common SQNR contract for both domains

**Status:** accepted, extended by contracts. Normative: `docs/contracts/fxp-policy-16.md` + `docs/contracts/qpsk-stimulus-15.md` + `docs/contracts/rrc-coefficient-contract-13.md` (as refined by #16). This ADR defines only the SQNR formula, the >=40 dB bar in both domains, and float equality `rtol=1e-10`/`atol=1e-12`; sweep policy and stimulus frame live in the contracts.

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
