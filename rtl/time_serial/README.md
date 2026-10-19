# rtl/time_serial — time-domain filter, serial version

T30 (#47) serial baseline `T-serial`: `S=1`, `P=1`, `SPC=1`, `II=8`. Run the
structural canonical frame from the repository root:

```bash
bash rtl/time_serial/run.sh
python -m pytest sim/python/tests/test_rtl_time_serial.py -v
```

T31 (#48) vector matching against the committed `rtl_matching` vectors
(canonical and the three `sys_corners`, see [Vector matching](#vector-matching-t31)):

```bash
python sim/python/tests/rtl_matching_stage.py --variant T-serial
bash rtl/time_serial/run.sh --vectors .build/rtl/matching/T-serial/canonical-none
python -m pytest sim/python/tests/test_rtl_time_matching.py -v
# Evidence: run every frame with capture, then draw the plots from the captures
python sim/python/tests/rtl_matching_stage.py --variant T-serial \
  --evidence-dir sim/python/artifacts/t31-time-matching
python sim/python/plot_matching.py
```

## Design

`time_serial_filter.sv` computes `y[n] = sum_k c[k] * x[n-k]` for `k = 0..7`
with one complex-by-real MAC: two signed 16x16 multipliers (I and Q) share the
same real coefficient, so one tap per cycle covers both components.

- **History:** eight packed `{Q,I}` codes, `history[k] = x[n-k]`. It shifts only
  on an accepted input (`valid_i && ready_o`); bubbles and stalls leave it alone.
- **Schedule:** the accept edge loads `x[n]`; the next eight edges run taps
  `0..7` in ascending order on registered operands. Tap 0 restarts the sum.
- **Output:** tap 7 adds the last product, applies the single RNE/saturating
  cast to `Q2.14` (`rrc_pkg::time_output_cast`) and loads the output register.
  The next input is accepted on that same edge, so under continuous traffic
  `ready_o` is high one cycle in eight (`II=8`). One output per accepted input
  gives `latency_samples=0`; the first valid output appears 9 cycles after its
  input is accepted (`latency_cycles=9`, asserted by the TB).
- **Backpressure:** if the previous output is still pending at tap 7, the
  engine holds its accumulator and tap counter and keeps `ready_o` low until
  the sink drains the output register. Nothing is lost or emitted twice.
- **Control paths:** `ready_o` and `valid_o` come only from registers, so
  neither depends combinationally on `valid_i` or `ready_i`.
- **Reset:** one `rrc_reset_sync` instance; every register (history,
  accumulators, counter, output) uses the synchronized reset.

Numerics follow the accepted time policy in `docs/contracts/fxp-policy-16.md`:
`Q2.14` data and coefficients, 32-bit products with 28 fractional bits, a
35-bit accumulator, and one RNE right shift by 14 followed by saturation to
16 bits. `rrc_pkg.sv` holds the coefficient table, the widths and the cast so
the optimized variants (T40) reuse the same arithmetic. An elaboration check
proves the accumulator cannot overflow for any input code
(`2^15 * sum|c| = 990248960 < 2^34`), so no overflow port is added. The same
check rejects any width other than 16 or `SPC` other than 1.

## Verification (structural, T30)

`sim/python/tests/rtl_filter_fixture.py` writes fixtures under `.build/`, never
`sim/vectors/`, with expected codes from an exact integer reference of the
accepted policy: Q2.14 codes of the frozen float taps, full-precision integer
products and sums, and one RNE (`round` of a `Fraction`) plus saturation. It
does not reuse the T20 FXP model (`fxp.py`) and never casts the float
reference output. Frames: canonical
(2048 + 7 flush zeros), impulse `1 - j` (`y[0:8] = c`), `+/-0.5` impulses
(exact RNE ties in both directions), full-scale sign-aligned input (both
saturation limits) and 64 arbitrary 16-bit codes. The shared TB runs each one
continuously (latency, `II`) and with bubbles, stalls and a mid-traffic reset.

`test_rtl_time_serial.py` also checks:

- the package cast against the exact reference on 2024 accumulator values;
- the coefficient table and widths against the numeric policy and the T20
  production policy (`fxp.quantize_coefficients`, `PRODUCTION_POLICY`);
- the T20 integration gate: the reference and `fxp.filter_time_fxp` give the
  same input codes, output codes, RNE operation/inexact/tie counts and
  saturations, with no internal overflow, on the five structural frames and
  the three `sys_corners` frames;
- the T22 integration gate: the committed export in `sim/vectors/fxp_expected/`
  (each file checked against its `.sha256` sidecar) holds the same coefficient
  codes as the reference and `RRC_COEFS`, derived from the same float golden,
  and the reference turns each exported `input.hex` into the exported
  `expected_time.hex` (canonical and the three `sys_corners`, 2055 codes each).
  The canonical structural fixture is that same frame, so the RTL's canonical
  run produces the T22 time codes;
- a 40-cycle sink stall: two inputs accepted, the second waits at tap 7;
- no combinational path from `valid_i` or `ready_i` to the outputs;
- synchronized reset release and history clearing mid-computation;
- elaboration and runner rejection of non-production width or `SPC`.

Removing RNE, saturation, the final-edge accept, the pending-output guard, the
accepted-only history shift, the history reset or the per-sample accumulator
clear each makes at least one of these tests fail.

## Learning

- The serial schedule keeps the single MAC busy every cycle: the eight taps
  need eight edges, and overlapping the last tap with the next accept is what
  makes `II=8` rather than 9.
- The shared TB's random stalls are shorter than eight cycles, so they never
  reach the tap-7 hold; a directed long stall is needed to cover it.
- QPSK inputs never exercise rounding or saturation (every product is a
  multiple of `2^14`), so directed arbitrary codes are the only evidence for
  that hardware.
- Icarus 11 rejects multidimensional package parameters and package function
  calls inside constant functions, hence the flat coefficient vector and the
  direct slices in the bound check.

## Vector matching (T31)

T31 closes the time lane's F3 gate: the RTL reproduces, bit for bit, the T22
production time codes of all four frames over the full causal window. Nothing
in the datapath changed for it; T31 adds the metadata that binds those codes to
this variant and the runs that prove the match.

- **Metadata:** `gen_vectors.py --stage rtl_matching --variant T-serial` writes
  `sim/vectors/rtl_matching/T-serial/<set>/<case>/` with a JSON manifest and
  the `vector_manifest.svh` the TB includes. It declares `SPC=1`,
  `latency_samples=0`, `latency_cycles=9` (the T30 design latency), 7 flush
  zeros and 2055 accepted and raw samples. The `.hex` payloads stay in
  `sim/vectors/fxp_expected/` and are bound by hash, not copied.
- **Staging:** `sim/python/tests/rtl_matching_stage.py` checks every sidecar,
  every bound hash and that the `.svh` localparams equal the manifest, then
  copies `input.hex`, `expected.hex` (`expected_time.hex`) and the `.svh` into
  `.build/`. The runner checks the sidecars again before compiling.
- **What one run proves:** the continuous run (`valid_i` and `ready_i` held
  high) asserts the declared 9-cycle latency, measures `II=8` over 2054
  intervals and compares all 2055 codes from `y[0]`. The robust run repeats the
  comparison with source bubbles, sink stalls, DUT `ready_o` backpressure and a
  tail stall, after a reset that aborts an accepted prefix. Both runs count
  2048 source plus 7 flush samples in and 2055 samples out, and the drain check
  fails on any undeclared extra output.
- **Evidence:** `sim/python/artifacts/t31-time-matching/evidence_manifest.json`
  (written by `rtl_matching_stage.py --evidence-dir`): 4/4 frames PASS, 8220
  compared codes, measured latency 9 and II 8 on every frame, plus the hashes
  of the `.svh` and payloads each run consumed. Each continuous run also
  captures its RTL outputs (`--capture`); the SHA-256 of every capture equals
  the bound `expected_time.hex`, which proves the match without relying on the
  TB comparator. The per-frame logs it writes next to it are git-ignored
  (`*.log`) and are attached to the PR.
- **Plots:** `sim/python/plot_matching.py` draws one PNG per frame in the same
  folder from those captures, after checking their hashes against the
  evidence: the RTL output over the full window, a zoom with the float
  reference, the expected codes (rings) and the RTL output (dots), and the RTL
  minus expected error, 0 LSB on all 2055 samples of every frame.
  `plot_manifest.json` binds the plots to the evidence they were drawn from.

`test_rtl_time_matching.py` runs the four frames and the failure cases: a wrong
code at the first, a middle and the last flush index reports that absolute
index with the expected and captured codes; a declared latency of 8 or 10
fails the unstalled run; one undeclared output more times out; an extra flush
zero fails the drain check; staging refuses a broken sidecar, a payload or
`.svh` the manifest does not bind, and any output inside `sim/vectors/`. A
scratch run with one coefficient changed (179 to 178) failed at index 7, the
first output that tap reaches.

Learning:

- The time lane needed no new TB logic: T03 already built the finite-frame
  scoreboard, so T31 is mostly provenance. The hard part is keeping the
  binding honest (payload hashes, `.svh` against the manifest), not the
  comparison.
- "Measured" latency is declared and then asserted: the TB cannot place
  outputs without a manifest, so the value comes from the design and the
  unstalled run turns it into a measurement (a wrong value fails). The log
  prints it as `measured_latency_cycles`.
- Every edit to `gen_vectors.py` changes the source hash recorded in the F1
  and F2 manifests and in the T20/T21 evidence, so adding this stage meant
  regenerating them (provenance only; payloads, metrics and plots unchanged).

## Scope limits

These are structural checks against an independent reference of the accepted
policy. Its agreement with the T20 model (PR #78) and with the T22 production
export (PR #81) is part of the suite, so both integration gates are closed by
test, not by a one-off comparison. The T22 `.hex` frames are QPSK, so they do
not exercise rounding or saturation; the directed frames and the T20 gate
cover that, and the T31 match on those frames says nothing new about that
hardware. The robust matching run's sink stalls stay below eight cycles, so it
never reaches the tap-7 hold; the directed 40-cycle stall in
`test_rtl_time_serial.py` covers it. SLOW 10 MHz main-target timing and PPA
are T41 (#52): `openlane/README.md` and `sim/python/artifacts/t41-time-ppa/`.
