# Vector Manifest Schema

Decision tickets: [#15](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/15), [#16](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/16), [#17](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/17)

Map: [#12](https://github.com/iledesma08/qpsk-rrc-filter-time-frequency/issues/12)

Date: 2026-09-23

Branch: `docs/12-contracts-remediation`

Scope: single normative schema for every generated vector set (T13 `gen_vectors.py`
output in `sim/vectors/`). This file is normative; the per-document field lists in
`qpsk-stimulus-15.md`, `fxp-policy-16.md`, `rtl-streaming-17.md`, and
`sim/vectors/README.md` are non-normative examples that point here. No
implementation code is included.

**Status:** normative. This file resolves the forward-looking
`vector-manifest-schema.md` pointer in ADR-0004
(`docs/adr/0004-packed-external-vectors.md:3`), which was dangling until this
task landed (see Task 4 report, Concerns §1).

## Conformance

- The generator MUST emit every field in §1-§4 for every vector set.
- The testbench MUST read `DATA_WIDTH`, `SPC`, `valid_start`, `valid_len`, and
  `latency_samples` from the manifest, never from hardcoded values (per
  `rtl-streaming-17.md` Testbench Contract).
- The hash check MUST pass before any vector comparison counts: every vector
  file has a matching `<vector>.sha256` sidecar (per ADR-0004 and
  `sim/vectors/README.md`); CI verifies it.
- Physical encoding: packed `.hex` records are one 32-bit `{Q[15:0], I[15:0]}`
  per complex sample, consumed with `$readmemh`; vectors are never compiled
  into the DUT; generated SystemVerilog (`vector_manifest.svh`) is metadata
  only; CSV is optional for Python analysis and is not consumed by RTL (per
  ADR-0004 and `sim/vectors/README.md`).
- Invariants (MUST hold; testbench may assert):
  - `DATA_WIDTH == W_common`
  - `SPC == SAMPLES_PER_CLOCK` (interface width, not throughput)
  - `F_data == F_coeff == W_common - 2` (see §5)
  - `input_samples == 2048`, `output_samples == 2055`,
    `valid_start == 0`, `valid_len == 2055`
  - `FFT_LEN == 16`, `HOP == 8`, `DISCARD_PREFIX == 8`, `EMIT_START == 8`,
    `EMIT_LEN == 8 == FFT_LEN - DISCARD_PREFIX`
  - `block_cadence == HOP`

Legacy aliases (MUST NOT be emitted as canonical fields; listed only so old
text stays readable): `input_scale_16bit` / `coefficient_scale_16bit` /
`output_scale_16bit` / `evidence_interpolation` (pre-Task-6 stimulus wording,
superseded by `W_common`/`F_data`/`F_coeff` + `rounding_mode`/`overflow_mode`);
`latency_time` / `latency_freq` (FXP sweep-row wording, superseded by
`latency_samples` / `latency_cycles` per variant); `valid_count` (alias of
`valid_len`); `S` (PPA time-lane factor, not the interface; do not conflate
`S` / `SPC` / `II`).

## 1. Stimulus fields (source: #15)

| Field | Type / allowed values | Meaning / source |
| --- | --- | --- |
| `stimulus_version` | string, `qpsk-stim-15-v1` | Stimulus contract version (`qpsk-stimulus-15.md` Vector Manifest Fields). |
| `symbol_count` | integer, `1024` | Frame length `S` (D1). |
| `edge_pattern_symbols` | integer, `40` | Five fixed 8-symbol patterns prepended (D3). |
| `random_seed` | integer, `2026` | Seed for `default_rng` (D2). |
| `prng` | string, `numpy.random.default_rng (PCG64)` | Generator (D2). |
| `symbol_map` | string, `0=+1+j, 1=+1-j, 2=-1+j, 3=-1-j` | `rng.integers(0,4)` corner mapping (Edge Patterns). MUST NOT be mutated: it is the executable mapping. |
| `symbol_map_coding` | string, `gray` | Descriptive metadata of `symbol_map` (adjacent symbols differ in one bit). MUST stay consistent with `symbol_map`; it describes the mapping without redefining it (T13 asserts consistency). |
| `symbol_energy` | number, `2` | Nominal pre-filter symbol energy `Es = E[\|s_k\|^2]` (`2` for `s_k in {+/-1 +/- j}`). Metadata only: it does not rescale `.hex`, RTL, or expected codes. MUST match the computation from `symbol_map` (T13 checks). |
| `vector_set` | enum: `canonical` \| `sys_corners` | Vector family. `canonical` is the 1024-symbol reference frame; `sys_corners` are full-length deterministic frames (Corner Sets). No `clean` family exists: the canonical stimulus is already noiseless. |
| `vector_case` | string, `none` \| `corner_repeat` \| `max_alternation` \| `single_symbol_perturbation` (extensible) | Stable case identifier within the family; `none` for the single-case `canonical` set. Future corners add new names without schema changes. |
| `samples_per_symbol` | integer, `2` | 2x oversampling (D4). |
| `upsampling` | string, `zero_insertion` | Zero insertion; vectors carry post-upsampling samples (D4). |
| `input_samples` | integer, `2048` | `L = 2*S` complex samples. |
| `output_samples` | integer, `2055` | Full causal `L + M - 1 = 2048 + 7` (D6). |
| `valid_start` | integer, `0` | Comparison window start (D6). |
| `valid_len` | integer, `2055` | Comparison window length; same window for time, frequency, FXP, RTL (D6). |
| `symbol_center_offset_samples` | float, `3.5` | Pulse center of symbol `k` at sample `2k + 3.5`; no output sample sits exactly at a center (D7, Signal Model). |

## 2. FXP policy fields (source: #16)

| Field | Type / allowed values | Meaning / source |
| --- | --- | --- |
| `W_common` | integer, `8, 10, 12, 14, 16, 18` (extend to `20` if nothing reaches 40 dB) | Shared external word width for data and coefficients (D1, D2). |
| `F_data` | integer, `W_common - 2` | Fractional bits of QPSK I/Q input (Numeric Policy; see §5). |
| `F_coeff` | integer, `W_common - 2` | Fractional bits of RRC coefficient; `Q1.(W-1)` stays a labelled phase-E sensitivity only (D2). |
| `rounding_mode` | enum: `RNE` (canonical) \| `truncation_toward_zero` (comparison row only) | RNE at every intentional narrowing; Python model and RTL use the same named op (Rounding). |
| `overflow_mode` | enum: `saturating_narrowing` (explicit boundaries only) \| `fail_on_internal_overflow` (accumulators) \| `wrap_diagnostic_only` (one negative control) | Saturation only at explicit narrowing/output; accumulators expose a flag and fail the candidate; wrap appears once as diagnostic (Saturation and overflow). |
| `W_product` | integer, `2*W_common` | Product width `W_d + W_c`; products added at full precision, single cast after the 8-term sum (Products). |
| `W_acc_time` | integer, baseline `2*W_common + 3`; experiment `2*W_common + 1`, `2*W_common + 2` with overflow assertion | Time accumulator width; `F_acc = 2*F` (D4, Products). |
| `fft_mode` | enum: `baseline_A_grow_by_stage` \| `baseline_B_one_bit_per_stage` | Frequency scaling under comparison at the same `W` (D5). |
| `fft_stage_widths` | int list, baseline A: `W, W+1, W+2, W+3, W+4` | Per-stage forward-FFT widths for unscaled 16-point radix-2 (Frequency-domain internal widths). Baseline B records its per-stage shift instead. |
| `W_acc_freq` | integer (example §7 derives `41`-bit pointwise product, `+4` unscaled-IFFT guard at `W=16`) | Frequency accumulator / datapath width at the declared `fft_mode`; both baselines use the same RNE rule (D5). |
| `ifft_scale` | string, `divide_by_16_then_cast_to_Q2.(W-2)` | Final normalization: divide by 16, then cast to `Q2.(W-2)`; the NumPy-default `1/N` is compensated exactly once (Frequency-domain internal widths, #14 D3). |

## 3. RTL streaming fields (source: #17)

| Field | Type / allowed values | Meaning / source |
| --- | --- | --- |
| `DATA_WIDTH` | integer, MUST equal `W_common` | Per-component width `W` (Interface Specification, Parameters). |
| `SPC` | integer, `1` serial baseline; `>1` unfolded | `SAMPLES_PER_CLOCK`: complex samples accepted/emitted per clock; interface width, not throughput (D4, Transfer rules). |
| `FFT_LEN` | integer, `16` | Frequency block transform length (D7, Parameters). |
| `HOP` | integer, `8` | New input samples per frequency block (D7, Parameters). |
| `DISCARD_PREFIX` | integer, `8` | IFFT samples discarded per block (D7, Parameters). |
| `EMIT_START` | integer, `8` | First emitted IFFT index (D7, Parameters). |
| `EMIT_LEN` | integer, `8` | Emitted samples per block, `FFT_LEN - DISCARD_PREFIX` (D7, Parameters). |
| `latency_samples` | integer, per variant | Sample-index distance from first input to first valid output (Latency declaration). Comparison uses absolute indices, never arrival time. |
| `latency_cycles` | integer, per variant | Implementation cycles, i.e. pipeline depth (Latency declaration). |
| `block_cadence` | integer, `== HOP` | Accepted input samples per frequency block; `8` for forced-50% (Latency declaration, #14 Block latency). |
| `fft_pipeline_cycles` | integer, per frequency variant | FFT + multiply + IFFT pipeline depth, recorded separately from block cadence (Latency declaration). |

`II` (initiation interval) is measured from the handshake (`valid && ready`),
never inferred from `SPC` alone; for the serial time lane `S=1`, `II=8`
(`ready_o` deasserts 7 of every 8 cycles under `valid_i = 1`); `ready_o = 1`
every cycle holds only for fully-parallel variants (D4, D5, Transfer rules).

## 4. Packing and integrity fields (sources: ADR-0004, #16 D7, #17)

| Field | Type / allowed values | Meaning / source |
| --- | --- | --- |
| `component_sign_extension` | enum: `sign_extend_to_16` | When `W < 16`, each signed component is sign-extended into the existing 16-bit I/Q field of the packed `{Q[15:0], I[15:0]}` record; when `W = 16` the field is direct (see §6). A candidate above 16 bits requires revisiting the record format instead of silent truncation (#16 Manifest Fields). |
| `hashes` | map: `stimulus_manifest_sha256`, `vector_manifest_sha256`, plus one `<vector>.sha256` sidecar per `.hex` file | Provenance: the hashes prove RTL and simulator consumed the same contract (#16 Sweep Matrix / Relationship; ADR-0004; `sim/vectors/README.md`). |

## 5. Common format `Q2.(W-2)`

`Qm.n` means `m` integer bits (sign included) plus `n` fractional bits,
`m + n` bits total; the stored integer represents the real value times `2^n`
(per `rrc-coefficient-contract-13.md` Q7/Q15 and `fxp-policy-16.md` D2).

- Data and coefficients share one signed format `Q2.(W-2)`: `F = W - 2`
  fractional bits, range approximately `[-2, +2)`.
- Quantization for a real value `x`:
  `q_unbounded = round_even(x * 2^F)`,
  `q = min(max(q_unbounded, -2^(W-1)), 2^(W-1)-1)` (per #16 Numeric Policy).
- `+1` and `-1` are exactly representable, which is why `Q2.(W-2)` is used for
  the declared `+/-1 +/- j` constellation instead of `Q1.15` (whose maximum is
  `1 - 2^-15`).
- At `W=16` the format is `Q2.14` and the accepted coefficients are the
  integers `[179, -1818, 1818, 11295, 11295, 1818, -1818, 179]` (per #16
  Numeric Policy). The `Q1.(W-1)` coefficient integers
  (`[359, -3636, 3636, 22590, 22590, 3636, -3636, 359]` at `W=16`) stay a
  labelled phase-E sensitivity experiment and are never folded into the
  common-width claim (per #16 D2/D4 and Task 1 remediation).

## 6. Sign extension into the packed record

Per #16 D7 and Manifest Fields, and the #17 Testbench Contract:

1. External records stay one 32-bit `{Q[15:0], I[15:0]}` with `I = real`,
   `Q = imaginary` (per ADR-0004 and #14 Complex FFT and Packing Contract).
2. When `W < 16`, each `W`-bit signed component is sign-extended to 16 bits
   before packing; the manifest records `component_sign_extension:
   sign_extend_to_16` and the active `W_common` stays explicit.
3. When `W = 16`, packing is direct.
4. A future candidate with `W > 16` MUST revisit the record format instead of
   truncating silently.
5. The testbench compares stored integer bit patterns after sign extension
   (exact match); it never compares via floating-point reconversion. A
   mismatch reports the absolute index, the expected code, and the captured
   code.

## 7. Frequency block count: 257 blocks

Per the accepted #14 forced-50% schedule (`frame_b[r] = x[8b-8+r]`, discard
`z[0:8]`, emit `z[8:16]`, first frame eight zeros + `x[0:8]`) and the #15 full
causal window (`valid_len = 2055 = 2048 + 7`):

- `blocks = ceil(2055 / 8) = 257`: 256 steady-state blocks + 1 tail-flush
  block (per `ppa-matrix-18.md` Workload as fixed in Task 2).
- The input is `2048` samples plus zero padding to cover `S+M-2` (per
  `frequency-block-contract-14.md` Padding/Ending), trimmed to
  `valid_len = 2055`.
- Steady-state `II` is reported on the first 256 blocks; latency is split
  into fill vs tail; VCD/SAIF activity covers all 257 blocks (per
  `ppa-matrix-18.md` Workload).
- The 257-block accounting does not change the emitted `y[n]` values: both
  hop-8 and hop-9 schedules produce the same sequence; only the framing
  differs (per #14 Switching cost).

## 8. Example manifest (`W = 16`, baseline A, serial time lane)

Non-normative illustration of a complete manifest. Normative allowed values
are in §1-§4; this example fixes one consistent point.

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
W_common: 16
F_data: 14
F_coeff: 14
rounding_mode: RNE
overflow_mode: saturating_narrowing_with_fail_on_internal_overflow
W_product: 32
W_acc_time: 35
fft_mode: baseline_A_grow_by_stage
fft_stage_widths: [16, 17, 18, 19, 20]
W_acc_freq: 45
ifft_scale: divide_by_16_then_cast_to_Q2.14
DATA_WIDTH: 16
SPC: 1
FFT_LEN: 16
HOP: 8
DISCARD_PREFIX: 8
EMIT_START: 8
EMIT_LEN: 8
latency_samples: 0
latency_cycles: 8
block_cadence: 8
fft_pipeline_cycles: 12
component_sign_extension: sign_extend_to_16
hashes:
  stimulus_manifest_sha256: <hex>
  vector_manifest_sha256: <hex>
```

Notes on the example: `W_product = 2*16 = 32`; `W_acc_time = 2*16+3 = 35`;
`fft_stage_widths` is baseline A at `W=16`; `W_acc_freq = 45` derives from the
`2*(16+4)+1 = 41`-bit pointwise product plus four unscaled-IFFT guard bits
(per #16 Frequency-domain internal widths) and is illustrative of baseline A;
`latency_cycles = 8` is wall-clock cycles from the first accepted input to the
first valid output measured with `ready_i = 1` held continuously and no
testbench stalls or gaps (per `rtl-streaming-17.md` Testbench Contract); for
this serial example it numerically coincides with the 8-cycle accept cadence,
but `latency_cycles` and `II` are different quantities and diverge in
pipelined or block variants. `latency_samples = 0` keeps absolute-index
comparison; `fft_pipeline_cycles`
is per-variant (12 shown as a placeholder depth); `W=16` packs directly so
`component_sign_extension` records the rule that sub-16 widths use.

## 9. Source pointers

| Manifest group | Normative contract | What that contract owns |
| --- | --- | --- |
| Stimulus (§1) | `docs/contracts/qpsk-stimulus-15.md` (D1-D8, Signal Model, Edge Patterns, Valid Output Window, Corner Sets) | Frame, PRNG/seed, edge patterns, upsampling, causal window, symbol centers, `Es = 2`, Gray mapping, `canonical` + `sys_corners` sets. |
| FXP policy (§2, §5, §6) | `docs/contracts/fxp-policy-16.md` (D1-D9, Numeric Policy, Sweep Matrix, Manifest Fields) | Common `Q2.(W-2)`, sweep widths, RNE/saturation, accumulator widths, FFT baselines, sign extension. Backed by `docs/contracts/fxp-common-width-16.md` (historical research report). |
| Streaming (§3) | `docs/contracts/rtl-streaming-17.md` (D1-D9, Interface Specification, Latency declaration, Testbench Contract) | Handshake, reset, packed `{Q, I}` bus, `SPC` vs `II`, latency declaration, frequency block parameters, vector-matching rules. |
| Block schedule (§7) | `docs/contracts/frequency-block-contract-14.md` (forced-50% OLS, Padding/Ending, Block latency) + `docs/contracts/ppa-matrix-18.md` (Workload) | `N=16`, `H=8`, discard `z[0:8]`, emit `z[8:16]`; 257-block tail-flush accounting. |
| Coefficients | `docs/contracts/rrc-coefficient-contract-13.md` (D1-D7, as refined by #16 D2) | 8-tap grid, raw values, unit-energy normalization, `D = 3.5`; coefficient format refined to common `Q2.(W-2)` by #16. |
| Packing / hash | `docs/adr/0004-packed-external-vectors.md` + `sim/vectors/README.md` | `{Q[15:0], I[15:0]}` records, `$readmemh`, `<vector>.sha256` sidecars, `vector_manifest.svh` metadata-only rule. |
| Correctness bars | `docs/adr/0005-common-sqnr-contract.md` + `docs/adr/0001-python-float-golden-simulator.md` | SQNR formula with `>= 40 dB` in both domains; float equality `rtol=1e-10`, `atol=1e-12`. |

## References

- QPSK stimulus contract: `docs/contracts/qpsk-stimulus-15.md`.
- FXP policy contract: `docs/contracts/fxp-policy-16.md`.
- RTL streaming contract: `docs/contracts/rtl-streaming-17.md`.
- Frequency block contract: `docs/contracts/frequency-block-contract-14.md`.
- RRC coefficient contract: `docs/contracts/rrc-coefficient-contract-13.md`.
- PPA matrix: `docs/contracts/ppa-matrix-18.md`.
- ADR-0004 packed external vectors, ADR-0005 common SQNR contract, and
  `CONTEXT.md` for the canonical vocabulary.
