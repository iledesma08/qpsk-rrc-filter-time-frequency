# rtl/freq_serial — frequency-domain filter, serial version

Run the T03 streaming shell test from the repository root:

```bash
bash rtl/freq_serial/run.sh
bash rtl/freq_serial/run.sh --data-width 12 --spc 2
```

`freq_serial_filter.sv` currently wraps the shared elastic transport shell:
`valid`/`ready`, packed `{Q,I}`, parameterized width/SPC, and synchronized reset
release from one wrapper-owned `rrc_reset_sync` instance. It forwards codes
unchanged; no FFT, multiply, IFFT or OLS engine runs.
Fixtures are generated under `.build/rtl/freq_serial/`, not `sim/vectors/`.

The actual serial frequency-domain implementation is T32 (`U=1`). Block
parameters are exposed with package defaults FFT16/H8/discard8/emit8. Emit
defaults derive from the wrapper's FFT/discard parameters, and inconsistent
tuples fail at simulation time zero. These are structural checks, not an engine.
The revised assignment fixes the hop-8 (50% overlap) baseline; no alternative
schedule is planned (`docs/contracts/frequency-block-contract-14.md`).
See `rtl/common/README.md` and `rtl/tb/README.md` for design, tests and evidence.
Real RRC matching, 257-block cadence checks and timing/PPA remain unrun.

Production uses the accepted Q2.14 interface (`W_common=16`, `F=14`); narrower
shell fixtures are diagnostic, and T03 implements no fractional arithmetic.
Numerical validation and T22's frozen coefficient export remain pending.
The generic TB handles explicit flush/padding/raw counts with synthetic frames;
the real 257-block schedule, latency and II belong to T32/T33 (#49/#50).
Target-specific physical configurations and runs belong to T43 (#54): SLOW
10 MHz (100 ns) main, FAST 100 MHz (10 ns) secondary. Prepare both; secondary
execution follows measured pilot capacity. The skeleton JSON's 10 ns clock and
the TB clock are setup, not principal-target timing validation or PPA evidence
for #55.
