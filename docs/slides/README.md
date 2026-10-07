# docs/slides — final presentation

Time vs frequency contrast + PPA table + lessons learned + actual vs planned Gantt (T50).

Upload the final PDF + source (pptx/keynote/latex) before the `v1.1-close` tag.

## Outline (T50)

1. Architecture: time-domain (`S4P1/S8P1`) vs frequency-domain (`U4/U8`), each contrasted with its serial baseline. Additional pipeline-depth and folded experiments are extension-only.
2. SQNR vs diagnostic width (W): sweep frontier + measured production Q2.14 SQNR in both domains, with overflow/saturation evidence, plus the cross-domain SQNR as time/frequency correspondence evidence (canonical gate, `sys_corners` diagnostics).
3. Six-architecture PPA comparison: declared SLOW serial / FAST optimized main goals, prepared paired clock runs and explicit statuses, matched-target Pareto and serial deltas. More architecture variants are extension-only; additional target runs are not additional architectures.
4. Lessons learned from completed work, including the OLS H8 schedule (fixed by the revised assignment), Q2 precision choice, and II vs fmax trade-offs. Label unmeasured H9/Q1/folded alternatives as discussion only.
5. Actual vs planned Gantt + demo.

The architecture part reuses the system block diagram and stage descriptions
in `docs/block-diagram.md` (T52).

Do not wait for optional Booth/ROM, narrow-guard or FFT-B experiments to finish
the base presentation. Include them only when explicitly activated and backed
by evidence, clearly separate from the six-architecture base. Q1.15 and the
AWGN/BER annex are outside base scope, not mandatory slide material.
