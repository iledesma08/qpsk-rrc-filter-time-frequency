# Glossary — EDA and flow vocabulary

> Companion to `CONTEXT.md` (project domain language). This file collects the
> EDA, verification, flow, and signal-processing terms used across issues, PRs,
> and contracts. Normative details live in `docs/contracts/` and `docs/adr/`;
> definitions here are summaries. Flow for new terms (see the PR template):
> look up the weird words > write your own definition > have the AI refine it >
> record it here and/or in the PR glossary.

## Signal processing

- **One-sided occupied bandwidth** — The highest positive frequency occupied
  by a baseband signal, measured from zero to one side of its spectrum. For the
  ideal RRC pulse it is `(1 + alpha) / (2T)`; with `alpha=0.5` and `T=1`, this
  is `0.75` cycles per symbol. The corresponding two-sided spectrum extends
  from `-0.75` to `+0.75` cycles per symbol.
- **Truncation** — Limiting an ideal pulse, which extends indefinitely in
  time, to a finite set of samples so it can be implemented as a practical
  filter. T10 keeps eight RRC samples; the finite filter therefore only
  approximates the ideal pulse and has a nonzero stopband.
- **Stopband** — The frequency region a filter is designed to attenuate. A
  finite eight-tap RRC reduces frequencies there but does not remove them
  perfectly; its actual response is shown separately from ideal band edges.
- **Tap** — Informal name for one discrete filter coefficient and its delay
  position. In this repository, **coefficient** is the preferred primary
  term; an eight-tap filter has eight coefficients.
- **Canonical artifact** — The versioned, machine-readable JSON that records
  the normative RRC parameters and float64 coefficient vector, with grid and
  raw values for audit. For T10 it is `rrc8-v1/manifest.json`; T11/T12 read
  its coefficients through `load_rrc8_coefficients()`.
- **SQNR (signal-to-quantization-noise ratio)** — A measure, in dB, of signal
  power relative to the error introduced by quantization. In this project it
  compares floating-point and fixed-point outputs. T10 defines coefficients;
  it does not run the FXP SQNR measurement.
- **Unit discrete L2 energy** — Coefficient normalization where
  `sum(|h[n]|^2) = 1`. For T10's real coefficients this is `sum(h[n]^2)=1`.
  It is not the same as unity DC gain, which would require `sum(h[n])=1`.
- **Grid** — The set of time instants at which the continuous RRC pulse is
  sampled to produce discrete coefficients. T10 uses the centered grid
  `t[n] = (n - (N-1)/2) * T/sps`, giving symmetric sample times and a
  half-sample center for even `N`.
  - **Causal grid** — A one-sided grid beginning at `t=0`, such as
    `t[n]=n*T/sps`. It includes the pulse's peak at zero but truncates the
    negative-time side differently; it is not the centered grid selected by
    the T10 contract.
- **FIR (finite impulse response)** — A digital filter whose response to an
  impulse has finite duration, so each output is a finite weighted sum of input
  samples. Whether those samples are past, present, or future depends on
  whether the FIR is causal.
  - **Causal FIR** — An FIR implemented without depending on future input:
    `y[m] = sum(h[k] * x[m-k])`. With coefficients stored in ascending
    physical time, index `k` identifies the input delay used by the sum.
- **Delay** — The time shift between a signal entering a filter and the
  corresponding filtered signal. A symmetric linear-phase FIR of length `N`
  has group delay `(N-1)/2` samples.
  - **Causal delay** — The delay of the causal FIR's output relative to its
    input. For T10's symmetric eight-coefficient filter it is `3.5` samples;
    this half-sample alignment is not rounded to 3 or 4.
- **Oversampling** — Representing each symbol with more than one sample. The
  project's `2x oversampling` means two samples per symbol, spaced by `T/2`.
  In the project's sample representation, symbols are placed on that finer
  grid by zero insertion; the additional positions are not values created by
  interpolating the pulse.
- **RNE (round-to-nearest-even)** — Rounding to the nearest integer, choosing
  the even integer when a value lies exactly halfway between two integers.
  NumPy's `rint` uses this rule. T10 uses it only for the explicitly
  illustrative Q2.14 integer example; the final common width is decided in
  T21/T22.

## Verification

- **DUT (device under test)** — The RTL being verified or synthesized: the
  four filter variants plus `rtl/common`. It is what vector matching checks,
  what Verilator lints, and what OpenLane synthesizes. Never the testbench,
  never the vectors.
- **TB (testbench)** — The harness around the DUT: generates clock/reset,
  replays stimulus vectors via `$readmemh`, and fails the run (`$fatal`,
  nonzero exit) on the first mismatch. Simulation-only: it is never
  synthesized and is excluded from DUT lint and from `VERILOG_FILES`.

## Backend and signoff

- **PNR (place and route)** — The backend stage that turns the synthesized
  netlist into physical layout: floorplanning (die/core area), placement of
  standard cells, clock-tree synthesis (CTS), global + detailed routing of
  wires, and power-grid (PDN) insertion. In this repo it is OpenLane 2's
  Classic flow; `PNR_SDC_FILE` is the constraint set it must close timing
  against.
- **SIGNOFF** — The final acceptance gate after PnR: the design is only a
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
    how long a *single* edge takes to rise/fall on one net; that is what this
    limit caps. *Skew* is the *difference in arrival time of the same
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
- `docs/contracts/rrc-coefficient-contract-13.md` — RRC grid, normalization,
  delay, and T10 canonical coefficient artifact.
- `docs/contracts/fxp-policy-16.md` — FXP/SQNR policy and common coefficient
  width decisions owned by later phases.
- `docs/contracts/toolchain-gap-2.md` — pins, `iverilog/vvp` contract,
  Verilator lint, OpenLane JSON/SDC/evidence.
- `docs/contracts/openlane-env-19.md` — verified Nix/OpenLane/PDK, smoke
  repro, PDN-0185 floor, syn-commit rule.
- `docs/adr/0001-python-float-golden-simulator.md` — Python float64 as the
  project's correctness reference; individual issues implement its stages.
- `docs/adr/0006-systemverilog-openlane-ppa-flow.md` — SystemVerilog +
  Icarus/vvp + Verilator lint-only + Classic 100MHz/10MHz-fallback.
