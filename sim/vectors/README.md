# sim/vectors — golden vectors (DO NOT edit by hand)

Generated only by `sim/python/gen_vectors.py` (T13), according to
`docs/adr/0004-packed-external-vectors.md`.

The generator has three stages: T13 creates F1 float references, T22 exports
F2 per-domain Q2.14 integer expected codes after numerical acceptance, and
T31/T33 produce F3 per-variant matching metadata with measured latency and
flush counts. Float references are not RTL expected codes; F1/F2 artifacts
must not invent future RTL latency. See the normative lifecycle in the schema.

- Each complex sample is a packed 32-bit `{Q[15:0], I[15:0]}` record in the
  input or expected-output `.hex` file.
- The generator also writes `vector_manifest.svh` with the vector count and
  packing metadata. Normative manifest schema:
  `docs/contracts/vector-manifest-schema.md`.
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
`vector_manifest.svh`. Those arrive with `fxp_expected` (T22) and
`rtl_matching` (T31/T33).

Review plots of these vectors are separate evidence in `sim/python/artifacts/t13-reference-vectors/` (`gen_vectors.py --plots-dir`). They are never written here: this folder holds only generated payloads, manifests, and sidecars.
