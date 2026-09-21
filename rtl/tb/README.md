# rtl/tb — testbenches with vector matching

TBs for all 4 variants (2× serial + 2× opt) against `sim/vectors/`.
Each TB: reads vectors, compares sample by sample, reports pass/fail with a log.

`rrc_placeholder_tb.sv` is the pre-F1 smoke harness. It checks the shared
registered stream shell and confirms the generated-vector directory is
available; real vector matching begins in F3.
