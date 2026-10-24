# FAST 100 MHz SDC template (PNR/SIGNOFF), identical to sky130_10MHz.sdc except period.
# Main target of the optimized rows, secondary of the serial rows (ppa-matrix-18 Clock Policy).
# See docs/contracts/toolchain-gap-2.md and openlane-env-19.md.
create_clock -name clk -period 10.000 [get_ports clk]
set_input_delay 2.0 -clock clk [all_inputs]
set_output_delay 2.0 -clock clk [all_outputs]
set_false_path -from [get_ports rst_n]
set_max_transition 1.5 [current_design]
set_max_fanout 16 [current_design]
