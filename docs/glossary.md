# Glossary — EDA and flow vocabulary

> Companion to `CONTEXT.md` (project domain language). This file collects the
> EDA, verification, and flow terms used across issues, PRs, and contracts.
> Normative details live in `docs/contracts/` and `docs/adr/`; definitions
> here are summaries. Flow for new terms (see the PR template): look up the
> weird words > write your own definition > have the AI refine it > record it
> here and/or in the PR glossary.

## Verification

- **DUT (device under test)** — the RTL being verified or synthesized: the
  four filter variants plus `rtl/common`. It is what vector matching checks,
  what Verilator lints, and what OpenLane synthesizes. Never the testbench,
  never the vectors.
- **TB (testbench)** — the harness around the DUT: generates clock/reset,
  replays stimulus vectors via `$readmemh`, and fails the run (`$fatal`,
  nonzero exit) on the first mismatch. Simulation-only: it is never
  synthesized and is excluded from DUT lint and from `VERILOG_FILES`.

## Backend and signoff

- **PNR (place and route)** — the backend stage that turns the synthesized
  netlist into physical layout: floorplanning (die/core area), placement of
  standard cells, clock-tree synthesis (CTS), global + detailed routing of
  wires, and power-grid (PDN) insertion. In this repo it is OpenLane 2's
  Classic flow; `PNR_SDC_FILE` is the constraint set it must close timing
  against.
- **SIGNOFF** — the final acceptance gate after PnR: the design is only a
  real result if every signoff check passes. Four sub-checks:
  - **STA timing** — static timing analysis, i.e. checking every
    register-to-register path against the clock *without* simulating
    vectors. Three quantities matter:
    - **Setup/hold slack** — the margin on each path: how much earlier than
      required the data arrives (setup slack, must be ≥ 0 or the clock is
      too fast) and how much longer than required it stays stable (hold
      slack, must be ≥ 0 or there is a race). Negative slack of either kind
      is a broken design.
    - **TNS (total negative slack)** — the sum of all negative slacks.
      Worst slack tells you the single worst path; TNS tells you how
      widespread the problem is (one bad path vs a hundred).
    - **Critical path** — the slowest path in the design; its delay sets the
      ceiling: `fmax ≈ 1000 / critical_path_delay_ns`. Reported in
      `summary.rpt` with per-corner detail in `max.rpt` (setup) / `min.rpt`
      (hold).
  - **DRC (design rule check)** — the layout obeys the foundry's
    geometric/manufacturing rules (widths, spacings, enclosures).
  - **LVS (layout vs schematic)** — the drawn layout is electrically the
    same circuit as the netlist.
  - **Antenna** — no long floating metal collects enough charge during
    fabrication to damage gates.

  Signoff is constrained by `SIGNOFF_SDC_FILE`, which must be identical to
  the PNR file except for the clock period — otherwise timing could pass
  against different constraints than the ones used to build the layout.
- **.sdc (Synopsys Design Constraints)** — the industry-standard constraint
  format (originally from Synopsys, understood by OpenROAD/OpenLane): clock
  definitions, I/O delays, false paths, and electrical limits in one file.
- **Input / output delay** — the timing budget reserved for the outside
  world: inputs are assumed to arrive a bounded time after the clock edge
  (2.0 ns here), and outputs must be stable a bounded time before the next
  edge, leaving the rest of the period for internal logic.
- **False path** — a path deliberately excluded from timing analysis because
  it can never matter functionally — here the async `rst_n`, which has no
  setup/hold requirement by construction.
- **Setup / hold** — the two fundamental timing contracts of every
  flip-flop: data must be stable a setup time *before* the clock edge and
  remain stable a hold time *after* it. Setup violations mean the clock is
  too fast for the logic; hold violations mean a race between launch and
  capture. Either is a broken design, not a warning.
- **Max transition** — the slowest edge allowed on any net (1.5 ns here).
  Slow edges spend too long in the threshold region (more noise sensitivity,
  more short-circuit current, more delay), so the tool must buffer or resize
  offenders.
  - **Slew vs skew (do not confuse them)** — *slew* (a.k.a. transition) is
    how long a *single* edge takes to rise/fall on one net; that is what
    this limit caps. *Skew* is the *difference in arrival time of the same
    clock edge at two different flip-flops* (clock-tree imbalance). Slew is
    per-net edge quality; skew is cross-chip clock alignment — both eat into
    the timing budget, but they are different quantities with different
    fixes (buffering/sizing vs clock-tree balancing).
- **Max fanout** — the most loads a single driver may feed (16 here) before
  it must be buffered or cloned. Keeps delays predictable and the library
  cells inside their characterized range.
  - **Fanout** — the number of gate inputs driven by one output. Each extra
    load adds capacitance, which slows the edge (see slew above) and
    increases dynamic power; past the limit the tool inserts buffers or
    clones the driver.

## Process

- **Syn-commit rule** — commit the synthesis/PnR inputs (one JSON config per
  top variant, SDC/TCL, DUT only) even when the numbers arrive later, so a
  missing PPA number is always traceable to an *unrun config* and never to
  missing setup. An unrun flow is recorded as unrun; estimates are never
  published as measured results.

## References

- `CONTEXT.md` — project domain vocabulary (QPSK, RRC, SQNR, vector
  matching, …).
- `docs/contracts/toolchain-gap-2.md` — pins, `iverilog/vvp` contract,
  Verilator lint, OpenLane JSON/SDC/evidence.
- `docs/contracts/openlane-env-19.md` — verified Nix/OpenLane/PDK, smoke
  repro, PDN-0185 floor, syn-commit rule.
- `docs/adr/0006-systemverilog-openlane-ppa-flow.md` — SystemVerilog +
  Icarus/vvp + Verilator lint-only + Classic 100MHz/10MHz-fallback.
