# SystemVerilog and OpenLane PPA flow

**Status:** accepted, extended by contracts. Normative: `docs/contracts/toolchain-gap-2.md` + `docs/contracts/openlane-env-19.md` + `docs/contracts/ppa-matrix-18.md` + `docs/contracts/rtl-streaming-17.md`. This ADR defines only SystemVerilog + Icarus/vvp (Verilator lint-only) and the OpenLane 2 Classic 100 MHz primary / 10 MHz labelled-fallback rule; environment pins and experiment matrix live in the contracts.

RTL is SystemVerilog simulated with Icarus/vvp; GTKWave is a manual debug
tool and Verilator is an optional DUT-lint complement. PPA uses OpenLane 2's
Classic flow in its Nix environment with `sky130A` and
`sky130_fd_sc_hd`, synthesizing the DUT and shared RTL without testbenches or
vectors. The primary timing target is 100 MHz; a 10 MHz run is an explicitly
labelled fallback when 100 MHz does not close.

Every comparable run records area, signoff timing/slack and derived fmax,
power with VCD/SAIF activity status, and DRC/LVS/antenna status. The initial
optimization comparison uses pipeline+systolic for time and unfolded for
frequency, with folded frequency hardware evaluated as an area contrast when
resources allow.
