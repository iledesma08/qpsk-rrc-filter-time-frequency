# rtl/freq_opt — frequency-domain filter, optimized version

The accepted reduced matrix is F-U4/F-U8 (T42-T43), after the working serial
baseline. Folded frequency hardware returns only on an approved scope extension.
Each row needs RRC matching, FAST 100 MHz (10 ns) main-target timing closure,
and PPA evidence. SLOW 10 MHz (100 ns) is secondary, never a replacement for a
failed FAST goal. T43 (#54) owns real target-specific configurations/runs;
#55 owns comparable PPA evidence. Prepare both targets, run main goals first,
and execute secondary runs according to measured real-filter pilot capacity,
not a promise to complete all twelve runs. See ADR-0006.

Run the T03 streaming shell test from the repository root:

```bash
bash rtl/freq_opt/run.sh
bash rtl/freq_opt/run.sh --data-width 16 --spc 4
```

`freq_opt_filter.sv` currently wraps the shared elastic **transport-only** shell
with packed `{Q,I}`, width/SPC parameters, handshake and synchronized reset
release. No unfolded FFT/IFFT datapath runs. FFT16/H8/discard8/emit8 are exposed
block defaults; unused-parameter lint warnings are expected until the engine
lands. Changing the accepted hop-8 baseline still requires the professor gate.

Production Q2.14 (`W_common=16`, `F=14`) is already declared; parameterized shell
widths are diagnostic fixtures, not alternative production formats. T03 has no
fractional arithmetic or frozen T22 coefficient table. The OpenLane JSON's 10 ns
setup and the TB's 10 ns clock do not validate FAST timing or create a PPA row.

Generated identity fixtures in `.build/rtl/freq_opt/` test control and packing,
not RRC matching or a frequency PPA row. `SPC` is bus width, not replication
factor `U` or measured throughput. See `rtl/common/README.md` and
`rtl/tb/README.md` for design, tests and evidence. Synthesis/signoff remain unrun.
