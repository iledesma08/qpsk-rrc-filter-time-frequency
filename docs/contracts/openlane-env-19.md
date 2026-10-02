# OpenLane 2 + Sky130 Environment Record

Task ticket: [#19](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/19)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-22

Updated: 2026-10-02

Branch: `docs/19-openlane-env`

Scope: environment verification record and report-path check. No filter RTL
or PPA result is included.

Clock/evidence policy amended by the user on 2026-10-02 for recommendations
1 and 5 per `docs/contracts/ppa-matrix-18.md`; no professor approval is
claimed. The environment observations below remain dated 2026-09-22.

## Verified Environment

| Item | Value |
| --- | --- |
| Machine used | Verified workstation (12 cores, 31 GiB RAM) |
| Nix | Determinate Nix 3.21.8 |
| Nix binaries | `/nix/var/nix/profiles/default/bin` (not in `PATH` inside the container used for this session) |
| OpenLane | v2.3.10 from a local `~/openlane2` clone |
| PDK | volare; `~/.volare/volare/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af` with `sky130A` and `sky130B` (2.1 GB) |
| Standard cell library | `sky130_fd_sc_hd` (confirmed in the smoke test and the minimal run) |
| Functional simulator | Icarus Verilog (not used by the smoke test; used by the project TBs) |

## Reproduce: Official Smoke Test

```bash
cd ~/openlane2
nix-shell --pure shell.nix --run "openlane --smoke-test"
```

Observed on 2026-09-22:

- Classic flow, 78 stages, about one minute on the verified machine.
- Final line: `Smoke test passed.` and exit code 0.
- The smoke test runs inside a temporary directory and deletes it afterwards;
  it leaves no run directory to archive. Keep the log as evidence.

## Reproduce: Minimal Design and Report Paths

The smoke test deletes its run directory, so a minimal design was used to
verify the report extraction path that F4 will use. Configuration below is
the PDN-floor validation only; per-variant F4 sizing follows the
same-utilization rule in the Small-Design PDN Lesson:

```json
{
  "DESIGN_NAME": "top",
  "VERILOG_FILES": "dir::src/*.v",
  "CLOCK_PORT": "clk",
  "CLOCK_PERIOD": 10.0,
  "FP_SIZING": "absolute",
  "DIE_AREA": [0, 0, 200, 200]
}
```

Command:

```bash
cd ~/openlane2
nix-shell --pure shell.nix --run \
  "openlane --pdk sky130A --scl sky130_fd_sc_hd --flow Classic /path/to/config.json"
```

A successful run creates `<design>/runs/RUN_<timestamp>/`. The evidence that
F4 must retain, matched by step name rather than step number:

- `final/metrics.json` and `final/metrics.csv`;
- `<step>-openroad-stapostpnr/summary.rpt`;
- `<step>-openroad-stapostpnr/<corner>/max.rpt`, `min.rpt`, `checks.rpt`, and
  `power.rpt`;
- DRC, LVS, antenna, and flow-status fields.

Observed example with the minimal design (tool validation only, not a project
result): `final/metrics.json` reported instance area `954.666 um^2`, 507
standard cells, setup worst slack `+6.2286 ns`, hold worst slack `+1.6254 ns`,
and zero TNS at a 10 ns clock. The STA step directory was
`54-openroad-stapostpnr` with the expected `summary.rpt`, per-corner reports,
and `power.rpt`.

## Small-Design PDN Lesson

The first minimal attempt failed at `OpenROAD.GeneratePDN` with:

```text
[PDN-0185] Insufficient width (21.16 um) to add straps on layer met4 in grid
"stdcell_grid" with total strap width 4.9 um and offset 16.32 um.
```

The default sizing produced a core too small for the default PDN straps.
Setting `FP_SIZING: absolute` with `DIE_AREA: [0, 0, 200, 200]` fixed it,
establishing `200x200 um` as the PDN-0185 floor. The project's 8-tap filters
are tiny, so F4 sizing is: size each die for 50-60% core utilization (target
~55%); final die is `max(sized-for-target, 200x200 um)`. Same PDN strategy,
not same die. Apply the same sizing rule to every target run and record die
area, core area, and utilization per run (from
`final/metrics.json`). This is a configuration detail, not a filter result.

## Team Availability

All four members already use Nix and OpenLane from previous coursework, so no
shared runner is needed. Re-run the smoke test above if a machine's environment
is reinstalled or updated; that test is the acceptance check for the toolchain.

## Commands for F4

- Run: `openlane --pdk sky130A --scl sky130_fd_sc_hd --flow Classic <config.json>`.
- Timing targets: `CLOCK_PERIOD: 100.0` for SLOW 10 MHz (main for
  `T-serial`/`F-serial`); `10.0` for FAST 100 MHz (main for
  `T-S4P1`/`T-S8P1`/`F-U4`/`F-U8`). The other target is secondary for each.
- Prepare six architectures x two targets = 12 runs, not 12 architectures;
  prioritize the six main targets, then comparative secondary runs as
  time/resources measured by the first real filter pilot permit. Record
  pilot runtime/resource use; smoke/minimal-design timings are not filter
  schedule estimates. All 12 runs before 2026-11-06 are not promised and no
  new assumed duration is introduced. Extra architectures remain extension-only.
- Re-synthesize, optimize, and run PnR independently at each target using the
  same RTL revision, parameters, and numerics, with the same conditions except
  the declared clock and the same sizing rule. Generate VCD/SAIF activity at
  the actual period; record period and annotation coverage rather than reuse
  another target's timing or merely scale its reported power.
- Record architecture, target/period, FAST/SLOW class, main/secondary role,
  corner, workload, and failed/unrun status with reasons. A SLOW pass does not
  erase a FAST failure or fulfill an optimized candidate's FAST main goal.
- Evidence: `final/metrics.json` plus the STA reports, DRC/LVS/antenna status,
  and the activity-annotation status for any power ranking.

Secondary runs furnish same-clock serial baselines. Pareto ranking and
architecture-only improvement claims require the same target, corner,
workload, and activity conditions. Cross-target values may be displayed with
explicit labels, but are not a controlled architecture-only comparison.

Each optimized candidate reports effective throughput, area, and power per
valid output deltas versus its same-domain serial using actual matched-target
results. Power per valid output (energy/output) requires valid actual-period
activity for both runs. Record comparator run tags and `not-comparable` with
the reason if the serial fails same-target gates, is unrun, or conditions do
not match; missing valid activity makes the power delta `not-comparable`.
Never invent a delta. Delivery requires demonstrated improvement in at least
one PPA axis from at least one optimized candidate per domain, not every
variant or every axis. Retain failed/non-improving candidates; a run failing
vector, physical-signoff, or target-timing gates cannot be a winner. SLOW
comparison evidence does not substitute for an optimized FAST main goal.

Historical wording (superseded 2026-10-02): 10 MHz was a labelled fallback
when the all-100-MHz primary target failed. This is no longer the active rule.

## Committed-but-unrun artifacts

- Commit the synthesis and PnR inputs for every top-level variant even when
  their numbers arrive later: SDC files, TCL build/timing scripts, and one
  OpenLane JSON config per top-level variant (DUT only, never testbenches).
  The setup must resolve both declared target runs; retain target-specific
  resolved configuration and evidence separately when each is executed.
- The committed evidence paths for each run are exactly: `resolved.json`;
  `final/metrics.json` and `metrics.csv`; `*-openroad-stapostpnr/summary.rpt`;
  per-corner `max.rpt`, `min.rpt`, `checks.rpt`, and `power.rpt` (see
  `docs/contracts/toolchain-gap-2.md` for what each report proves). Area is
  read in square micrometres; Fmax is derived as
  `1000 / critical_path_delay_ns` from `max.rpt` (or `CLOCK_PERIOD` minus
  signed setup slack), never from a dedicated estimate file.
- An unrun script is recorded as unrun. Estimates MUST NOT be published as
  measured results. Failed runs retain available logs/reports and the failure
  reason; do not fabricate missing signoff or power evidence.

## Status

Resolved: the environment and the report path are verified, and the
reproduction steps are recorded. The team already has the toolchain from
previous coursework; the smoke test above is the re-verification check.

## References

- ADR-0006 (SystemVerilog and OpenLane PPA flow).
- `docs/contracts/toolchain-gap-2.md`.
- `docs/contracts/frequency-block-contract-14.md` and `docs/contracts/fxp-policy-16.md`.
