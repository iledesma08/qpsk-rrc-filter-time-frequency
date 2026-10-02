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

Placeholder: this README keeps the folder in git.
