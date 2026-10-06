# RRC Architectures and PPA Comparison

## Design Choice

Use **systolic + pipeline in the time domain** and **unfolded arithmetic in
the frequency domain**, each compared against its own serial baseline. The
base experiment has six architectures. These are design choices and a
measurement method, not predictions of which candidate will win PPA.

Both domains implement the same 8-tap RRC filter for QPSK, with 50% roll-off
and 2x oversampling. Time-domain filtering computes direct convolution;
frequency-domain filtering uses complex FFT16 -> bin-wise response multiply
-> IFFT16 with overlap-save (OLS). The accepted forced-50% schedule uses
eight history samples plus eight new samples, discards `z[0:8]`, and emits
`z[8:16]`. The eighth discarded position avoids a duplicate/pre-boundary
output; it is not an extra alias-corrupted sample. Hop 9 is no longer a
candidate: the revised assignment fixes 50% overlap (#74).

Sources: [canonical vocabulary](../../CONTEXT.md#language),
[architecture matrix](../contracts/ppa-matrix-18.md#matrix), and
[forced-50% OLS derivation](../contracts/frequency-block-contract-14.md#forced-50-ols).

## Six Architectures

| Variant | Architecture | Controlled comparison | Main target |
| --- | --- | --- | --- |
| T-serial | One reused MAC; `S=1`, `P=1`, `SPC=1`; scheduling `II=8` | Time-domain correctness and PPA reference | SLOW 10 MHz |
| T-S4P1 | Four active systolic PEs; one registered arithmetic stage per PE | Partial tap parallelism; scheduling `II=2` | FAST 100 MHz |
| T-S8P1 | Eight systolic PEs; full tap array, `P=1` | S4 -> S8 scaling at fixed pipeline depth; scheduling `II=1` | FAST 100 MHz |
| F-serial | `U=1` arithmetic issue lane for FFT, bin multiply, and IFFT | Frequency-domain correctness and PPA reference | SLOW 10 MHz |
| F-U4 | Unfolded engine with four arithmetic issue lanes | Intermediate replication relative to `U=1` | FAST 100 MHz |
| F-U8 | Unfolded engine with eight arithmetic issue lanes | U4 -> U8 scaling; full radix-2 butterfly parallelism for FFT16 | FAST 100 MHz |

Read the factors separately:

- **`S`** counts time-domain tap processing elements (PEs) active in an issue
  group. Remaining tap groups use later cycles; `II=8/S` is the scheduling
  target before interface bubbles, not a measured result.
- **`P`** counts registered arithmetic stages per time-domain PE. `P=1`
  registers multiply/accumulate as one stage; `P=2` adds a register between
  multiplication and addition. It changes critical path and latency, not
  numeric widths or the sample schedule.
- **`U`** counts frequency-domain arithmetic issue lanes. It is neither the
  interface width nor a promise of `U` output samples per cycle. Include
  scheduling, storage, bin multiplication, and IFFT in the engine accounting.
- **`SPC`** (`SAMPLES_PER_CLOCK`) is the number of complex sample lanes in an
  interface beat. A beat transfers only on `valid && ready`; bus width alone
  does not determine sustained throughput.
- **`II`** is the measured initiation interval in cycles. State whether the
  measurement concerns accepted samples/beats or internal work groups, and
  report effective output throughput separately. `S=8` means eight taps can
  work in parallel, not eight output samples per clock.

Generate variants from one parameterized source, recording the revision and
factors. The extension adds `T-S2P1`, `T-S2P2`, `T-S4P2`, `T-S8P2`, `F-U2`,
and `F-F2`; these are not part of the six-row base. The folded `F=2` contrast
reuses the logical U8 schedule over two issue slots with half the physical
lanes, including its registers, multiplexers, and controller. Serial resource
reuse and this explicit folded contrast are distinct comparison points.
Pipeline-depth effects require fixed-`S` P1/P2 pairs on extension; the base
isolates systolic scaling at `P=1` and frequency replication at U4/U8.

Sources: [factor definitions](../contracts/ppa-matrix-18.md#factor-definitions),
[variant discipline](../contracts/ppa-matrix-18.md#production-practice-for-variants),
and [interpretation rules](../contracts/ppa-matrix-18.md#interpretation-rules).

## Shared Numerical Contract

Production input/output I/Q components and stored RRC coefficients use
**signed `Q2.14`**, with `W_common=16` and `F_data=F_coeff=14`. Internal
arithmetic is wider: time products retain 32 bits with 28 fractional bits;
the conservative eight-term accumulator is 35 bits with 28 fractional bits.
Sum products without inter-tap rounding, then narrow once to the output.

Use round-to-nearest, ties-to-even (**RNE**) at every intentional narrowing,
with saturation only at explicit conversion/narrowing/output boundaries.
Internal overflow rejects the candidate; wrapping is only a diagnostic
negative control. Acceptance requires zero internal overflow on the
canonical and edge-case checks, zero canonical output saturation, and
**SQNR >= 40 dB in each domain** against the aligned float64 reference.
Use the complex I/Q power formula in the
[SQNR ADR](../adr/0005-common-sqnr-contract.md#common-sqnr-contract-for-both-domains).

The frequency integer model must freeze FFT/IFFT ordering, twiddle integers,
`H[k]` generation, internal widths, narrowing points, and total scaling before
accepting sweep rows. A float FFT followed only by an output cast is not an
FXP model. Use grow-by-stage baseline A for the base; one-bit-per-stage
baseline B is an optional same-width experiment, not a blocker or an implicit
production change. Restore the output scale with the recorded total
compensation, including inverse normalization exactly once.

The diagnostic width sweep (`W=8,10,12,14,16,18`, extending to 20 if needed)
remains required evidence of the precision frontier. Report the smallest
passing common width, but do not automatically replace production Q2.14.
A production-format change requires a recorded decision and regenerated
evidence. Within each domain, serial and optimized architectures at both
targets keep identical widths, rounding, saturation, and expected codes.
Time and frequency FXP codes need not be identical to each other: each RTL
must match its own accepted FXP model bit for bit.

Sources: [numeric policy](../contracts/fxp-policy-16.md#numeric-policy),
[frequency arithmetic freeze](../contracts/fxp-policy-16.md#frequency-arithmetic-freeze-t20-before-t21),
[numerical acceptance](../contracts/fxp-policy-16.md#acceptance-rule), and
[base and optional scope](../contracts/fxp-policy-16.md#base-scope-amendment-accepted-2026-10-02).

## Correctness Evidence

Build evidence in stages rather than inventing future numeric or timing data:

| Phase / artifact stage | Evidence and purpose |
| --- | --- |
| F1 / `float_reference` | Deterministic stimulus and full causal float64 references for canonical and corner frames; declare domain, provenance, and hashes. No final integer expectations or RTL latency. |
| F2 / `fxp_expected` | Accepted Q2.14 input and per-domain integer expected codes from the actual FXP models, with frozen policy and SQNR/overflow/saturation evidence. No guessed per-variant latency. |
| F3 / `rtl_matching` | Bind F2 payload hashes to variant identity, measured latency, interface width, flush/padding, and physical transfer counts. Require 100% exact integer matching, including corner sets. |

Use external packed 32-bit `{Q[15:0], I[15:0]}` records (`I=real`,
`Q=imaginary`), `$readmemh`, and SHA-256 sidecars; vectors are not DUT logic.
Metadata may change for a different latency without rewriting numeric
payloads. Changing arithmetic policy requires regeneration and repeat
matching. Establish the serial reference before accepting optimizations.

The canonical source has 1024 symbols and 2048 zero-inserted samples. Both
domains compare exactly **2055** causal outputs, `y[0:2055]`. Distinguish
that numerical window from physical transfers:

| Domain at `SPC=1` | Source samples | Accepted flush zeros | Total accepted inputs | Raw outputs | Compared codes |
| --- | --- | --- | --- | --- | --- |
| Time | 2048 | 7 | 2055 | 2055 | 2055 |
| Frequency | 2048 | 8 | 2056 | 2056 (257 blocks) | 2055 |

Frequency output index 2055 is declared block padding, not a 2056th expected
code. Wider-interface final-beat padding is recorded separately as
`transport_padding_samples`, with actual per-variant input/output counts.
Initial history is zero inside the DUT; flush zeros are accepted transactions,
whereas invalid bubbles do not advance history. Stop input after the declared
count and drain with a bounded timeout. Check ordering, raw counts, no loss or
duplication under gaps/backpressure, and exact valid-window codes.

Measure cycle latency in a run without testbench stalls or gaps; keep it
separate from II and frequency block fill. Both causal output sequences start
at `y[0]` (`latency_samples=0`); block fill does not shift the comparison by
eight indices.

Sources: [artifact lifecycle](../contracts/vector-manifest-schema.md#artifact-lifecycle-amended-2026-10-02),
[finite-frame counts](../contracts/vector-manifest-schema.md#finite-frame-transport-counts-f3),
[matching and robustness](../contracts/rtl-streaming-17.md#matching-and-robustness),
and [serial-first rule](../adr/0002-serial-rtl-before-optimization.md#serial-rtl-with-vector-matching-before-optimizing).

## Comparable PPA Runs

Prepare **both targets for every architecture**: SLOW 10 MHz (`100 ns`) and
FAST 100 MHz (`10 ns`). Six architectures x two targets means twelve prepared
runs, not twelve architectures. Execute the six main runs first: two serials
at SLOW and four optimized candidates at FAST. Then prioritize secondary runs
that establish same-target serial/optimized comparisons in each domain;
schedule the remaining pairs using runtime/resource evidence from a real
filter pilot, rather than assuming all twelve runs fit the available capacity.

Re-synthesize, optimize timing, and run place-and-route separately at each
target, keeping RTL and numerics unchanged. A secondary SLOW pass does not
fulfill an optimized candidate's failed FAST objective. Record target, role,
and passed/failed/unrun status. Compare architectures only at the same target,
signoff corner, workload, and activity policy. A 10 MHz serial versus a
100 MHz optimized result may be shown as labelled context, but cannot prove
architecture-only gains or enter one shared Pareto ranking.

Use the same pinned OpenLane 2 Classic flow, `sky130A`/`sky130_fd_sc_hd`,
synthesis/physical settings, SDC template, IO constraints, PDN strategy, and
sizing rule. Target 50-60% core utilization (about 55%) with the specified
200 x 200 um minimum die floor; record die/core areas and utilization rather
than forcing every candidate onto the same die. Include deployed buffers,
FFT storage, controllers, reset synchronization, and handshake logic in area;
exclude testbenches and vectors.

Sources: [clock policy](../contracts/ppa-matrix-18.md#clock-policy) and
[measurement conditions](../contracts/ppa-matrix-18.md#measurement-conditions).

## Metrics and Selection

- **Performance:** measure valid outputs per second from output handshakes at
  the signoff clock, plus input acceptance II, cycle latency, setup/hold slack,
  and derived fmax. Do not substitute clock frequency, `SPC`, or lane count
  for effective throughput. Separate steady-state throughput from frame
  fill/tail; frequency steady-state statistics use the first 256 blocks,
  while full-frame accounting covers all 257. Exclude implementation padding
  from valid-output counts and state the measurement interval.
- **Area:** report implemented area in `um^2`, die/core area, utilization, and
  throughput per `um^2`, with the complete DUT accounting above.
- **Power:** generate VCD/SAIF separately per candidate and target at its actual
  period, using the same canonical workload and reset/warm-up policy and
  covering the tail block. Record annotation coverage and core + clock-tree
  power, excluding IO power. Unannotated power is an auxiliary estimate,
  never dynamic-power ranking evidence. Annotated power divided by effective
  valid-output throughput is energy per output, not power in watts.
- **Gates:** require 100% vector matching, physical signoff (DRC, LVS, antenna),
  and timing closure at the declared target before ranking. A configured
  period is a constraint, not proof of closure.
- **Selection:** build same-condition Pareto fronts for area versus effective
  throughput, adding energy per valid output when annotation is valid. A point
  is dominated if another is no worse on every compared axis and better on at
  least one. Defend the chosen trade-off without an arbitrary weighted score.

For every optimized candidate, report absolute/percentage deltas against its
**same-domain serial at the same clock**, with both run tags, units, and sign
convention. If the serial is unrun, fails a gate, or uses incompatible
conditions, mark the delta `not-comparable` with a reason; never substitute a
different clock's baseline. Missing comparable annotation makes the power
delta `not-comparable` even if area/throughput can be compared.

The required optimization evidence is improvement in at least one PPA axis
from at least one optimized candidate **per domain** under these conditions.
The label "optimized" is not evidence; neither every candidate nor every
axis must improve. Retain regressions, failed goals, and missing evidence.
A same-target SLOW improvement and fulfillment of a FAST main goal are
separate claims.

Keep a run ledger binding architecture/factors, revision, numeric/vector
hashes, target/role, corner, status, II/latency/throughput, area, activity and
power status, signoff, serial run tag, and deltas. Preserve resolved configs,
metrics JSON/CSV, post-PnR timing/power/signoff reports, and functional logs
so the comparison can be reproduced. Rerun finalists only to resolve a
genuine tie or unexplained outlier.

Sources: [workload](../contracts/ppa-matrix-18.md#workload),
[activity and power](../contracts/ppa-matrix-18.md#activity-and-power),
[ranking gates](../contracts/ppa-matrix-18.md#ranking-rule),
[optimization evidence](../contracts/ppa-matrix-18.md#optimization-evidence),
and [normalized evidence row](../contracts/ppa-matrix-18.md#normalized-row).
