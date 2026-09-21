# Packed external vectors for vector matching

**Status: accepted**

Python remains the golden-vector source of truth. `gen_vectors.py` generates
packed `.hex` input and expected-output files, one 32-bit record per complex
sample using `{Q[15:0], I[15:0]}`, plus a SHA-256 sidecar and a generated
`vector_manifest.svh` containing metadata such as the vector count and
packing. Testbenches consume the files with `$readmemh`; vectors are never
compiled into the DUT. Generated SystemVerilog includes are reserved for small
hardware constants such as frozen coefficient tables.

CSV may be emitted as an optional Python-analysis export, but it is not part
of RTL vector matching.
