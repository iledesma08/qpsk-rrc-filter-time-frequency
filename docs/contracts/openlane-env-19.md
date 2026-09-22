# OpenLane 2 + Sky130 Environment Record

Task ticket: [#19](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/19)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-22

Updated: 2026-09-22

Branch: `docs/19-openlane-env`

Scope: environment verification record and report-path check. No filter RTL
or PPA result is included.

## Verified Environment

| Item | Value |
| --- | --- |
| Machine used | Ignacio's workstation (12 cores, 31 GiB RAM) |
| Nix | Determinate Nix 3.21.8 |
| Nix binaries | `/nix/var/nix/profiles/default/bin` (not in `PATH` inside the container used for this session) |
| OpenLane | v2.3.10 at `/home/askesis/openlane2` |
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
verify the report extraction path that F4 will use. Configuration:

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
Setting `FP_SIZING: absolute` with `DIE_AREA: [0, 0, 200, 200]` fixed it. The
project's 8-tap filters are tiny, so every variant config must set an explicit
die area large enough for the PDN from the start, or provide a reduced PDN
configuration. This is a configuration detail, not a filter result.

## Per-Member Status

| Member | Status |
| --- | --- |
| Ignacio (`iledesma08`) | Verified: smoke test passed and a real minimal run completed with reports. |
| Juan (`JRondon23`) | Pending: run the same smoke test on his machine. |
| Matias (`matiascostamagna`) | Pending: run the same smoke test on his machine. |
| Andres (`AndresCesana`) | Pending: run the same smoke test on his machine. |

Requirements per member: Nix, an `openlane2` clone, and about 2.1 GB for the
volare PDK. If a machine cannot host the environment, the fallback is to use
the verified workstation or agree on a shared runner; no cloud service is
required by ADR-0006.

## Commands for F4

- Run: `openlane --pdk sky130A --scl sky130_fd_sc_hd --flow Classic <config.json>`.
- Timing targets: `CLOCK_PERIOD: 10.0` for 100 MHz, `100.0` for the labelled
  10 MHz fallback.
- Evidence: `final/metrics.json` plus the STA reports, DRC/LVS/antenna status,
  and the activity-annotation status for any power ranking.

## Status

Resolved: the environment and the report path are verified, and the
reproduction steps are recorded. Three team members still need to run the
smoke test on their own machines before the F4 PPA phase.

## References

- ADR-0006 (SystemVerilog and OpenLane PPA flow).
- `docs/contracts/toolchain-gap-2.md`.
- `docs/contracts/frequency-block-contract-14.md` and `docs/contracts/fxp-policy-16.md`.
