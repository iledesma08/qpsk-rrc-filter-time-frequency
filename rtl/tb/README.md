# rtl/tb — testbenches with vector matching

TBs for all 4 variants (2× serial + 2× opt) against `sim/vectors/`.
Each TB: reads vectors, compares sample by sample, reports pass/fail with a log.

`rrc_placeholder_tb.sv` is the pre-F1 smoke harness. It checks the shared
registered stream shell and confirms the generated-vector directory is
available; real vector matching begins in F3.

The accepted testbench contract (handshake driving, latency from the manifest,
exact integer-code comparison, bubble and stall robustness tests) is in
`docs/contracts/rtl-streaming-17.md`. The placeholder harness is retired when
the parameterized vector-matching testbenches land.

Impulse check: `x[0] = impulse => y[0:8] = h` (first 8 outputs equal the
8-tap RRC impulse response, per the time-domain contract).
