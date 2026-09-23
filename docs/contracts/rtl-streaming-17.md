# RTL Streaming Contract

Decision ticket: [#17](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/17)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-22

Updated: 2026-09-22

Branch: `docs/17-rtl-streaming`

Scope: decision record for the common SystemVerilog streaming interface used by
the serial and optimized time/frequency variants, the latency declaration, the
frequency block parameters, and the vector-matching testbench contract. No
implementation code is included.

## Accepted Decisions

The team accepted these decisions on 2026-09-22:

- **D1 — Handshake:** production-style `valid`/`ready` (`valid_i`, `ready_o`,
  `valid_o`, `ready_i`), not `valid`-only and not full AXI-Stream.
- **D2 — Reset:** `rst_n` active-low with asynchronous assertion and
  synchronous deassertion through an internal reset synchronizer.
- **D3 — Port style:** one packed complex bus `{Q[W-1:0], I[W-1:0]}` per
  sample, unpacked internally with explicit signed casts.
- **D4 — Throughput:** parameterized `SAMPLES_PER_CLOCK` (`SPC`); serial is 1,
  unfolded variants increase it.
- **D5 — Transfer semantics:** transfers occur on `valid && ready`; otherwise
  the datapath holds. Bubbles are first-class and supported.
- **D6 — Latency:** declared per variant as `latency_samples` and
  `latency_cycles`; comparison is by absolute sample index.
- **D7 — Frequency block:** `FFT_LEN`, `HOP`, `DISCARD_PREFIX`, `EMIT_START`,
  and `EMIT_LEN` are parameters; the DUT initializes its zero history
  internally; `valid_o` emits `EMIT_LEN` contiguous samples per block.
- **D8 — Shared parameters:** `rtl/common/rrc_pkg.sv` holds the shared
  constants; `DATA_WIDTH` and `SAMPLES_PER_CLOCK` are module parameters.
- **D9 — Location:** this contract lives in `docs/contracts/` and follows the
  integration-branch flow.

## Decision Rationale

### D1 — Handshake: `valid`/`ready`

- **Alternatives:** `valid`-only without backpressure; full AXI-Stream with
  `TDATA`/`TKEEP`/`TLAST`/`TID`.
- **Why they were rejected:** `valid`-only cannot signal bubbles or stalls, so
  a gap would either be treated as a zero sample or require a continuity
  guarantee outside the interface; full AXI-Stream adds protocol fields that
  the filter does not need and would mix bus overhead into the PPA comparison.
- **Why this was chosen:** `valid`/`ready` is the production minimum for an
  integrable block, handles bubbles and stalls explicitly, and costs the same
  control logic in both lanes, so the PPA comparison stays fair.

### D2 — Reset: asynchronous assertion, synchronous deassertion

- **Alternatives:** fully asynchronous reset (the current placeholder style);
  fully synchronous reset.
- **Why they were rejected:** a fully asynchronous reset requires
  recovery/removal timing checks and a balanced reset tree, and its release is
  a metastability risk unless synchronized; a fully synchronous reset cannot
  reset a design whose clock is stopped and is less representative of
  production reset handling.
- **Why this was chosen:** it is the standard production pattern: the reset
  works independently of the clock, while the release is synchronized so every
  flop leaves reset on the same clock edge. The synchronizer is two flops per
  clock domain.

### D3 — Ports: packed complex bus

- **Alternatives:** separate signed `i_i`/`q_i`/`i_o`/`q_o` ports.
- **Why it was rejected:** separate ports are workable, but they create a
  second packing convention next to the ADR-0004 vector record and add port
  plumbing; the signedness pitfalls of part-selects are handled by the explicit
  casts required by the FXP policy anyway.
- **Why this was chosen:** `{Q[W-1:0], I[W-1:0]}` matches the packed vector
  record, keeps one packing convention, and still unpacks to signed fields
  immediately inside each module.

### D4 — Throughput: parameterized `SAMPLES_PER_CLOCK`

- **Alternatives:** fix the external interface at one sample per clock for
  every variant.
- **Why it was rejected:** unfolding processes `N` samples per cycle by
  definition; forcing a one-sample interface would require rate adaptation and
  buffering that is not part of the filter and would distort the PPA result.
- **Why this was chosen:** a single parameter covers the serial baseline and
  every unfolded variant, and the manifest declares the active value so the
  testbench and the PPA matrix know the rate. `SPC` is the interface width
  (samples per clock on `sample_i`/`sample_o`); it is not throughput. The
  initiation interval `II` is measured from the handshake (`valid && ready`)
  and depends on the micro-architecture (for the serial time lane `S=1`,
  `II=8`).

### D5 — Transfer semantics

- **Alternatives:** assume a contiguous stream and leave bubble handling out of
  scope.
- **Why it was rejected:** the handshake chosen in D1 makes bubbles part of the
  interface contract; assuming continuity would waste that capability and hide
  stall bugs.
- **Why this was chosen:** `valid && ready` transfer semantics with register
  hold is the standard streaming behavior, and the canonical vectors still
  drive `valid_i = 1` every cycle so the common case stays simple. The DUT
  backpressures via `ready_o`: the serial time lane (`S=1`, `II=8`) deasserts
  `ready_o` 7 of every 8 cycles. `ready_o = 1` in every cycle holds only for
  fully-parallel variants that can accept a new sample each clock.

### D6 — Latency declaration

- **Alternatives:** prescribe one fixed latency for all variants; compare
  outputs by arrival time.
- **Why they were rejected:** the serial, pipelined, and block architectures
  have different latencies, and an arrival-time comparison would fail for any
  variant whose latency differs from the golden model.
- **Why this was chosen:** each variant declares its latency in the manifest
  and the comparison uses absolute sample indices from the stimulus contract;
  the frequency variant additionally declares its block cadence and FFT/IFFT
  pipeline cycles separately.

### D7 — Frequency block parameters and internal history

- **Alternatives:** hardcode hop 8; have the testbench send the zero history;
  emit a single pulse per block with a separate count signal.
- **Why they were rejected:** hardcoding blocks the professor-gate switch to
  hop 9; testbench-supplied history would change the stimulus vectors and hide
  the initialization contract; a pulse-per-block output needs extra counters
  and complicates sample matching.
- **Why this was chosen:** `HOP`, `DISCARD_PREFIX`, `EMIT_START`, and
  `EMIT_LEN` are parameters, the DUT resets its frame history to zero, and
  `valid_o` emits `EMIT_LEN` contiguous samples per block so the comparison is
  a flat sample sequence.

### D8 — Shared parameter package

- **Alternatives:** duplicate constants in each module; use `define macros.
- **Why they were rejected:** duplicated constants drift between the time and
  frequency variants; `define macros are order-dependent and harder to scope.
- **Why this was chosen:** one package in `rtl/common/` gives a single source
  of truth for the block constants, while `DATA_WIDTH` and
  `SAMPLES_PER_CLOCK` stay as module parameters for per-variant configuration.

### D9 — Location

- **Alternatives:** keep the interface in the issue text; leave it on a
  research branch; commit directly to `main`.
- **Why they were rejected:** issue text is hard to diff and review; research
  branches are throwaway snapshots; a direct `main` commit bypasses the
  protected-branch flow.
- **Why this was chosen:** it matches the other contracts, stays reviewable in
  a PR, and lands on `main` through the final integration PR.

## Interface Specification

### Parameters

| Parameter | Scope | Baseline | Meaning |
| --- | --- | --- | --- |
| `DATA_WIDTH` | module | 16 | Per-component width `W` from the FXP policy. |
| `SAMPLES_PER_CLOCK` | module | 1 | Complex samples accepted/emitted per clock. |
| `FFT_LEN` | package | 16 | Frequency block transform length. |
| `HOP` | package | 8 | New input samples per frequency block. |
| `DISCARD_PREFIX` | package | 8 | IFFT samples discarded per block. |
| `EMIT_START` | package | 8 | First emitted IFFT index. |
| `EMIT_LEN` | package | 8 | Emitted samples per block (`FFT_LEN - DISCARD_PREFIX`). |

### Ports

Every variant exposes the same port names:

```systemverilog
module <variant> #(
  parameter integer DATA_WIDTH         = 16,
  parameter integer SAMPLES_PER_CLOCK  = 1
) (
  input  logic                                     clk,
  input  logic                                     rst_n,      // active-low, async assert, sync deassert
  input  logic                                     valid_i,
  output logic                                     ready_o,
  input  logic [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_i,
  output logic                                     valid_o,
  input  logic                                     ready_i,
  output logic [SAMPLES_PER_CLOCK-1:0][2*DATA_WIDTH-1:0] sample_o
);
```

Bus packing per sample:

```text
sample[2*DATA_WIDTH-1:0] = { Q[DATA_WIDTH-1:0], I[DATA_WIDTH-1:0] }
sample[DATA_WIDTH-1:0]   = I
sample[2*DATA_WIDTH-1:DATA_WIDTH] = Q
```

The module must unpack to explicitly `signed` fields before any arithmetic.
The time and frequency paths use the same port layout.

### Transfer rules

- A transfer happens when `valid && ready` on the same side.
- `SPC` is the interface width (complex samples per clock on the bus); `II`
  (initiation interval, in cycles between accepted input samples) is measured
  from the handshake, never inferred from `SPC` alone.
- `valid_o` must not depend combinationally on `ready_i`; `ready_o` may depend
  on `valid_i`.
- When there is no transfer, every register that holds stream state must hold
  its value.
- The canonical stimulus drives `valid_i = 1` in every clock after reset, and
  the DUT backpressures via `ready_o`: the serial time lane (`S=1`, `II=8`)
  deasserts `ready_o` 7 of every 8 accepted-sample cycles. `ready_o = 1` in
  every cycle holds only for fully-parallel variants; the handshake exists
  for integration and for stall tests.

### Reset behavior

- `rst_n` is active-low and is allowed to assert asynchronously.
- An internal two-flop synchronizer per clock domain produces the
  synchronized reset used by all sequential logic; modules must not use
  `rst_n` directly except in the synchronizer.
- During reset: `valid_o = 0`, `ready_o = 0`, `sample_o = 0`, and all internal
  history, accumulators, and valid pipelines are cleared.
- After deassertion, the first accepted sample is the first stimulus sample.

### Latency declaration

Each variant records in its manifest:

```text
latency_samples    # sample-index distance from first input to first valid output
latency_cycles     # implementation cycles (pipeline depth)
```

Frequency variants additionally record:

```text
block_cadence       # HOP
fft_pipeline_cycles # FFT + multiply + IFFT pipeline depth
```

The comparison never uses arrival time; the testbench places each captured
sample at its absolute index using `latency_samples`. The testbench measures
`II` from accepted transfers (`valid && ready`) and asserts no sample is
lost, duplicated, or invented under `ready_o` deassertion.

### Frequency block boundary

- The DUT resets its frame history to zero; the testbench sends only the
  stimulus samples from `x[0]`.
- `valid_o` is high for `EMIT_LEN` contiguous cycles per block, emitting
  `z[EMIT_START + i]` for `0 <= i < EMIT_LEN`.
- `ready_o` may stay high when the engine accepts one sample per clock; a
  variant that cannot accept a sample in some cycle must deassert it.

### Shared package

`rtl/common/rrc_pkg.sv` holds `FFT_LEN`, `HOP`, `DISCARD_PREFIX`, `EMIT_START`,
and `EMIT_LEN`, plus the accepted coefficient table once frozen. Per-variant
configuration stays in module parameters. No duplicated constants between the
time and frequency variants.

## Testbench Contract

- One parameterized testbench family reads the input and expected vectors,
  drives `valid_i` and `sample_i`, and captures `sample_o` on
  `valid_o && ready_i`.
- The canonical run holds `ready_i = 1`; a separate robustness test inserts a
  bubble (`valid_i = 0`) and a stall (`ready_i = 0`) and checks that no sample
  is lost, duplicated, or invented. The testbench also asserts no loss under
  DUT-side `ready_o` deassertion (e.g. serial `S=1` backpressure) and measures
  steady-state `II` from accepted transfers (`valid && ready`).
- The comparison is exact on the stored integer codes after sign extension to
  the packed 16-bit fields; floating-point conversion is not used.
- A mismatch reports the absolute index, the expected code, and the captured
  code.
- The testbench reads `DATA_WIDTH`, `SAMPLES_PER_CLOCK`, and
  `latency_samples` from the vector manifest, never from hardcoded values.

## Relationship to the Placeholder Shell

The current `rtl/common/rrc_stream_placeholder.sv` and
`rtl/tb/rrc_placeholder_tb.sv` are a temporary toolchain smoke shell with a
scalar port and no handshake. This contract supersedes that interface; the F3
implementation replaces the shell, and the placeholder testbench is retired
when the real vector-matching testbenches land.

## References

- Frequency block contract: `docs/contracts/frequency-block-contract-14.md`.
- QPSK stimulus contract: `docs/contracts/qpsk-stimulus-15.md`.
- FXP policy contract: `docs/contracts/fxp-policy-16.md`.
- RRC coefficient contract: `docs/contracts/rrc-coefficient-contract-13.md`.
- ADR-0002, ADR-0004, ADR-0005, ADR-0006, and `CONTEXT.md`.
