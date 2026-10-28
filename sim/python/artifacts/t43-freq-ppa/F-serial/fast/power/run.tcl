set ppa(top) {freq_serial_filter}
set ppa(corner) {nom_tt_025C_1v80}
set ppa(libs) {/home/majac/.volare/volare/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib}
set ppa(netlist) {/home/majac/curso/qpsk-rrc-filter-time-frequency/.build/ppa/F-serial/fast/openlane/51-openroad-fillinsertion/freq_serial_filter.nl.v}
set ppa(spef) {/home/majac/curso/qpsk-rrc-filter-time-frequency/.build/ppa/F-serial/fast/openlane/53-openroad-rcx/nom/freq_serial_filter.nom.spef}
set ppa(sdc) {/home/majac/curso/qpsk-rrc-filter-time-frequency/openlane/sdc/sky130_100MHz.sdc}
set ppa(saif) {/home/majac/curso/qpsk-rrc-filter-time-frequency/sim/python/artifacts/t43-freq-ppa/F-serial/fast/activity.saif.gz}
set ppa(scope) {rrc_stream_tb/dut}
set ppa(out) {/home/majac/curso/qpsk-rrc-filter-time-frequency/.build/ppa/F-serial/fast/power}
source {/home/majac/curso/qpsk-rrc-filter-time-frequency/openlane/scripts/annotated_power.tcl}
