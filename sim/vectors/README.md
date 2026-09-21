# sim/vectors — golden vectors (DO NOT edit by hand)

Generated only by `sim/python/gen_vectors.py` (T13), according to
`docs/adr/0004-packed-external-vectors.md`.

- Each complex sample is a packed 32-bit `{Q[15:0], I[15:0]}` record in the
  input or expected-output `.hex` file.
- The generator also writes `vector_manifest.svh` with the vector count and
  packing metadata.
- RTL vector-matches against these files.
- Every generated vector must have a matching `<vector>.sha256` sidecar; CI verifies it.
- Generated SystemVerilog is metadata only; vectors are not compiled into the DUT.
- CSV is optional for Python analysis and is not consumed by RTL.
- If a test fails, regenerate with the script; never edit the vector.

Placeholder: this README keeps the folder in git.
