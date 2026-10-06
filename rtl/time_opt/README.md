# rtl/time_opt — time-domain filter, optimized version

The accepted reduced matrix is T-S4P1/T-S8P1 (T40-T41), built after the working
serial baseline. Each row needs RRC vector matching, FAST 100 MHz (10 ns)
main-target timing closure, and PPA evidence. SLOW 10 MHz (100 ns) is a secondary
comparative target, not a substitute for a failed FAST goal. T41 (#52) owns real
target-specific configurations/runs; #55 owns comparable PPA evidence. Prepare
both targets, run main goals first, and execute secondary runs according to
measured real-filter pilot capacity, not a promise to complete all twelve runs.
See `docs/adr/0006-systemverilog-openlane-ppa-flow.md`.

Run the T03 streaming shell test from the repository root:

```bash
bash rtl/time_opt/run.sh
bash rtl/time_opt/run.sh --data-width 16 --spc 4
```

`time_opt_filter.sv` currently wraps the same elastic **transport-only** shell
as the other variants. It has packed `{Q,I}`, width/SPC parameters, handshake
and synchronized reset release, but no systolic or pipelined RRC datapath.
Its generated identity fixtures in `.build/rtl/time_opt/` verify streaming
control, not an optimized filter or a PPA row. `SPC` is not the systolic factor
`S`, and neither alone establishes throughput.

Production Q2.14 (`W_common=16`, `F=14`) is already declared; parameterized shell
widths are diagnostic fixtures, not alternative production formats. T03 has no
fractional arithmetic or frozen T22 coefficient table. The OpenLane JSON's 10 ns
setup and the TB's 10 ns clock do not validate FAST timing or create a PPA row.

See `rtl/common/README.md` and `rtl/tb/README.md` for design, tests and evidence.
Optimization, real RRC matching and synthesis/signoff remain unrun.
