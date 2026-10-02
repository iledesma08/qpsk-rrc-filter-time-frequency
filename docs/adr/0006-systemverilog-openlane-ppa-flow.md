# SystemVerilog and OpenLane PPA flow

**Status:** accepted, amended by the user on 2026-10-02 for recommendations 1 and 5; no professor approval is claimed. Normative: `docs/contracts/toolchain-gap-2.md` + `docs/contracts/openlane-env-19.md` + `docs/contracts/ppa-matrix-18.md` + `docs/contracts/rtl-streaming-17.md`. This ADR defines SystemVerilog + Icarus/vvp (Verilator lint-only) and the OpenLane 2 Classic flow with serial SLOW / optimized FAST main targets; environment pins and experiment matrix live in the contracts.

RTL is SystemVerilog simulated with Icarus/vvp; GTKWave is a manual debug
tool and Verilator is an optional DUT-lint complement. PPA uses OpenLane 2's
Classic flow in its Nix environment with `sky130A` and
`sky130_fd_sc_hd`, synthesizing the DUT and shared RTL without testbenches or
vectors. The six base architectures remain `T-serial`, `T-S4P1`, `T-S8P1`,
`F-serial`, `F-U4`, and `F-U8`. The serial main target is SLOW 10 MHz (100 ns);
the four optimized main targets are FAST 100 MHz (10 ns).

Prepare both targets per architecture: six architectures x two targets =
12 runs, not 12 architectures. Prioritize the six declared main-target runs,
then execute secondary comparative runs as time/resources measured by the
first real filter pilot permit. All 12 completed runs before 2026-11-06 are
not promised, and no new assumed duration is introduced. Secondary runs
supply same-clock serial baselines, not a fallback-only lane.

Re-synthesize, optimize, and run PnR separately at each target under the same
conditions except the declared clock, without changing RTL or numerics.
Activity must correspond to the actual period. Record target, class,
main-or-secondary role, and failed/unrun status; passing SLOW never fulfills
a failed FAST main goal.

Every comparable run records area, signoff timing/slack and derived fmax,
power with VCD/SAIF activity status, and DRC/LVS/antenna status. Pareto ranking
and architecture-only improvement claims require the same target, corner,
workload, and activity conditions. Explicitly labelled cross-target displays
are allowed, but are not controlled architecture-only comparisons.

Each optimized candidate reports effective throughput, area, and power per
valid output deltas versus its same-domain serial under comparable conditions,
including valid actual-period activity for power. Use actual matched-target
results; a failed or unrun serial baseline is `not-comparable`, not an
invented delta. Delivery requires improvement in at least one PPA axis from
at least one optimized candidate per domain, not from every variant or in
every axis. Retain failed/non-improving candidates; no winner may fail vector,
physical-signoff, or target-timing gates. Secondary SLOW evidence does not
replace an optimized candidate's FAST main goal.

The base comparison retains registered `P=1` time architectures and unfolded
frequency architectures. Additional `P=2`, `U=2`, and folded architectures
remain extension-only under the existing matrix contract; this amendment
does not activate them or change precision or Booth/ROM guidance.

Base-scope amendment accepted 2026-10-02: ordinary signed RTL arithmetic and
one validated fixed-coefficient path suffice. Custom Booth, alternate ROMs,
narrower accumulators and FFT-B are optional follow-ups with no delivery
blocking edges. Additional matrix architectures remain extension-only;
Q1.15 and AWGN/BER/full-link analysis remain outside base scope. Fixed formats,
matching, target closure and honest PPA evidence are not optional.

Historical decision (superseded 2026-10-02): every architecture originally had
a 100 MHz primary target, with a labelled 10 MHz fallback only if it failed.
That policy is retained here as history, not as the current run rule.
