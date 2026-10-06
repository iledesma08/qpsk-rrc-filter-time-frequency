# Glossary — EDA and flow vocabulary

> Companion to `CONTEXT.md` (project domain language). This file collects the
> EDA, verification, flow, and signal-processing terms used across issues, PRs,
> and contracts. Normative details live in `docs/contracts/` and `docs/adr/`;
> definitions here are summaries. Flow for new terms (see the PR template):
> look up the weird words > write your own definition > have the AI refine it >
> record it here and/or in the PR glossary.

## Signal processing

- **Complex number** - A value with real and imaginary components, written
  `z = I + jQ`, where `j^2 = -1`. Here I is the in-phase component and Q is
  the quadrature component; `1+j` means I=1 and Q=1, not two consecutive
  values. Python uses `1j` for the imaginary unit. Both symbols and samples
  can be complex: the number format does not determine their role.
- **Symbol** - A value representing a group of information bits at the symbol
  rate, before oversampling and filtering. The index `k` in `s[k]` counts
  symbols; in this project each QPSK symbol represents two bits.
  - **QPSK (quadrature phase-shift keying)** - A modulation with four possible
    symbol phases, carrying two bits per symbol. This project's constellation
    is the four unnormalized corners `+1+j, +1-j, -1+j, -1-j`. Each has
    `|s[k]|^2 = I^2 + Q^2 = 2`, so the symbol energy is `Es=2`; scaling by
    `1/sqrt(2)` would change the agreed stimulus to `Es=1`.
  - **Gray mapping** - Assigning bit labels so neighboring constellation
    points differ in exactly one bit. The contract maps `00 -> +1+j`,
    `01 -> +1-j`, `10 -> -1+j`, and `11 -> -1-j` (integer indices 0 through
    3). Neighbors differ only in I or only in Q. This is a property of the
    labels, not a requirement that consecutive generated symbols visit
    neighboring corners or follow a Gray-code sequence.
- **Sample** - A signal value at one instant of the discrete time grid. The
  index `n` in `x[n]` or `y[n]` counts samples, not symbols. At 2x oversampling
  there are two sample instants per symbol period, separated by `T/2`.
  Before filtering, even input indices contain QPSK symbols and odd indices
  contain inserted zeros; after filtering, samples need not be zeros or
  constellation corners. The canonical frame has 1024 symbols and 2048
  input samples.
- **Zero-insertion** - Placing symbols on a finer sample grid and filling the
  additional positions with zeros. For this project's 2x oversampling,
  `x[2k] = s[k]` and `x[2k+1] = 0`, starting with the first symbol at `x[0]`.
  The inserted zero is not a QPSK symbol or missing data. Zero insertion
  alone does not create the shaped pulse; the following RRC filter generates
  the intermediate waveform values.
- **RRC filter (root-raised-cosine)** - A pulse-shaping filter whose ideal
  frequency-response magnitude is the square root of a raised-cosine
  response. A matched pair of ideal RRC filters produces the raised-cosine
  Nyquist response, with zero intersymbol interference at symbol instants
  under ideal timing. This project fixes the roll-off at `alpha=0.5`; RRC is
  not interchangeable with plain raised cosine.
  - **FIR RRC** - A finite impulse response implementation that approximates
    the ideal RRC pulse with a finite coefficient vector. This project uses
    eight real coefficients at two samples per symbol, applied as
    `y[n] = sum(h[m] * x[n-m])` for `m=0..7`. They shape I and Q separately
    through the same filter. Truncation means the eight-coefficient filter
    does not inherit every ideal RRC property exactly.
  - **Pulse shaping** - Turning the symbol impulses into overlapping,
    scaled copies of a chosen pulse to control the transmitted waveform and
    spectrum. Here zero insertion supplies the impulses and the RRC filter
    supplies the pulse shape. It creates waveform samples between symbol
    instants, not new information symbols.
- **Sample-and-hold** - Keeping a value constant until the next update. As an
  alternative 2x symbol-to-sample representation, it would repeat each symbol:
  `x[2k] = x[2k+1] = s[k]`. Unlike zero insertion, this introduces a
  rectangular hold pulse and changes the spectrum, so it is not the input
  representation selected for this project.
- **OLS (overlap-save)** - Computing linear FIR convolution in blocks using
  `FFT -> response multiply -> IFFT`. Consecutive input frames reuse history
  samples; the IFFT prefix corrupted by circular convolution is discarded,
  and the remaining outputs are concatenated, not added. For an `M`-coefficient
  FIR and an `N`-point FFT, the minimal overlap and discard are `M-1`, leaving
  `N-M+1` valid outputs. This project instead uses `M=8`, `N=16` and a forced
  50% overlap: eight history samples plus eight new samples per frame,
  discard `z[0:8]`, and emit `z[8:16]`. Seven discarded outputs are corrupted;
  the eighth is valid but belongs to the preceding output position (or the
  pre-input position in the first frame), so it is omitted to preserve the
  eight-sample cadence without duplication.
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
  illustrative Q2.14 integer example; production Q2.14 is already declared,
  while T20/T21 validate its arithmetic and T22 exports accepted integer codes.

## Streaming and RTL structure

- **Streaming** - Exchanging an ordered sequence progressively through
  transfers, rather than requiring the whole frame at once. A stream can pause
  without changing the order or identity of its accepted samples.
- **Handshake** - The agreement that transfers data at a clock edge when both
  the producer's `valid` and the consumer's `ready` are asserted. Offering valid
  data alone is not an accepted transfer.
- **Shell** - A shared interface/control envelope prepared to contain a
  processing implementation. A shell can implement transport without yet
  performing the numerical operations of a filter.
- **Beat** - One complete group of samples transferred together by a single
  handshake. With SPC=4 a beat carries four complex samples; four elapsed
  clocks are not automatically four beats.
- **Lane** - One sample position within a multi-sample beat. Lane 0 is the
  earliest sample in this project's ordering; all lanes transfer together.
- **Wrapper** - An outer module that exposes an interface and connects it to
  an implementation inside. Different wrapper names do not by themselves
  establish different algorithms or performance.
- **Package** - A SystemVerilog namespace containing shared declarations,
  such as constants and types. It is not an instantiated datapath or storage
  for samples in flight.
- **Backpressure** - A consumer's lack of capacity propagated toward the
  producer through `ready`. A producer offering valid data must wait and
  preserve that offer until it is accepted.
- **Bubble** - An input opportunity with no valid sample offered. It is an
  absence of data, not a sample whose value is zero; a source bubble can coexist
  with a pending output stall.
- **Stall** - A valid output waiting because its consumer is not ready.
  No output is consumed during that wait, regardless of how many clocks pass.
- **Hold** - Preserving a pending valid indication and its payload until the
  consumer accepts it. Retaining stale payload bits while valid is zero is not
  a pending valid transaction.
- **Push / pop** - Inserting an accepted beat into storage / removing a
  consumed beat from storage. Both can occur at the same edge, replacing the
  old beat with a new one without duplicating or losing either.
- **Cycle latency (latencia en ciclos)** - Clock-edge separation between an
  accepted input and the appearance of its corresponding valid output under
  stated observation and traffic conditions. A subsequent stall can delay
  consumption without changing when that output first became valid.
- **Sample latency (latencia en muestras)** - The sample-index offset used
  to align captured output records with their reference sequence. It is not
  elapsed clocks, the FIR's group delay, or automatically the FFT block size.
- **Initiation interval, II (intervalo de iniciacion)** - The number of
  cycles between successive accepted inputs under stated traffic conditions.
  It describes acceptance cadence, not bus width or input-to-output latency.

  **II=1:** consecutive beats can be accepted every cycle when valid data and
  downstream capacity are available; it does not guarantee progress under stalls.

  **II=8:** successive acceptances are eight cycles apart under continuous
  offered traffic without downstream stalls. With SPC=1 this is one sample
  per eight cycles, not eight cycles of sample-index displacement.

- **Synthetic transport (transporte sintetico)** - A controlled test scenario
  with artificial input codes and a declared transport relationship, such as
  unchanged output codes. It verifies transfer mechanics, not an RRC response.
- **Sign extension (extension de signo)** - Widening a two's-complement
  signed integer by repeating its sign bit, preserving its value. Eight-bit
  `FF` (-1) becomes sixteen-bit `FFFF`, not zero-extended `00FF` (+255).
- **Flush** - Explicitly accepted zero-valued input samples after the original
  source frame, used to complete its declared response. Flush samples are data,
  unlike idle clocks; they are distinct from padding added only to fill a beat.
- **Datapath** - The arithmetic and data-storage path that performs the
  numerical transformation, such as FIR accumulation or FFT butterflies.
  Transporting unchanged bits does not implement that filter datapath.

## Verification

- **Fixture** - A controlled, reproducible set of inputs, expected results,
  and configuration for a test. A transport fixture is not automatically a
  canonical QPSK frame or a golden RRC output.
- **Scoreboard** - Verification bookkeeping that associates accepted or
  consumed transactions with expected results and checks their order and
  counts. It advances on transfer events, not simply on elapsed clocks.
- **rtol (relative tolerance)** - The magnitude-dependent part of a numerical
  comparison's allowed error. NumPy's `assert_allclose(actual, expected, ...)`
  checks each element using
  `abs(actual - expected) <= atol + rtol * abs(expected)`.
  Thus `rtol=1e-10` contributes an allowed error of `1e-10` when the expected
  magnitude is 1, but contributes nothing when the expected value is zero.
  Time/frequency floating-point output comparisons use `rtol=1e-10` together
  with `atol=1e-12` to allow small rounding differences, not timing shifts.
- **atol (absolute tolerance)** - The fixed part of the same error bound,
  expressed in the units of the compared values. It remains effective near
  zero, where the relative contribution becomes tiny. With the project's
  `atol=1e-12`, an expected zero permits an absolute error up to `1e-12`;
  an expected magnitude of 1 permits `1.01e-10` when combined with
  `rtol=1e-10`. These tolerances apply to approximate floating-point checks;
  exact stimulus regeneration and RTL integer-code vector matching still
  require equality.
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
- `docs/contracts/qpsk-stimulus-15.md` - Symbol mapping, energy, edge patterns,
  and the shared zero-inserted sample frame.
- `docs/contracts/frequency-block-contract-14.md` - OLS frames, overlap,
  discard policy, and output alignment.
- `docs/contracts/fxp-policy-16.md` — FXP/SQNR policy and common coefficient
  width decisions owned by later phases.
- `docs/contracts/toolchain-gap-2.md` — pins, `iverilog/vvp` contract,
  Verilator lint, OpenLane JSON/SDC/evidence.
- `docs/contracts/rtl-streaming-17.md` - Handshake, packing, reset,
  sample/cycle latency, initiation interval, and finite-frame transport counts.
- `docs/contracts/vector-manifest-schema.md` - Production vector metadata
  and its separation from synthetic transport fixtures.
- `docs/contracts/openlane-env-19.md` — verified Nix/OpenLane/PDK, smoke
  repro, PDN-0185 floor, syn-commit rule.
- `docs/adr/0001-python-float-golden-simulator.md` — Python float64 as the
  project's correctness reference; individual issues implement its stages.
- `docs/adr/0005-common-sqnr-contract.md` - Shared comparison window and
  time/frequency floating-point tolerances.
- `docs/adr/0006-systemverilog-openlane-ppa-flow.md` — SystemVerilog +
  Icarus/vvp + Verilator lint-only + Classic; serial SLOW 10 MHz and optimized
  FAST 100 MHz main targets, with matched-target secondary comparisons.
