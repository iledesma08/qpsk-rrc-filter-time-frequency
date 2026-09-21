# Common SQNR contract for both domains

**Status: accepted**

SQNR is measured over the same deterministic QPSK frame for both filter
domains, aggregating I and Q power:

```text
SQNR = 10 log10(sum(|y_float|^2) / sum(|y_float - y_fxp|^2))
```

The comparison uses the common emitted output frame, aligned for model
latency, and excludes samples produced only by implementation padding. The
smallest common FXP width that reaches at least 40 dB in both domains is
selected. Float time/frequency equality uses `rtol=1e-10` and `atol=1e-12`.
