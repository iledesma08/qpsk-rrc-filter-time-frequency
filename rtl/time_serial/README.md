# rtl/time_serial — time-domain filter, serial version

T30 (#47) serial baseline `T-serial`: `S=1`, `P=1`, `SPC=1`, `II=8`. Run the
structural canonical frame from the repository root:

```bash
bash rtl/time_serial/run.sh
python -m pytest sim/python/tests/test_rtl_time_serial.py -v
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

## Scope limits

These are structural checks against an independent reference of the accepted
policy. Its agreement with the T20 model (PR #78) is part of the suite, so the
T20 integration is closed by test, not by a one-off comparison. Final
integration with the T22 production artifacts (#46) is still
open. Exact matching against `sim/vectors/`, measured `rtl_matching` metadata
and the `sys_corners` sets are T31 (#48). SLOW 10 MHz main-target timing and PPA
belong to T41 (#52). The OpenLane JSON's 10 ns setup is not timing evidence.
