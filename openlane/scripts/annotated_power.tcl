# Annotated power of one OpenLane run (T41 #52), run with OpenSTA after the flow.
# OpenLane's own power.rpt never reads activity; this script loads the same
# post-PnR netlist, parasitics, signoff SDC and corner liberty as its
# STAPostPNR step, reports the unannotated power (it must equal OpenLane's
# power.rpt), then reads the activity window of the run's gate-level
# simulation (SAIF) and reports again. With ppa(vcd) it then reads the same
# window as a VCD and reports a third time: the cross-check of the SAIF.
#
# The caller sets the ppa array and sources this file:
#   ppa(top) ppa(corner) ppa(libs) ppa(netlist) ppa(spef) ppa(sdc)
#   ppa(saif) ppa(scope) ppa(out) and optionally ppa(vcd)
# Outputs in ppa(out): power_unannotated.rpt, power_annotated.rpt,
# power_vcd_check.rpt and pins.txt (every leaf pin and port with its
# direction, to measure annotation coverage).

set_cmd_units -time ns -capacitance pF -current mA -voltage V -resistance kOhm -distance um
set corner $ppa(corner)
define_corners $corner
foreach lib $ppa(libs) {
    read_liberty -corner $corner $lib
}
read_verilog $ppa(netlist)
link_design $ppa(top)
read_sdc $ppa(sdc)
# The SDC says nothing about propagation; OpenLane then propagates every clock.
set_propagated_clock [all_clocks]
read_spef -corner $corner $ppa(spef)

report_power -corner $corner -digits 6 > $ppa(out)/power_unannotated.rpt
read_saif -scope $ppa(scope) $ppa(saif)
report_power -corner $corner -digits 6 > $ppa(out)/power_annotated.rpt
if { [info exists ppa(vcd)] } {
    # Prints "Annotated <n> pin activities."; the same pins take the VCD values.
    read_vcd -scope $ppa(scope) $ppa(vcd)
    report_power -corner $corner -digits 6 > $ppa(out)/power_vcd_check.rpt
}

set pins [open $ppa(out)/pins.txt w]
foreach pin [get_pins -hierarchical *] {
    puts $pins "[get_full_name $pin] [get_property $pin direction]"
}
foreach port [get_ports *] {
    puts $pins "[get_full_name $port] [get_property $port direction]"
}
close $pins
