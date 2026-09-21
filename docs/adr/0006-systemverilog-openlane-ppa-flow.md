# SystemVerilog and OpenLane PPA flow

**Status: accepted**

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
