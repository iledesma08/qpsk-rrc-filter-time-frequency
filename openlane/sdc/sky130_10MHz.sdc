# 10 MHz labelled fallback SDC (identical to sky130_100MHz.sdc except period).
# Never ranked with 100 MHz passes (D3 interpretation, ADR-0006).
# See docs/contracts/toolchain-gap-2.md and openlane-env-19.md.
create_clock -name clk -period 100.000 [get_ports clk]
set_input_delay 2.0 -clock clk [all_inputs]
set_output_delay 2.0 -clock clk [all_outputs]
set_false_path -from [get_ports rst_n]
set_max_transition 1.5 [current_design]
set_max_fanout 16 [current_design]
