# QPSK Stimulus Contract

Decision ticket: [#15](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/15)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-22

Updated: 2026-09-22

Branch: `docs/15-qpsk-stimulus`

Scope: decision record for the deterministic stimulus used by the time and
frequency floating-point models, the FXP/SQNR measurement, and RTL vector
matching. No implementation code is included.

## Accepted Decisions

The team accepted these decisions on 2026-09-22:

- **D1 — Frame length:** `S = 1024` symbols.
- **D2 — PRNG and seed:** `numpy.random.default_rng(2026)`, with an explicit
  mapping of four generated values to the QPSK corners.
- **D3 — Edge patterns:** five fixed 8-symbol patterns (40 symbols total)
  prepended to the random part.
- **D4 — Oversampling representation:** zero-insertion upsampling; vectors
  carry the post-upsampling samples, not the symbols.
- **D5 — Initial state:** zero filter history, first symbol at sample 0, no
  in-frame guard symbols.
- **D6 — Valid output window:** full causal output `y[0:L+M-1]` for the
  golden, the SQNR measurement, and vector matching.
- **D7 — Symbol centers and interpolation:** `symbol_center_offset = 3.5`
  samples; evidence stays on the natural sample grid, interpolation is only
  allowed in labelled slides.
- **D8 — Location:** this contract lives in `docs/contracts/` and follows the
  integration-branch flow.

## Decision Rationale

### D1 — Frame length: 1024 symbols

- **Alternatives:** 256 symbols (lighter vectors) and 4096 symbols (more
  statistical stability).
- **Why they were rejected:** 256 symbols leave less margin for the SQNR
  statistics and fewer samples around the edge patterns, which weakens the
  measurement; 4096 symbols make the vector files and the RTL matching run
  longer without adding information for an 8-tap filter.
- **Why 1024 was chosen:** it gives enough samples for a stable SQNR, keeps
  each vector around a few kilobytes, keeps the RTL matching fast, and still
  provides enough symbols for the eye and spectrum plots.

### D2 — PRNG and seed: `numpy.random.default_rng(2026)`

- **Alternatives:** seed 42, Python `random.Random`, or no fixed seed.
- **Why they were rejected:** seed 42 is equally valid and was displaced only
  by a documented project constant, so it is not a technical rejection;
  `random.Random` is a general-purpose PRNG with weaker stream-stability
  guarantees than NumPy's PCG64; an unfixed seed would break reproducibility
  and vector matching entirely.
- **Why this was chosen:** NumPy is already a project dependency, PCG64 is the
  modern generator with documented stream stability, and a fixed integer seed
  plus an explicit corner mapping makes regeneration deterministic across
  machines.

### D3 — Edge patterns: five fixed 8-symbol patterns

- **Alternatives:** random symbols only; a different or larger pattern set;
  patterns appended at the end of the frame.
- **Why they were rejected:** random-only can under-sample extrema and I/Q
  imbalance; a larger set would reduce the random portion without adding
  coverage beyond the intended cases; appending patterns at the end would
  complicate the frame end and the valid-window checks.
- **Why this set was chosen:** the five patterns cover all corners, the
  anti-diagonal, I-only alternation, Q-only alternation, and a constant corner,
  in a small prefix that is easy to verify while keeping the rest of the frame
  random.

### D4 — Oversampling: zero insertion, vectors carry samples

- **Alternatives:** vectors carry symbols and the RTL performs the upsampling;
  sample-and-hold upsampling.
- **Why they were rejected:** RTL upsampling would add logic that is not part
  of the filter and would make the RTL diverge from the simulator flow;
  sample-and-hold has a sinc-shaped droop and would require a different pulse
  design.
- **Why this was chosen:** zero insertion followed by the RRC filter is the
  canonical pulse-shaping chain, it matches the 2-samples-per-symbol design of
  the coefficient contract, and the RTL receives one sample per clock with no
  extra upsampler.

### D5 — Initial state: zero history, no guards

- **Alternatives:** prepend guard symbols; start from random history; wait for
  a history fill before emitting.
- **Why they were rejected:** guards consume samples and complicate the valid
  window; random history adds hidden state that must be reproduced exactly;
  waiting complicates the streaming contract for no mathematical benefit.
- **Why this was chosen:** zero history is the natural causal start
  (`x[n] = 0` for `n < 0`), it matches the zero pre-frame padding of the
  frequency OLS contract, and it is trivially reproducible.

### D6 — Valid window: full causal output

- **Alternatives:** input-length window (2048 samples); symbol-aligned trimmed
  window; different windows per domain.
- **Why they were rejected:** trimming the tail discards real signal energy; a
  symbol-aligned trim interacts with the half-sample delay and is easy to get
  wrong; per-domain windows violate the common-window requirement of
  ADR-0005.
- **Why this was chosen:** it keeps all the energy, contains no
  implementation-only padding, gives both domains and the FXP model identical
  absolute indices, and the manifest declares `valid_start` and `valid_len`
  explicitly.

### D7 — Symbol centers: natural grid, presentation-only interpolation

- **Alternatives:** interpolate to symbol centers for all evidence; display
  with sample-and-hold; forbid interpolation entirely.
- **Why they were rejected:** interpolated evidence compares derived values
  rather than implementation output and can hide one-sample alignment errors;
  sample-and-hold distorts the waveform; forbidding interpolation in slides
  adds no value.
- **Why this was chosen:** verification stays exact on the samples that the
  golden and RTL actually produce, while slides can use a clearly labelled
  presentation-only view.

### D8 — Location: `docs/contracts/` with the integration flow

- **Alternatives:** keep the decision in the issue text; commit directly to
  `main`; keep it only on a research branch.
- **Why they were rejected:** issue text is hard to diff and review; a direct
  `main` commit bypasses the protected-branch flow; research branches are
  throwaway snapshots and are not the canonical home.
- **Why this was chosen:** it matches the existing contracts, keeps the
  decision reviewable in a PR, and lands on `main` through the single final
  integration PR.

## Signal Model

Symbols are the unnormalized QPSK corners accepted in the RRC contract:

```text
s[k] in {+1+j, +1-j, -1+j, -1-j}, k = 0..S-1, S = 1024
```

Nominal symbol energy is `Es = E[|s_k|^2]`; for `s_k in {+/-1 +/- j}`,
`Es = 2`. This definition fixes the analysis scale only: it does not modify
or rescale the `.hex` vectors, the RTL, or the generated expected codes,
which keep the declared unnormalized constellation per the RRC contract D3.
The `1/sqrt(2)` normalization (`Es = 1`) belongs solely to link-budget or
presentation analysis when such analysis is explicitly defined; it is never
folded into stimulus, vectors, or RTL.

Zero-insertion upsampling produces `L = 2*S = 2048` complex samples:

```text
x[2k]   = s[k]
x[2k+1] = 0        for k = 0..S-1
```

The RRC filter `h[0..7]` from the RRC contract (unit energy, ascending time,
`D = 3.5` samples) is applied as the causal FIR

```text
y[n] = sum(m=0..7) h[m] * x[n-m],  n = 0..L+M-2
```

The full causal output has `L + M - 1 = 2048 + 7 = 2055` samples, indices
`0..2054`. Symbol `k` has its pulse center at sample position `2k + 3.5`, so
there is no output sample exactly at a symbol center.

## Edge Patterns

The first 40 symbols are fixed patterns; the remaining 984 are random.

| # | Pattern | Eight symbols |
| --- | --- | --- |
| a | four corners in order | `+1+j, +1-j, -1+j, -1-j, +1+j, +1-j, -1+j, -1-j` |
| b | anti-diagonal alternation | `+1+j, -1-j, +1+j, -1-j, +1+j, -1-j, +1+j, -1-j` |
| c | I alternation | `+1+j, -1+j, +1+j, -1+j, +1+j, -1+j, +1+j, -1+j` |
| d | Q alternation | `+1+j, +1-j, +1+j, +1-j, +1+j, +1-j, +1+j, +1-j` |
| e | single corner | `+1+j` repeated eight times |

The random part uses `idx = rng.integers(0, 4, size=984)` with this mapping:

```text
0 -> (+1, +1)
1 -> (+1, -1)
2 -> (-1, +1)
3 -> (-1, -1)
```

The mapping is Gray: symbols adjacent in the constellation (differing only
in I or only in Q) differ in exactly one bit. Recorded as the descriptive
manifest field `symbol_map_coding: gray`, which MUST stay consistent with
this mapping without redefining it.

## Valid Output Window

- The comparison window is the full causal output: `valid_start = 0`,
  `valid_len = 2055`.
- The same frame is used by the time golden, the frequency golden, the FXP
  model, and the RTL vectors.
- There is no implementation-only padding and no in-frame guard symbols; the
  implicit zero history before sample 0 is part of the causal definition.
- Presentation plots may trim to the input-length view (`2048` samples), but
  that trimmed view is never the comparison window.

## Vector Manifest Fields

Normative schema: `docs/contracts/vector-manifest-schema.md` (§1 stimulus
fields). The example below is non-normative and must match the schema. The
future T13 generator records these fields:

```text
stimulus_version: qpsk-stim-15-v1
symbol_count: 1024
edge_pattern_symbols: 40
random_seed: 2026
prng: numpy.random.default_rng (PCG64)
symbol_map: 0=+1+j, 1=+1-j, 2=-1+j, 3=-1-j
symbol_map_coding: gray
symbol_energy: 2
vector_set: canonical
vector_case: none
samples_per_symbol: 2
upsampling: zero_insertion
input_samples: 2048
output_samples: 2055
valid_start: 0
valid_len: 2055
symbol_center_offset_samples: 3.5
input_scale_16bit: Q2.14
coefficient_scale_16bit: Q2.14
coefficient_scale_sensitivity: Q1.15 (phase E only, never folded into common-width claim)
output_scale_16bit: Q2.14 (provisional; frozen in T20/T21)
evidence_interpolation: none
```

## Reproducibility Checks

These checks belong to the future T11/T13 tests:

- Regenerating with seed `2026` produces an identical symbol stream and
  byte-identical vector files.
- The first 40 symbols match the documented edge patterns.
- The input stream has symbols at even indices and zeros at odd indices.
- The output length is `2055` and the impulse-alignment check passes: for an
  impulse at `x[0]`, the first eight emitted samples are the tap sequence in
  order.
- Symbol centers are reported at `2k + 3.5`; no check may assume an integer
  sample at the center.
- The time and frequency goldens agree on this frame within the ADR-0005
  tolerance `rtol=1e-10`, `atol=1e-12`.
- The FXP SQNR measurement uses the same frame and the full causal window.

## Interpolation Policy

Because the group delay is `3.5` samples, symbol centers fall between computed
samples. Interpolating would estimate values that neither the golden nor the
RTL produces, and a smooth interpolation can hide a one-sample alignment
error. Verification evidence therefore uses the natural sample grid only.

For slides, an interpolated eye diagram or symbol-center view is allowed when
it is clearly labelled as presentation-only. It must not replace the
verification plots or the comparison data. The eye/zero-ISI evidence uses the
canonical frame defined above; no separate clean-channel stimulus exists
because the canonical stimulus is already noiseless.

## Corner Sets

In addition to the canonical frame, T13 generates the `sys_corners` vector
set: full canonical-length frames (1024 symbols, 2048 samples, 2055 outputs,
same window and invariants) with fully deterministic symbol content. Every
symbol below is a valid QPSK corner; zero is not a valid end-to-end symbol
and MUST NOT appear as a symbol value in these frames (upsampling zeros at
odd sample indices are unaffected).

| `vector_case` | Exact 1024-symbol sequence | Stresses |
| --- | --- | --- |
| `corner_repeat` | `+1+j` repeated 1024 times | Maximum sustained build-up; accumulator near maximum; output saturation |
| `max_alternation` | (`+1+j`, `-1-j`) alternating, 512 pairs | Maximum sample-to-sample swing; I and Q flip every symbol |
| `single_symbol_perturbation` | Background `+1+j` 1024 times except index **512** = `-1-j` (diagonal opposite: maximum single-symbol perturbation, mid-frame, away from edges) | Isolated transition spreading through the 8 taps |

`vector_case` names are stable identifiers; future corners add new names
without changing the schema. The true impulse-response check (impulse at
`x[0]`, first eight outputs equal the tap sequence) stays a mathematical/sim
check per Reproducibility Checks and the #14 numerical-equivalence check; it
is NOT a QPSK end-to-end vector and MUST NOT be confused with
`single_symbol_perturbation`.

## References

- RRC coefficient contract: `docs/contracts/rrc-coefficient-contract-13.md`.
- Frequency block contract: `docs/contracts/frequency-block-contract-14.md`.
- ADR-0004 packed external vectors, ADR-0005 common SQNR contract, and
  `CONTEXT.md` for the canonical vocabulary.
