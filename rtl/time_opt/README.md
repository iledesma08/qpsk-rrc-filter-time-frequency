# rtl/time_opt — time-domain filter, optimized version

The accepted reduced matrix is T-S4P1/T-S8P1 (T40-T41), built after the working
serial baseline. Each row needs RRC vector matching, 100 MHz timing closure
(10 MHz explicitly labelled fallback), and PPA evidence.

Run the placeholder smoke test from the repository root:

```bash
bash rtl/time_opt/run.sh
```
