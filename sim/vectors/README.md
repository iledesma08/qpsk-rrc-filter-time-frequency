# sim/vectors — golden vectors (DO NOT edit by hand)

Generated only by `sim/python/gen_vectors.py` (T13, T22), according to
`docs/adr/0004-packed-external-vectors.md`.

The generator has three stages: T13 creates F1 float references, T22 exports
F2 per-domain Q2.14 integer expected codes after numerical acceptance, and
T31/T40 (time) and T33/T42 (frequency) produce F3 per-variant matching metadata
with measured latency and flush counts. Float references are not RTL expected codes; F1/F2 artifacts
must not invent future RTL latency. See the normative lifecycle in the schema.

- Each complex sample is a packed 32-bit `{Q[15:0], I[15:0]}` record in the
  input or expected-output `.hex` file.
- The `rtl_matching` stage (T31/T33/T40/T42) also writes `vector_manifest.svh` with the
  vector count, packing and measured per-variant metadata. Normative manifest
  schema: `docs/contracts/vector-manifest-schema.md`.
- RTL vector-matches against these files.
- Every generated vector must have a matching `<vector>.sha256` sidecar; CI verifies it.
- Generated SystemVerilog is metadata only; vectors are not compiled into the DUT.
- CSV is optional for Python analysis and is not consumed by RTL.
- If a test fails, regenerate with the script; never edit the vector.

## F1 float references (T13)

Regenerate with (Matias is the sole regenerator):

```bash
python sim/python/gen_vectors.py --stage float_reference --output-dir sim/vectors
```

Layout: `float_reference/<vector_set>/<vector_case>/`, one directory per frame
(`canonical/none` and `sys_corners/{corner_repeat,max_alternation,single_symbol_perturbation}`):

- `input_samples.c16.bin`: the 2048 zero-inserted input samples.
- `reference_time.c16.bin`, `reference_freq.c16.bin`: the 2055-sample full
  causal float64 references of each domain.
- `manifest_time.json`, `manifest_freq.json`: `artifact_stage: float_reference`,
  `model_domain`, schema section 1 stimulus fields, provenance, and file hashes.
- A `<file>.sha256` sidecar (`sha256sum` format) for every file above.

The `.c16.bin` payloads are raw C-order little-endian complex128 (`<c16`) with
no header, so each file's SHA-256 equals the array hash recorded by the T11/T12
evidence manifests. They are Python-side references for F2. They are not packed
`.hex` records and are never RTL expected codes. F1 writes no `.hex` and no
`vector_manifest.svh`. The `.hex` files arrive with `fxp_expected` (T22) and
`vector_manifest.svh` with `rtl_matching` (T31/T33).

Review plots of these vectors are separate evidence in `sim/python/artifacts/t13-reference-vectors/` (`gen_vectors.py --plots-dir`). They are never written here: this folder holds only generated payloads, manifests, and sidecars.

## F2 integer expected codes (T22)

Regenerate after F1, with the F1 frames already in the output directory
(Matias is the sole regenerator):

```bash
python sim/python/gen_vectors.py --stage fxp_expected --output-dir sim/vectors
```

The export reads each F1 frame after its hash check and runs the production
integer models of `sim/python/fxp.py` (`Q2.14`, RNE, 35-bit time accumulator,
FFT baseline A). Expected codes are never a cast of the float references. It
refuses to write anything unless the T21 evidence
(`sim/python/artifacts/t21-width-sweep/evidence_manifest.json`) accepts
production `Q2.14` on these same F1 manifests, every frame reproduces the output
codes T21 accepted, and every acceptance gate passes: SQNR >= 40 dB, a stable
split half and zero output saturation on `canonical`, the cross-domain gate on
`canonical`, and zero internal overflow on all four frames.

Layout: `fxp_expected/`, mirroring F1:

- `rrc8_q2.14_coefficients.json`: the production coefficient table. It keeps the
  `rrc8-v1` float64 golden beside the eight `Q2.14` codes
  `[179, -1818, 1818, 11295, 11295, 1818, -1818, 179]`, with hashes and
  provenance. A coefficient outside the 16-bit range is an error, never a
  saturation.
- `<vector_set>/<vector_case>/input.hex`: the 2048 `Q2.14` input codes, shared by
  both domains.
- `<vector_set>/<vector_case>/expected_time.hex`, `expected_freq.hex`: the 2055
  expected codes of each domain over the full causal window.
- `<vector_set>/<vector_case>/manifest_time.json`, `manifest_freq.json`:
  `artifact_stage: fxp_expected`, `model_domain`, schema sections 1, 2 and 4, the
  per-domain SQNR, split halves, overflow and saturation counts with the gates
  that apply to the frame, the T21 acceptance binding, and hashes of the F1
  manifest, coefficient table, T21 evidence, `.hex` files and codes (`<i8`,
  columns `[I, Q]`, as in the T20/T21 evidence).
- A `<file>.sha256` sidecar for every file above.

Each `.hex` line is one 32-bit `{Q[15:0], I[15:0]}` record (8 lowercase hex
digits) for `$readmemh`; at `W=16` the components are packed directly. F2
carries no RTL latency, transport counts or `vector_manifest.svh`, and the
per-domain manifests do not carry `sqnr_cross_db`. T31/T33 bind these payloads
by hash and add the measured per-variant metadata.

## F3 RTL matching metadata (T31, T33, T40)

Regenerate after F2, with the F2 frames already in the output directory
(Matias is the sole regenerator):

```bash
python sim/python/gen_vectors.py --stage rtl_matching --variant T-serial --output-dir sim/vectors
python sim/python/gen_vectors.py --stage rtl_matching --variant T-S4P1 --output-dir sim/vectors
python sim/python/gen_vectors.py --stage rtl_matching --variant T-S8P1 --output-dir sim/vectors
python sim/python/gen_vectors.py --stage rtl_matching --variant F-serial --output-dir sim/vectors
```

`T-serial` (T31, #48), `T-S4P1` and `T-S8P1` (T40, #51) and `F-serial` (T33, #50) are
implemented. `F-U4`/`F-U8` belong to T42 (#53); they refuse
instead of guessing their data.

Layout: `rtl_matching/<variant_id>/<vector_set>/<vector_case>/`, metadata only:

- `manifest_time.json`: `artifact_stage: rtl_matching`, `variant_id`,
  `rtl_variant`, schema sections 1-4 copied from the F2 manifest, the section 3
  streaming fields (`DATA_WIDTH`, `SPC`, block constants, `latency_samples`,
  `latency_cycles`, `fft_pipeline_cycles`) and the section 7 transport counts
  (`flush_samples`, `transport_padding_samples`, `accepted_input_samples`,
  `raw_output_samples`). For `T-serial`: `SPC=1`, latency 0 samples / 9 cycles,
  7 flush zeros, 2055 accepted and raw samples.
- `manifest_freq.json` (`F-serial`, T33): the same fields for the frequency
  domain: `SPC=1`, latency 0 samples / 99 cycles, `fft_pipeline_cycles=89`,
  8 flush zeros, 2056 accepted and raw samples (257 blocks). Index 2055 is the
  block padding, outside the compared window (`valid_len=2055`) and not an
  expected code.
- `T-S4P1`/`T-S8P1` are two rows of one RTL source (`rtl_variant: time_opt`).
  Their manifests add `rtl_parameters` (`SYSTOLIC_PES` 4 or 8,
  `PIPELINE_DEPTH` 1), which the runner turns into the module parameters. It
  stays out of the `.svh`, whose localparams are the T03 list, and never uses
  the legacy name `S`. Both rows declare latency 0 samples / 2 cycles and bind
  the same payloads as `T-serial`, since all three are bit-exact.
- `vector_manifest.svh`: the integer localparams the testbench includes, the
  same values as the JSON manifest. Generated SystemVerilog is metadata only.
- A `<file>.sha256` sidecar for each.

F3 never copies or rewrites the `.hex` payloads: the manifest points at
`fxp_expected/<vector_set>/<vector_case>/` with relative paths and binds the F2
manifest, `input.hex`, `expected_<tag>.hex` and the coefficient table by hash,
plus the `.svh` it describes. The export checks every F2 file against its
sidecar and its F2 manifest before writing anything. `latency_cycles` is the
variant's declared design latency; the matching run asserts it in the unstalled
run, and its evidence is
`sim/python/artifacts/t31-time-matching/evidence_manifest.json` (T-serial) and
`sim/python/artifacts/t40-time-opt-matching/<variant_id>/evidence_manifest.json`
(T-S4P1, T-S8P1). The manifests
carry no host tool versions, so a fresh export is byte-identical to the
committed one. `sim/python/tests/rtl_matching_stage.py` stages a frame for the
testbench after checking every binding; see `rtl/tb/README.md`.
