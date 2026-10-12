# rtl/freq_serial — frequency-domain filter, serial version (F-serial)

`freq_serial_filter.sv` is the serial baseline of the frequency lane: forced-50%
overlap-save, FFT16 → bin-wise product with `H[k]` → IFFT16, in the production
Q2.14 integer arithmetic of `docs/contracts/fxp-policy-16.md`. It replaces the
T03 transport shell (T32, #49). The datapath is the shared
`rtl/common/rrc_freq_engine.sv` with `U=1`; this wrapper adds the reset
synchronizer and the interface and parameter checks.

```bash
bash rtl/freq_serial/run.sh      # elaborates the DUT; it is NOT a functional check
```

## Status

- Elaborates with Icarus (`-g2012 -Wall`) and passes the structural parameter
  tests. Verilator lint has only width/unused-bit warnings.
- **Not functionally verified.** Matching against expected codes needs the T22
  vectors (#46) and the per-variant metadata (T33, #50), so the runner does not
  simulate yet. The 257-block schedule, latency and `II` are not measured. The
  tables were generated from the frozen model (`fxp.py`), not retyped.
- Not synthesized: no Yosys/OpenLane run, no timing or PPA (T43, #54).

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
samples) and a 16-entry work buffer with 45-bit `I` and `Q`. There is no external
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

That is about 107 cycles per block (an estimate; not measured yet), about 27
thousand for the canonical frame, against 8 cycles per sample for the serial
time-domain filter.

`ready_o` is high only in ACCEPT (gated by the synchronized reset) and is low
while computing and emitting. `valid_o`, `sample_o` and `ready_o` never depend
combinationally on `ready_i` or `valid_i`; the output register holds under
`ready_i = 0`. The work buffer is a uniform 45-bit container: every stage width
of the freeze fits it, and the largest value reachable is far below its limit
(analytic bound about 2^38.4; adversarial full-scale frames in the T20 model reach
2^34.1), so the hardware cannot wrap and no overflow port is needed.

## Parameters

`FFT_LEN`, `HOP`, `DISCARD_PREFIX`, `EMIT_START` and `EMIT_LEN` are real
parameters: the history depth (`FFT_LEN - HOP`), the block counter and the
emission window derive from them. The transform and its tables are fixed at 16
points, `DISCARD_PREFIX` must be at least 7 (an 8-tap filter), `EMIT_START` must
equal `DISCARD_PREFIX` and `EMIT_LEN` must equal `HOP`. Violations, and
`DATA_WIDTH != 16` or `SPC != 1`, fail at time zero. **Only the baseline tuple
(16, 8, 8, 8, 8) is a contract configuration**: the revised assignment fixes
hop 8 and no alternative schedule is planned (`frequency-block-contract-14.md`),
so other structurally legal tuples such as `HOP=9` are elaboration checks, not
supported or verified configurations.

## Open items

- Integration gate (#49): the T22 export (#46) and the T20 policy must be
  checked against the tables in `rrc_freq_pkg.sv` (twiddles, `H[k]`) before
  closing; the matching and metadata are T33.
- `U` is a parameter of the engine for the F-U4/F-U8 rows (T42); only `U=1`
  elaborates.

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
