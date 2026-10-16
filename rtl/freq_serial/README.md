# rtl/freq_serial — frequency-domain filter, serial version (F-serial)

`freq_serial_filter.sv` is the serial baseline of the frequency lane: forced-50%
overlap-save, FFT16 → bin-wise product with `H[k]` → IFFT16, in the production
Q2.14 integer arithmetic of `docs/contracts/fxp-policy-16.md`. It replaces the
T03 transport shell (T32, #49). The datapath is the shared
`rtl/common/rrc_freq_engine.sv` with `U=1`; this wrapper adds the reset
synchronizer and the interface and parameter checks.

```bash
bash rtl/freq_serial/run.sh      # canonical T22 codes through rrc_stream_tb (structural fixture)
```

## Status

- CI runs `freq_serial` through the shared testbench `rrc_stream_tb` with a
  structural fixture built in `.build/` from the committed T22 vectors
  (`sim/python/tests/rtl_freq_fixture.py`; nothing is written to `sim/vectors/`).
  `bash rtl/freq_serial/run.sh` passes the canonical frame, and
  `sim/python/tests/test_rtl_freq_serial.py` passes all four frames (canonical
  and the three `sys_corners`, 2055 exact codes each, 257 blocks, 2056 raw
  outputs). Each run has a continuous pass (latency, `II` accounting) and a
  robust pass (bubbles, stalls, a reset after two accepted samples).
- The same test file checks the rounding and saturation primitives against an
  exact reference (the vectors reach no RNE tie and no output saturation), a
  reset in the middle of RUN, EMIT and DRAIN, the runner limits and a latency
  change. `test_rtl_freq_tables.py` compares the tables and widths with the T20
  freeze and the T22 coefficient export. `test_rtl_config.py` holds the
  parameter-override check.
- Elaborates with Icarus (`-g2012 -Wall`, no warnings). It synthesizes with the
  Yosys 0.46 of OpenLane 2.3.10 (synthesis step only: 30896 cells, 331821 um^2 of
  cell area). Verilator lint has only width/unused-bit warnings.
- The committed `rtl_matching` manifest, its hashes and the formal matching
  report (VCD coverage, steady-state `II`) are T33 (#50). The structural fixture
  does not replace them.
- Not placed and routed: the committed floorplan (`DIE_AREA` 200 x 200 um) is the
  T02 skeleton and is far too small for this design (about 331821 um^2 of cells),
  so the full flow stops at global placement. Sizing, timing and PPA are T43
  (#54).

## What this filter does

We filter the 2x-oversampled QPSK stream with the 8-tap RRC in the frequency
domain instead of convolving in time: **FFT → multiply by the filter response →
IFFT**. The result must equal the time-domain filter (within quantization).

Multiplying spectra is a *circular* convolution and the filter needs a *linear*
one. With a 16-point FFT and 8 taps, the first `M-1 = 7` outputs of every block
are corrupted by the wrap-around. We use overlap-save with a forced 50% overlap
(the revised assignment fixes it):

- A block is a 16-sample frame: **8 history samples + 8 new samples**. The
  history is the previous block's 8 new samples (zeros for the first block).
- The 16 outputs are `z[0:16]`. We **discard `z[0:8]`** (7 corrupted + 1 that
  repeats the previous block) and **emit `z[8:16]`**, which are the 8 correct
  output samples `y[8b .. 8b+7]`.
- Each block takes 8 samples and gives 8, so the hop is 8. The canonical frame
  is 2048 samples + 8 flush zeros = 2056 = 257 blocks; 2055 outputs are compared.

## Arithmetic

Data and coefficients are Q2.14 (16 bits, 14 fractional bits, so +1 is exactly
16384). Intermediates are wider: FFT stages grow 16 → 20 bits, the spectral
product has 41 bits, IFFT stages 42 → 45. Every reduction of fractional bits is
RNE (ties to even); saturation only appears in the final cast.

1. **Forward FFT16, radix-2 DIF, 4 stages, unscaled.** A butterfly takes `a` and
   `b` and gives `u = a + b` and `v = RNE14((a - b)·T[k])`, `T[k] = e^(-j2πk/16)`.
   The pairs are `span` apart: 8, 4, 2, 1. Each stage is **8 butterflies**, so a
   FFT is 4 × 8 = 32. The output is in bit-reversed order and is not reordered.
2. **Multiply by `H[k]`.** `H[k]` is the FFT16 of the 8 quantized taps padded
   with zeros, a fixed table computed once (stored at bit-reversed addresses so
   each bin meets its own `H`). The complex product is exact: no rounding, 28
   fractional bits (14 from the data, 14 from `H`).
3. **Inverse FFT16, radix-2 DIT, 4 stages, unscaled.** `v = RNE14(b·conj(T[k]))`,
   outputs `a + v` and `a - v`; spans 1, 2, 4, 8. Bit-reversed in, natural
   (time) order out.
4. **Scaling, once, at the end.** The unscaled forward FFT has gain 1 and the
   unscaled IFFT has gain 16, so the `/16` is applied exactly once, together with
   the binary-point move: 28 → 14 fractional bits (14) plus the `/16` (4) is one
   **RNE shift by 18**, then saturation to 16 bits (`output_cast`). This is the
   `1/N` of NumPy's inverse FFT. The 14-bit roundings inside the butterflies are
   the twiddle's binary point, not scaling. Scaling stage by stage ("baseline B")
   is an optional experiment, not what we build.

## Architecture: serial, `U = 1`

One butterfly unit (one complex multiplier plus an adder and a subtractor) is
reused for the forward FFT, the spectral product and the IFFT. This is the
serial baseline; "folded" is a different architecture of the extension scope.
All storage is internal registers: a 16 × 16-bit input frame (history + new
samples) and a 16-entry work buffer with 45-bit `I` and `Q`. The multiplier takes
45-bit by 16-bit operands (61-bit products, 62-bit sum). There is no external
memory, and the bins only ever live in the work buffer. The output is 8
time-domain samples per block, and whoever receives them concatenates the blocks.

The butterfly has two phases: one cycle fetches the operands into registers and
the next multiplies, rounds, adds or subtracts and writes back. Butterflies in a
pass touch disjoint pairs, so a fetch overlaps the previous execute; one drain
cycle at the end of each pass makes the next pass read fully written values.

| State | What happens | Cycles |
| --- | --- | --- |
| ACCEPT | 8 samples accepted, `ready_o` high | 8 |
| LOAD | frame copied (sign-extended) to the work buffer, history shifts | 1 |
| RUN | 4 FFT passes (9 each), product pass (17), 4 IFFT passes (9 each) | 89 |
| EMIT | `z[8:16]` out through one output register | 8 |
| DRAIN | last output waits for its consumer | 1 |

Measured with the testbench on the canonical frame (the fixture pins the 99): the first output appears 99
cycles after the first accepted sample, and the whole frame (2056 accepted
samples, 257 blocks, 2056 raw outputs) takes 27499 cycles, i.e. 107 cycles per
block, against 8 cycles per sample for the serial time-domain filter.

`ready_o` is high only in ACCEPT (gated by the synchronized reset) and is low
while computing and emitting. `valid_o`, `sample_o` and `ready_o` never depend
combinationally on `ready_i` or `valid_i`; the output register holds under
`ready_i = 0`. The work buffer is a uniform 45-bit container: every stage width
of the freeze fits it, and the engine checks at elaboration that no full-scale
frame can wrap it (`BOUND_BITS`, no port needed): `|x| < 2^16`, the unscaled FFT
gains at most 16, `|H[k]| <= |re|+|im| <= 30472 < 2^15` (`FREQ_H_L1_MAX`, tied to
the table by a test), the product keeps full precision and the unscaled IFFT gains
16 again, so every value is below 2^39 against a limit of 2^44. Adversarial
full-scale frames in the T20 model reach 2^34.1.

**Model/RTL difference.** The T20 model flags any value above its stage widths
(16..20 and 41..45), which only bound the accepted stimulus; on a full-scale frame
it would report overflow where the RTL silently computes in 45 bits. The RTL never
wraps, so it needs no overflow flag, and its results on the accepted frames are
bit-exact with the model.

**Reset.** The control state, the frame history (zero), `valid_o` and `sample_o`
are reset. The work buffer and the operand registers are not: this is an explicit
interpretation of "all internal history, accumulators and valid pipelines are
cleared" (`rtl-streaming-17`), because LOAD writes every entry before anything
reads it, no output is valid before that, and reset flops are larger in sky130. A
reset in RUN, EMIT or DRAIN is covered by a test. `ex_v` could also go unreset: it
clears itself in the first cycle.

## Parameters

`FFT_LEN`, `HOP`, `DISCARD_PREFIX`, `EMIT_START` and `EMIT_LEN` are real
parameters: the history depth (`FFT_LEN - HOP`), the block counter and the
emission window derive from them. The transform and its tables are fixed at 16
points, `DISCARD_PREFIX` must be at least 7 (an 8-tap filter), `EMIT_START` must
equal `DISCARD_PREFIX` and `EMIT_LEN` must equal `HOP`; one function,
`rrc_freq_pkg::valid_framing`, is the predicate for the engine and the wrapper.
Violations, and `DATA_WIDTH != 16` or `SPC != 1`, fail at time zero. **Only the baseline tuple
(16, 8, 8, 8, 8) is a contract configuration**: the revised assignment fixes
hop 8 and no alternative schedule is planned (`frequency-block-contract-14.md`),
so other structurally legal tuples such as `HOP=9` are elaboration checks, not
supported or verified configurations.

## Open items

- Integration gate (#49), checked on 2026-10-13: the twiddle and `H[k]` tables of
  `rrc_freq_pkg.sv` equal the T20 freeze, and `H[k]` recomputed from the T22
  coefficient codes (`[179, -1818, 1818, 11295, 11295, 1818, -1818, 179]`) with
  the frozen rule (DFT16 of the zero-padded codes, one RNE) is identical too. The
  committed matching and the `rtl_matching` metadata are T33 (#50), including
  the value to record for `fft_pipeline_cycles`.
- `U` is a parameter of the engine for the F-U4/F-U8 rows (T42); only `U=1`
  elaborates.
- Declared deviation from "no duplicated constants" (`rtl-streaming-17` D8,
  CONTRIBUTING section 7): `rrc_freq_pkg` repeats `FREQ_FFT_LEN` and `FREQ_IN_W`
  because the Yosys of OpenLane 0.46 cannot parse a package parameter that refers
  to another package; the engine checks them against `rrc_pkg` at elaboration and a
  test checks them too. `FREQ_FILTER_TAPS` and `FREQ_FRAC` wait for T30 (#79) to
  add `RRC_TAPS` and `FRAC_BITS` to `rrc_pkg`.

## Learning

- Overlap-save exists because multiplying FFT spectra is a circular convolution.
  Half of every block's output is discarded on purpose: 7 values are corrupted by
  the wrap-around and the eighth repeats the previous block. That is the price of
  the forced 50% overlap.
- Samples enter one at a time (`SPC = 1`); 8 new samples plus 8 of history form
  the 16-sample frame, and each block emits 8 time-domain samples. The bins only
  exist inside the work buffer.
- A FFT16 stage is 8 butterflies, so the FFT is 32 butterflies and the IFFT
  another 32, all run by the same butterfly one after another.
- The unscaled FFT has gain 1 and the unscaled IFFT gains 16. The `/16` is applied
  exactly once, fused with the binary-point move into a single RNE shift of 18
  bits; any other count changes the output scale.
- The product with `H[k]` is what turns FFT/IFFT into a filter, and it is exact.
  The only intermediate roundings are the 14-bit ones of the twiddle products.
- Serial means one butterfly shared by every phase: it costs cycles (about 107
  per block) and gives the minimum arithmetic area. F-U4/F-U8 replicate this unit,
  so it lives in `rtl/common`.
- The widths of the numeric freeze only bound the accepted stimulus. The 45-bit
  container was sized with a magnitude bound and checked against adversarial
  full-scale inputs, which is what shows it cannot wrap.
