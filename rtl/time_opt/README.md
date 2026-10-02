# rtl/time_opt — time-domain filter, optimized version

The accepted reduced matrix is T-S4P1/T-S8P1 (T40-T41), built after the working
serial baseline. Each row needs RRC vector matching, FAST 100 MHz main-target
timing closure, and PPA evidence. SLOW 10 MHz is a secondary comparative target,
not a substitute for a failed FAST goal. Prepare both target runs and prioritize
them per `docs/adr/0006-systemverilog-openlane-ppa-flow.md`.

Run the placeholder smoke test from the repository root:

```bash
bash rtl/time_opt/run.sh
```
