# rtl/time_serial — time-domain filter, serial version

Run the T03 streaming shell test from the repository root:

```bash
bash rtl/time_serial/run.sh
bash rtl/time_serial/run.sh --data-width 8 --spc 4
```

`time_serial_filter.sv` currently wraps the shared elastic transport shell:
`valid`/`ready`, packed `{Q,I}`, parameterized width/SPC, and one wrapper-owned
`rrc_reset_sync` instance shared with future datapath state. It forwards codes
unchanged; it is not a time-domain filter.
The run verifies reset, exact codes, latency, bubbles and stalls using generated
fixtures in `.build/rtl/time_serial/`, not RRC goldens.

The actual one-MAC time-domain filter is T30 (`S=1`, SPC=1, II=8); the transport
shell's II=1 is not that baseline. See `rtl/common/README.md` for the shared
design and `rtl/tb/README.md` for manifest usage, tests and evidence. Timing/PPA
and real filter vector matching remain unrun.

Production uses the accepted Q2.14 interface (`W_common=16`, `F=14`); narrower
shell fixtures are diagnostic, and T03 implements no fractional arithmetic.
Numerical validation and T22's frozen coefficient export remain pending.
Real matching belongs to T31 (#48). Target-specific physical configurations
and runs belong to T41 (#52): SLOW 10 MHz (100 ns) main, FAST 100 MHz (10 ns)
secondary. Prepare both; secondary execution follows measured pilot capacity.
The skeleton JSON's 10 ns clock and the TB clock are setup, not principal-target
timing validation or PPA evidence for #55.
